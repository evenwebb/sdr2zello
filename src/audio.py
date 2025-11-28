"""
Audio Management and Processing for sdr2zello
Handles audio routing to Zello app via system audio with advanced DSP filtering
"""

import asyncio
import numpy as np
import wave
import logging
import json
import io

try:
    import pyaudio
except ImportError:
    pyaudio = None
    logging.warning("pyaudio not installed - audio output will be disabled")

try:
    import lameenc
    LAMEENC_AVAILABLE = True
except ImportError:
    LAMEENC_AVAILABLE = False
    logging.warning("lameenc not installed - MP3 encoding will be disabled, using WAV instead")

from typing import Optional, Callable, List, Dict, Any
from datetime import datetime
import threading
import os

from .config import get_settings
from .dsp_filters import create_dsp_processor, DSPProcessor
from .security import sanitize_filename

logger = logging.getLogger(__name__)


class AudioBuffer:
    """Thread-safe audio buffer for storing transmission audio (optimized with NumPy)"""

    def __init__(self, max_duration: float = 30.0, sample_rate: int = 48000):
        self.max_samples = int(max_duration * sample_rate)
        self.sample_rate = sample_rate
        # Use NumPy array instead of queue for better performance
        self.buffer = np.zeros(self.max_samples, dtype=np.float32)
        self.write_index = 0
        self.is_recording = False
        self.start_time = None
        self._lock = threading.Lock()

    def start_recording(self):
        """Start recording audio"""
        with self._lock:
            self.clear()
            self.is_recording = True
            self.write_index = 0
            self.start_time = datetime.now()

    def stop_recording(self) -> tuple:
        """Stop recording and return audio data"""
        with self._lock:
            self.is_recording = False
            duration = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0.0

            # Extract audio data (only recorded portion)
            if self.write_index > 0:
                audio_data = self.buffer[:self.write_index].copy()
            else:
                audio_data = np.array([], dtype=np.float32)

            return audio_data, duration

    def add_samples(self, samples: np.ndarray):
        """Add audio samples to buffer (optimized with NumPy)"""
        if not self.is_recording or samples.size == 0:
            return

        with self._lock:
            if not self.is_recording:
                return
            
            # Flatten if needed
            if samples.ndim > 1:
                samples = samples.flatten()
            
            # Calculate how many samples we can add
            remaining_space = self.max_samples - self.write_index
            samples_to_add = min(len(samples), remaining_space)
            
            if samples_to_add > 0:
                # Add samples
                end_idx = self.write_index + samples_to_add
                self.buffer[self.write_index:end_idx] = samples[:samples_to_add]
                self.write_index = end_idx
            
            # If buffer is full and more samples, shift buffer (circular buffer behavior)
            if samples_to_add < len(samples) and self.write_index >= self.max_samples:
                # Shift buffer left and add remaining samples
                overflow = len(samples) - samples_to_add
                self.buffer[:-overflow] = self.buffer[overflow:]
                self.buffer[-overflow:] = samples[samples_to_add:]
                # write_index stays at max_samples

    def clear(self):
        """Clear the buffer"""
        with self._lock:
            self.buffer.fill(0.0)
            self.write_index = 0


class VirtualAudioDevice:
    """Manages virtual audio device for routing to Zello with DSP processing"""

    def __init__(self, sample_rate: int = 48000, channels: int = 1, dsp_config: Optional[Dict] = None):
        self.sample_rate = sample_rate
        self.channels = channels
        self.pyaudio_instance = None
        self.output_stream = None
        self.device_index = None

        # Initialize DSP processor
        self.dsp_processor = create_dsp_processor(sample_rate=sample_rate, config=dsp_config)
        self.dsp_enabled = True

        logger.info(f"VirtualAudioDevice initialized with DSP processing")

    async def initialize(self):
        """Initialize audio device"""
        if pyaudio is None:
            logger.warning("PyAudio not available - audio output disabled")
            return

        try:
            self.pyaudio_instance = pyaudio.PyAudio()

            # Find suitable output device
            self.device_index = await self._find_output_device()

            if self.device_index is None:
                logger.warning("No suitable audio output device found, using default")
                self.device_index = self.pyaudio_instance.get_default_output_device_info()['index']

            logger.info(f"Using audio device index: {self.device_index}")

        except Exception as e:
            logger.error(f"Error initializing audio device: {e}")
            # Don't raise in case of audio issues - continue without audio
            logger.warning("Continuing without audio output")

    async def _find_output_device(self) -> Optional[int]:
        """Find suitable output device"""
        if not self.pyaudio_instance:
            return None

        try:
            device_count = self.pyaudio_instance.get_device_count()

            for i in range(device_count):
                device_info = self.pyaudio_instance.get_device_info_by_index(i)

                # Look for virtual audio cable or similar devices (Linux PulseAudio)
                device_name = device_info.get('name', '').lower()
                if any(keyword in device_name for keyword in
                       ['virtual', 'cable', 'pulse', 'monitor', 'sdr2zello']):
                    if device_info.get('maxOutputChannels', 0) > 0:
                        logger.info(f"Found virtual audio device: {device_info['name']}")
                        return i

            # Fallback to default output device
            default_device = self.pyaudio_instance.get_default_output_device_info()
            logger.info(f"Using default audio device: {default_device['name']}")
            return default_device['index']

        except Exception as e:
            logger.error(f"Error finding output device: {e}")
            return None

    async def play_audio(self, audio_data: np.ndarray):
        """Play audio through the virtual device
        
        Returns:
            tuple: (success: bool, error_message: str)
        """
        if pyaudio is None or not self.pyaudio_instance or audio_data.size == 0:
            return False, "Audio device not initialized or empty audio data"

        try:
            # Convert to appropriate format
            audio_data = self._prepare_audio_data(audio_data)

            # Create output stream if not exists
            if not self.output_stream or self.output_stream._stream is None:
                self.output_stream = self.pyaudio_instance.open(
                    format=pyaudio.paFloat32,
                    channels=self.channels,
                    rate=self.sample_rate,
                    output=True,
                    output_device_index=self.device_index,
                    frames_per_buffer=1024
                )

            # Play audio
            audio_bytes = audio_data.astype(np.float32).tobytes()
            self.output_stream.write(audio_bytes)
            return True, ""

        except Exception as e:
            error_msg = f"Error playing audio: {e}"
            logger.error(error_msg)
            return False, str(e)

    def _prepare_audio_data(self, audio_data: np.ndarray) -> np.ndarray:
        """Prepare audio data for playback with DSP processing"""
        # Ensure correct shape and type
        if audio_data.ndim > 1:
            audio_data = audio_data.flatten()

        if audio_data.size == 0:
            return audio_data

        try:
            # Apply DSP processing if enabled
            if self.dsp_enabled and self.dsp_processor:
                audio_data = self.dsp_processor.process(audio_data)
            else:
                # Fallback to basic processing
                # Normalize to prevent clipping
                if np.max(np.abs(audio_data)) > 0:
                    audio_data = audio_data / np.max(np.abs(audio_data)) * 0.8

                # Apply simple noise gate to reduce background noise
                threshold = 0.01
                audio_data = np.where(np.abs(audio_data) < threshold, 0, audio_data)

        except Exception as e:
            logger.error(f"Error in DSP processing, using fallback: {e}")
            # Fallback to basic normalization
            if np.max(np.abs(audio_data)) > 0:
                audio_data = audio_data / np.max(np.abs(audio_data)) * 0.8

        return audio_data

    def set_dsp_config(self, config: Dict[str, Any]):
        """Update DSP configuration"""
        if self.dsp_processor:
            self.dsp_processor.update_config(config)
            logger.info("DSP configuration updated")

    def set_eq_gain(self, band_name: str, gain_db: float):
        """Set equalizer gain for specific band"""
        if self.dsp_processor:
            self.dsp_processor.set_eq_gain(band_name, gain_db)

    def enable_dsp(self):
        """Enable DSP processing"""
        self.dsp_enabled = True
        logger.info("DSP processing enabled")

    def disable_dsp(self):
        """Disable DSP processing"""
        self.dsp_enabled = False
        logger.info("DSP processing disabled")

    def get_dsp_stats(self) -> Dict[str, Any]:
        """Get DSP processing statistics"""
        if self.dsp_processor:
            return self.dsp_processor.get_stats()
        return {}

    async def cleanup(self):
        """Cleanup audio resources"""
        if self.output_stream:
            self.output_stream.stop_stream()
            self.output_stream.close()
            self.output_stream = None

        if self.pyaudio_instance:
            self.pyaudio_instance.terminate()
            self.pyaudio_instance = None


class AudioRecorder:
    """Records and saves transmission audio"""

    def __init__(self, recordings_dir: str = "recordings"):
        self.recordings_dir = recordings_dir
        self.ensure_recordings_dir()

    def ensure_recordings_dir(self):
        """Ensure recordings directory exists"""
        if not os.path.exists(self.recordings_dir):
            os.makedirs(self.recordings_dir)
            logger.info(f"Created recordings directory: {self.recordings_dir}")

    async def save_transmission(self, audio_data: np.ndarray, frequency: float,
                              timestamp: datetime, sample_rate: int = 48000,
                              metadata: Optional[Dict[str, Any]] = None) -> str:
        """Save transmission audio to file with metadata"""
        try:
            if audio_data.size == 0:
                logger.warning("No audio data to save")
                return ""

            # Get recording format from settings
            from .config import get_settings
            settings = get_settings()
            recording_format = getattr(settings, 'recording_format', 'wav').lower()
            mp3_bitrate = getattr(settings, 'mp3_bitrate', '192k')

            # Create filename with sanitization
            timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
            freq_mhz = frequency / 1e6
            filename_base = f"{timestamp_str}_{freq_mhz:.3f}MHz"
            filename_base = sanitize_filename(filename_base)  # Sanitize to prevent path traversal
            
            # Determine file extension and format
            if recording_format == 'mp3' and LAMEENC_AVAILABLE:
                audio_filename = f"{filename_base}.mp3"
                file_format = 'MP3'
            else:
                # Fallback to WAV if MP3 not available or format is wav
                if recording_format == 'mp3' and not LAMEENC_AVAILABLE:
                    logger.warning("MP3 format requested but lameenc not available, falling back to WAV")
                audio_filename = f"{filename_base}.wav"
                file_format = 'WAV'
            
            json_filename = f"{filename_base}.json"
            
            audio_filepath = os.path.join(self.recordings_dir, audio_filename)
            json_filepath = os.path.join(self.recordings_dir, json_filename)

            # Prepare audio data
            audio_data = self._prepare_for_saving(audio_data)
            duration = len(audio_data) / sample_rate

            # Save audio file based on format
            if file_format == 'MP3' and LAMEENC_AVAILABLE:
                # Convert numpy array directly to MP3 using lameenc (faster, no subprocess)
                # Convert to 16-bit integer
                audio_int16 = (audio_data * 32767).astype(np.int16)
                
                # Parse bitrate (e.g., "192k" -> 192)
                bitrate_value = int(mp3_bitrate.replace('k', ''))
                
                # Create MP3 encoder
                encoder = lameenc.Encoder()
                encoder.set_bit_rate(bitrate_value)
                encoder.set_in_sample_rate(sample_rate)
                encoder.set_channels(1)  # Mono
                encoder.set_quality(2)  # Quality: 0=best, 9=fastest (2 is good balance)
                
                # Encode audio data
                mp3_data = encoder.encode(audio_int16.tobytes())
                mp3_data += encoder.flush()  # Finalize encoding
                
                # Write MP3 file
                with open(audio_filepath, 'wb') as mp3_file:
                    mp3_file.write(mp3_data)
            else:
                # Save as WAV file
                with wave.open(audio_filepath, 'wb') as wav_file:
                    wav_file.setnchannels(1)  # Mono
                    wav_file.setsampwidth(2)  # 16-bit
                    wav_file.setframerate(sample_rate)

                    # Convert to 16-bit integer
                    audio_int16 = (audio_data * 32767).astype(np.int16)
                    wav_file.writeframes(audio_int16.tobytes())

            # Prepare comprehensive metadata
            recording_metadata = {
                'recording_info': {
                    'filename': audio_filename,
                    'filepath': audio_filepath,
                    'timestamp': timestamp.isoformat(),
                    'duration_seconds': round(duration, 3),
                    'sample_rate': sample_rate,
                    'channels': 1,
                    'bit_depth': 16,
                    'format': file_format,
                    'bitrate': mp3_bitrate if file_format == 'MP3' else None,
                    'file_size_bytes': os.path.getsize(audio_filepath) if os.path.exists(audio_filepath) else 0
                },
                'frequency_info': {
                    'frequency_hz': float(frequency),
                    'frequency_mhz': round(freq_mhz, 6),
                    'friendly_name': metadata.get('friendly_name', '') if metadata else '',
                    'description': metadata.get('description', '') if metadata else '',
                    'group': metadata.get('group', '') if metadata else '',
                    'tags': metadata.get('tags', '') if metadata else '',
                    'modulation': metadata.get('modulation', 'FM') if metadata else 'FM',
                    'priority': metadata.get('priority', 0) if metadata else 0
                },
                'signal_info': {
                    'signal_strength_dbm': metadata.get('signal_strength', 0.0) if metadata else 0.0,
                    'squelch_threshold_dbm': metadata.get('squelch_threshold', -50.0) if metadata else -50.0,
                    'peak_signal_strength_dbm': metadata.get('peak_signal_strength', 0.0) if metadata else 0.0
                },
                'audio_stats': {
                    'duration_seconds': round(duration, 3),
                    'sample_count': len(audio_data),
                    'max_amplitude': float(np.max(np.abs(audio_data))),
                    'rms_level': float(np.sqrt(np.mean(audio_data**2))),
                    'peak_level_db': round(20 * np.log10(np.max(np.abs(audio_data)) + 1e-10), 2)
                },
                'system_info': {
                    'application': 'sdr2zello',
                    'version': '1.0.0',
                    'recording_timestamp': datetime.now().isoformat()
                }
            }
            
            # Add any additional metadata passed in
            if metadata:
                if 'additional_info' in metadata:
                    recording_metadata['additional_info'] = metadata['additional_info']
                if 'notes' in metadata:
                    recording_metadata['notes'] = metadata['notes']

            # Save metadata as JSON
            with open(json_filepath, 'w', encoding='utf-8') as json_file:
                json.dump(recording_metadata, json_file, indent=2, ensure_ascii=False)

            # Save recording to database
            try:
                from .database import get_async_db, DatabaseManager
                async with get_async_db() as db:
                    # Check if recording already exists (avoid duplicates)
                    existing = await DatabaseManager.get_recording_by_filepath(db, audio_filepath)
                    if not existing:
                        recording_data = {
                            'filename': audio_filename,
                            'filepath': audio_filepath,
                            'file_size_bytes': recording_metadata['recording_info']['file_size_bytes'],
                            'format': file_format,
                            'bitrate': recording_metadata['recording_info'].get('bitrate'),
                            'timestamp': timestamp,
                            'duration_seconds': recording_metadata['recording_info']['duration_seconds'],
                            'sample_rate': recording_metadata['recording_info']['sample_rate'],
                            'channels': recording_metadata['recording_info']['channels'],
                            'bit_depth': recording_metadata['recording_info']['bit_depth'],
                            'frequency_hz': recording_metadata['frequency_info']['frequency_hz'],
                            'frequency_mhz': recording_metadata['frequency_info']['frequency_mhz'],
                            'friendly_name': recording_metadata['frequency_info'].get('friendly_name', ''),
                            'description': recording_metadata['frequency_info']['description'],
                            'group': recording_metadata['frequency_info']['group'],
                            'tags': recording_metadata['frequency_info']['tags'],
                            'modulation': recording_metadata['frequency_info']['modulation'],
                            'priority': recording_metadata['frequency_info']['priority'],
                            'signal_strength_dbm': recording_metadata['signal_info']['signal_strength_dbm'],
                            'peak_signal_strength_dbm': recording_metadata['signal_info']['peak_signal_strength_dbm'],
                            'squelch_threshold_dbm': recording_metadata['signal_info']['squelch_threshold_dbm'],
                            'max_amplitude': recording_metadata['audio_stats']['max_amplitude'],
                            'rms_level': recording_metadata['audio_stats']['rms_level'],
                            'peak_level_db': recording_metadata['audio_stats']['peak_level_db'],
                            'notes': recording_metadata.get('notes', '')
                        }
                        await DatabaseManager.create_recording(db, recording_data)
                        logger.debug(f"Saved recording to database: {audio_filename}")
            except Exception as e:
                logger.warning(f"Failed to save recording to database: {e}")

            logger.info(f"Saved transmission audio: {audio_filepath} ({file_format}) with metadata: {json_filepath}")
            return audio_filepath

        except Exception as e:
            logger.error(f"Error saving transmission audio: {e}")
            return ""

    def _prepare_for_saving(self, audio_data: np.ndarray) -> np.ndarray:
        """Prepare audio data for saving"""
        # Flatten if multi-dimensional
        if audio_data.ndim > 1:
            audio_data = audio_data.flatten()

        # Normalize
        if np.max(np.abs(audio_data)) > 0:
            audio_data = audio_data / np.max(np.abs(audio_data)) * 0.9

        # Apply simple high-pass filter to remove DC component
        if len(audio_data) > 1:
            audio_data = np.diff(np.concatenate(([0], audio_data)))

        return audio_data


class AudioManager:
    """Main audio management class with DSP support"""

    def __init__(self, dsp_config: Optional[Dict] = None):
        self.settings = get_settings()

        # Get DSP configuration from settings or use provided config
        if dsp_config is None:
            self.dsp_config = self.settings.get_dsp_config()
        else:
            # Merge provided config with settings
            base_config = self.settings.get_dsp_config()
            base_config.update(dsp_config)
            self.dsp_config = base_config

        # Get initial equalizer settings
        self.eq_config = self.settings.get_eq_config()

        self.virtual_device = VirtualAudioDevice(
            sample_rate=self.settings.audio_sample_rate,
            channels=self.settings.audio_channels,
            dsp_config=self.dsp_config
        )
        self.recorder = AudioRecorder()
        self.audio_buffer = AudioBuffer(sample_rate=self.settings.audio_sample_rate)

        self.transmission_callback: Optional[Callable] = None
        self.audio_enabled = True
        
        # Track transmission metadata
        self.current_transmission_metadata: Optional[Dict[str, Any]] = None
        self.peak_signal_strength: float = -100.0

        logger.info(f"AudioManager initialized with DSP configuration: {self.dsp_config}")

    async def initialize(self):
        """Initialize audio manager"""
        try:
            await self.virtual_device.initialize()

            # Apply initial equalizer settings
            await self._apply_eq_settings()

            logger.info("Audio manager initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing audio manager: {e}")
            raise

    async def _apply_eq_settings(self):
        """Apply equalizer settings to DSP processor"""
        if self.virtual_device and self.virtual_device.dsp_processor:
            for band_name, gain in self.eq_config.items():
                if abs(gain) > 0.1:  # Only apply non-zero gains
                    self.virtual_device.set_eq_gain(band_name, gain)
            logger.debug("Applied equalizer settings from configuration")

    def set_transmission_callback(self, callback: Callable):
        """Set callback for completed transmissions"""
        self.transmission_callback = callback

    async def handle_transmission_start(self, frequency: float, metadata: Optional[Dict[str, Any]] = None):
        """Handle start of transmission"""
        logger.debug(f"Starting audio recording for {frequency / 1e6:.3f} MHz")
        self.audio_buffer.start_recording()
        
        # Store transmission metadata
        self.current_transmission_metadata = metadata or {}
        self.current_transmission_metadata['frequency'] = frequency
        self.peak_signal_strength = self.current_transmission_metadata.get('signal_strength', -100.0)
        
        # Reset Zello status tracking
        self.current_zello_status = {
            'sent': False,
            'success': False,
            'error': '',
            'audio_enabled': self.audio_enabled
        }

    async def handle_transmission_audio(self, audio_data: np.ndarray):
        """Handle incoming transmission audio"""
        if not self.audio_enabled or audio_data.size == 0:
            self.current_zello_status['error'] = "Audio disabled or empty data"
            return

        # Add to recording buffer
        self.audio_buffer.add_samples(audio_data)

        # Route to Zello via virtual audio device
        if self.virtual_device:
            success, error = await self.virtual_device.play_audio(audio_data)
            self.current_zello_status['sent'] = True
            if success:
                self.current_zello_status['success'] = True
                self.current_zello_status['error'] = ''
            else:
                self.current_zello_status['success'] = False
                self.current_zello_status['error'] = error
        else:
            self.current_zello_status['sent'] = False
            self.current_zello_status['success'] = False
            self.current_zello_status['error'] = "Virtual audio device not initialized"

    async def handle_transmission_end(self, frequency: float, timestamp: datetime, 
                                     metadata: Optional[Dict[str, Any]] = None):
        """Handle end of transmission"""
        logger.debug(f"Ending audio recording for {frequency / 1e6:.3f} MHz")

        # Stop recording and get audio data
        audio_data, duration = self.audio_buffer.stop_recording()

        if audio_data.size > 0:
            # Prepare comprehensive metadata
            recording_metadata = self.current_transmission_metadata.copy() if self.current_transmission_metadata else {}
            
            # Merge with any additional metadata passed
            if metadata:
                recording_metadata.update(metadata)
            
            # Ensure frequency is set
            recording_metadata['frequency'] = frequency
            recording_metadata['timestamp'] = timestamp
            recording_metadata['duration'] = duration
            
            # Add signal strength info
            if 'signal_strength' not in recording_metadata:
                recording_metadata['signal_strength'] = self.peak_signal_strength
            recording_metadata['peak_signal_strength'] = self.peak_signal_strength
            recording_metadata['squelch_threshold'] = self.settings.squelch_threshold
            
            # Add modulation if not present
            if 'modulation' not in recording_metadata:
                # Determine modulation from frequency band
                if 118e6 <= frequency <= 137e6:
                    recording_metadata['modulation'] = 'AM'
                else:
                    recording_metadata['modulation'] = 'FM'
            
            # Save recording with metadata
            filepath = await self.recorder.save_transmission(
                audio_data, frequency, timestamp, self.settings.audio_sample_rate,
                metadata=recording_metadata
            )

            # Notify callback if set
            if self.transmission_callback:
                await self.transmission_callback({
                    'frequency': frequency,
                    'duration': duration,
                    'timestamp': timestamp,
                    'audio_file': filepath,
                    'metadata': recording_metadata
                })

            logger.info(f"Completed transmission recording: {duration:.2f}s on {frequency / 1e6:.3f} MHz")
            
            # Reset metadata tracking
            self.current_transmission_metadata = None
            self.peak_signal_strength = -100.0

    def enable_audio(self):
        """Enable audio output"""
        self.audio_enabled = True
        logger.info("Audio output enabled")

    def disable_audio(self):
        """Disable audio output"""
        self.audio_enabled = False
        logger.info("Audio output disabled")

    def get_status(self) -> dict:
        """Get audio system status"""
        status = {
            'audio_enabled': self.audio_enabled,
            'recording': self.audio_buffer.is_recording,
            'device_initialized': self.virtual_device.pyaudio_instance is not None,
            'sample_rate': self.settings.audio_sample_rate,
            'channels': self.settings.audio_channels,
            'dsp_enabled': self.virtual_device.dsp_enabled if self.virtual_device else False,
            'dsp_config': dict(self.dsp_config)  # More efficient than .copy()
        }

        # Add DSP statistics if available
        if self.virtual_device:
            dsp_stats = self.virtual_device.get_dsp_stats()
            status['dsp_stats'] = dsp_stats

        return status

    # DSP Control Methods
    def update_dsp_config(self, config: Dict[str, Any]):
        """Update DSP configuration"""
        self.dsp_config.update(config)
        if self.virtual_device:
            self.virtual_device.set_dsp_config(config)
        logger.info(f"DSP configuration updated: {config}")

    def set_eq_gain(self, band_name: str, gain_db: float):
        """Set equalizer gain for specific band"""
        if self.virtual_device:
            self.virtual_device.set_eq_gain(band_name, gain_db)
        logger.debug(f"EQ band {band_name} set to {gain_db} dB")

    def enable_dsp_module(self, module_name: str):
        """Enable specific DSP module"""
        config = {f'enable_{module_name}': True}
        self.update_dsp_config(config)

    def disable_dsp_module(self, module_name: str):
        """Disable specific DSP module"""
        config = {f'enable_{module_name}': False}
        self.update_dsp_config(config)

    def set_noise_gate_threshold(self, threshold_db: float):
        """Set noise gate threshold in dB"""
        config = {'noise_gate_threshold': threshold_db}
        self.update_dsp_config(config)

    def set_agc_target_level(self, target_db: float):
        """Set AGC target level in dB"""
        config = {'agc_target_level': target_db}
        self.update_dsp_config(config)

    def set_noise_reduction_strength(self, alpha: float):
        """Set noise reduction strength (alpha parameter)"""
        config = {'noise_reduction_alpha': alpha}
        self.update_dsp_config(config)

    def enable_dsp_processing(self):
        """Enable DSP processing"""
        if self.virtual_device:
            self.virtual_device.enable_dsp()

    def disable_dsp_processing(self):
        """Disable DSP processing"""
        if self.virtual_device:
            self.virtual_device.disable_dsp()

    def get_dsp_config(self) -> Dict[str, Any]:
        """Get current DSP configuration"""
        return dict(self.dsp_config)  # More efficient than .copy()

    def reset_dsp_stats(self):
        """Reset DSP processing statistics"""
        if self.virtual_device and self.virtual_device.dsp_processor:
            self.virtual_device.dsp_processor.reset_stats()

    def get_eq_bands(self) -> List[str]:
        """Get list of available EQ bands"""
        if self.virtual_device and self.virtual_device.dsp_processor:
            return list(self.virtual_device.dsp_processor.equalizer.bands.keys())
        return []

    async def cleanup(self):
        """Cleanup audio resources"""
        if self.virtual_device:
            await self.virtual_device.cleanup()
        logger.info("Audio manager cleaned up")