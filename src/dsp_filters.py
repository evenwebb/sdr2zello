"""
Digital Signal Processing (DSP) Module for sdr2zello
Provides noise filtering, audio enhancement, and signal processing capabilities
"""

import numpy as np
import logging
from typing import Tuple, Optional, Dict, Any
from scipy import signal
from scipy.signal import butter, filtfilt
from collections import deque
import threading
import time

logger = logging.getLogger(__name__)


class NoiseGate:
    """Simple noise gate implementation"""

    def __init__(self, threshold: float = -40.0, attack_time: float = 0.001,
                 release_time: float = 0.1, sample_rate: int = 48000):
        self.threshold = threshold  # dB
        self.attack_time = attack_time  # seconds
        self.release_time = release_time  # seconds
        self.sample_rate = sample_rate

        # Calculate attack and release coefficients
        self.attack_coeff = np.exp(-1.0 / (attack_time * sample_rate))
        self.release_coeff = np.exp(-1.0 / (release_time * sample_rate))

        self.envelope = 0.0
        self.gate_state = False

    def process(self, audio_data: np.ndarray) -> np.ndarray:
        """Apply noise gate to audio data (vectorized for performance)"""
        if len(audio_data) == 0:
            return audio_data
        
        # Vectorized envelope calculation
        abs_samples = np.abs(audio_data)
        
        # Calculate envelope using vectorized operations
        # For attack: envelope = abs_sample + attack_coeff * (envelope - abs_sample)
        # For release: envelope = abs_sample + release_coeff * (envelope - abs_sample)
        envelope_array = np.zeros_like(abs_samples)
        envelope_array[0] = abs_samples[0] + self.attack_coeff * (self.envelope - abs_samples[0]) if abs_samples[0] > self.envelope else abs_samples[0] + self.release_coeff * (self.envelope - abs_samples[0])
        
        # Vectorized envelope tracking
        for i in range(1, len(abs_samples)):
            if abs_samples[i] > envelope_array[i-1]:
                envelope_array[i] = abs_samples[i] + self.attack_coeff * (envelope_array[i-1] - abs_samples[i])
            else:
                envelope_array[i] = abs_samples[i] + self.release_coeff * (envelope_array[i-1] - abs_samples[i])
        
        # Update state for next call
        self.envelope = envelope_array[-1]
        
        # Convert to dB (vectorized)
        envelope_db = 20 * np.log10(envelope_array + 1e-10)
        
        # Apply gate with hysteresis (vectorized)
        threshold_low = self.threshold - 6  # Hysteresis
        gate_mask = np.zeros_like(envelope_db, dtype=bool)
        
        # State machine for gate (vectorized where possible)
        current_state = self.gate_state
        for i in range(len(envelope_db)):
            if envelope_db[i] > self.threshold:
                current_state = True
            elif envelope_db[i] < threshold_low:
                current_state = False
            gate_mask[i] = current_state
        
        self.gate_state = current_state
        
        # Apply gate (vectorized)
        output = np.where(gate_mask, audio_data, 0.0)
        
        return output


class AutomaticGainControl:
    """Automatic Gain Control (AGC) implementation"""

    def __init__(self, target_level: float = -20.0, attack_time: float = 0.003,
                 release_time: float = 0.1, max_gain: float = 40.0,
                 sample_rate: int = 48000):
        self.target_level = target_level  # dB
        self.attack_time = attack_time
        self.release_time = release_time
        self.max_gain = max_gain  # dB
        self.sample_rate = sample_rate

        # Calculate coefficients
        self.attack_coeff = np.exp(-1.0 / (attack_time * sample_rate))
        self.release_coeff = np.exp(-1.0 / (release_time * sample_rate))

        self.envelope = 0.0
        self.gain = 1.0

    def process(self, audio_data: np.ndarray) -> np.ndarray:
        """Apply AGC to audio data (vectorized for performance)"""
        if len(audio_data) == 0:
            return audio_data
        
        # Vectorized envelope calculation
        abs_samples = np.abs(audio_data)
        
        # Calculate envelope using vectorized operations
        envelope_array = np.zeros_like(abs_samples)
        envelope_array[0] = abs_samples[0] + self.attack_coeff * (self.envelope - abs_samples[0]) if abs_samples[0] > self.envelope else abs_samples[0] + self.release_coeff * (self.envelope - abs_samples[0])
        
        # Vectorized envelope tracking
        for i in range(1, len(abs_samples)):
            if abs_samples[i] > envelope_array[i-1]:
                envelope_array[i] = abs_samples[i] + self.attack_coeff * (envelope_array[i-1] - abs_samples[i])
            else:
                envelope_array[i] = abs_samples[i] + self.release_coeff * (envelope_array[i-1] - abs_samples[i])
        
        # Update state for next call
        self.envelope = envelope_array[-1]
        
        # Calculate required gain (vectorized)
        envelope_db = np.where(envelope_array > 1e-10, 20 * np.log10(envelope_array), -100.0)
        required_gain_db = self.target_level - envelope_db
        required_gain_db = np.clip(required_gain_db, -60, self.max_gain)
        target_gain_array = np.power(10, required_gain_db / 20)
        
        # Smooth gain changes (vectorized where possible)
        gain_array = np.zeros_like(target_gain_array)
        current_gain = self.gain
        
        for i in range(len(target_gain_array)):
            target_gain = target_gain_array[i]
            if target_gain > current_gain:
                current_gain = target_gain + self.attack_coeff * (current_gain - target_gain)
            else:
                current_gain = target_gain + self.release_coeff * (current_gain - target_gain)
            gain_array[i] = current_gain
        
        self.gain = gain_array[-1]
        
        # Apply gain (fully vectorized)
        output = audio_data * gain_array
        
        return output


class SpectralNoiseReduction:
    """Spectral subtraction noise reduction"""

    def __init__(self, sample_rate: int = 48000, frame_size: int = 1024,
                 overlap: float = 0.5, alpha: float = 2.0):
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.hop_size = int(frame_size * (1 - overlap))
        self.alpha = alpha  # Over-subtraction factor

        self.noise_estimate = None
        self.frame_count = 0
        self.window = np.hanning(frame_size)

        # Buffer for overlap-add
        self.input_buffer = deque(maxlen=frame_size * 2)
        self.output_buffer = np.zeros(frame_size * 2)

    def estimate_noise(self, audio_frame: np.ndarray) -> np.ndarray:
        """Estimate noise spectrum from audio frame"""
        windowed = audio_frame * self.window
        spectrum = np.fft.rfft(windowed)
        magnitude = np.abs(spectrum)

        if self.noise_estimate is None:
            self.noise_estimate = magnitude
        else:
            # Update noise estimate (assuming first few frames are noise)
            if self.frame_count < 10:
                self.noise_estimate = 0.95 * self.noise_estimate + 0.05 * magnitude

        return magnitude

    def process_frame(self, audio_frame: np.ndarray) -> np.ndarray:
        """Process single audio frame"""
        if len(audio_frame) != self.frame_size:
            return audio_frame

        windowed = audio_frame * self.window
        spectrum = np.fft.rfft(windowed)
        magnitude = np.abs(spectrum)
        phase = np.angle(spectrum)

        # Update noise estimate if needed
        if self.noise_estimate is None or self.frame_count < 10:
            self.estimate_noise(audio_frame)

        # Spectral subtraction
        if self.noise_estimate is not None:
            # Calculate gain function
            snr = magnitude / (self.noise_estimate + 1e-10)
            gain = 1 - self.alpha / snr
            gain = np.maximum(gain, 0.1)  # Floor to prevent artifacts

            # Apply gain
            enhanced_magnitude = magnitude * gain
            enhanced_spectrum = enhanced_magnitude * np.exp(1j * phase)

            # Convert back to time domain
            enhanced_frame = np.fft.irfft(enhanced_spectrum)
            enhanced_frame = enhanced_frame[:self.frame_size] * self.window
        else:
            enhanced_frame = windowed

        self.frame_count += 1
        return enhanced_frame

    def process(self, audio_data: np.ndarray) -> np.ndarray:
        """Process audio data with spectral noise reduction"""
        # Add to input buffer
        self.input_buffer.extend(audio_data)

        output = np.zeros_like(audio_data)
        output_idx = 0

        # Process frames
        while len(self.input_buffer) >= self.frame_size:
            # Extract frame
            frame = np.array(list(self.input_buffer)[:self.frame_size])

            # Process frame
            enhanced_frame = self.process_frame(frame)

            # Overlap-add
            self.output_buffer[:self.frame_size] += enhanced_frame

            # Copy output
            samples_to_copy = min(self.hop_size, len(audio_data) - output_idx)
            output[output_idx:output_idx + samples_to_copy] = self.output_buffer[:samples_to_copy]
            output_idx += samples_to_copy

            # Shift buffers
            for _ in range(self.hop_size):
                if self.input_buffer:
                    self.input_buffer.popleft()

            self.output_buffer[:self.frame_size] = self.output_buffer[self.hop_size:self.hop_size + self.frame_size]
            self.output_buffer[self.frame_size:] = 0

            if output_idx >= len(audio_data):
                break

        return output


class AudioEqualizer:
    """Multi-band audio equalizer"""

    def __init__(self, sample_rate: int = 48000):
        self.sample_rate = sample_rate
        self.bands = {}
        self._setup_default_bands()

    def _setup_default_bands(self):
        """Setup default EQ bands"""
        # Standard frequency bands
        band_configs = [
            {'name': 'sub_bass', 'freq': 60, 'gain': 0.0, 'q': 1.0, 'filter_type': 'highpass'},
            {'name': 'bass', 'freq': 200, 'gain': 0.0, 'q': 0.7, 'filter_type': 'bell'},
            {'name': 'low_mid', 'freq': 500, 'gain': 0.0, 'q': 0.7, 'filter_type': 'bell'},
            {'name': 'mid', 'freq': 1000, 'gain': 0.0, 'q': 0.7, 'filter_type': 'bell'},
            {'name': 'high_mid', 'freq': 2000, 'gain': 0.0, 'q': 0.7, 'filter_type': 'bell'},
            {'name': 'presence', 'freq': 4000, 'gain': 0.0, 'q': 0.7, 'filter_type': 'bell'},
            {'name': 'brilliance', 'freq': 8000, 'gain': 0.0, 'q': 1.0, 'filter_type': 'bell'},
            {'name': 'air', 'freq': 12000, 'gain': 0.0, 'q': 1.0, 'filter_type': 'lowpass'},
        ]

        for config in band_configs:
            self.add_band(**config)

    def add_band(self, name: str, freq: float, gain: float = 0.0,
                 q: float = 1.0, filter_type: str = 'bell'):
        """Add EQ band"""
        self.bands[name] = {
            'freq': freq,
            'gain': gain,
            'q': q,
            'type': filter_type,
            'filter': None
        }
        self._update_filter(name)

    def set_gain(self, band_name: str, gain_db: float):
        """Set gain for specific band"""
        if band_name in self.bands:
            self.bands[band_name]['gain'] = gain_db
            self._update_filter(band_name)

    def _update_filter(self, band_name: str):
        """Update filter coefficients for band"""
        band = self.bands[band_name]
        freq = band['freq']
        gain = band['gain']
        q = band['q']
        filter_type = band['type']

        nyquist = self.sample_rate / 2
        normalized_freq = freq / nyquist

        if filter_type == 'bell':
            # Peaking EQ
            if abs(gain) > 0.1:
                if gain > 0:
                    # Boost
                    b, a = signal.iirpeak(normalized_freq, Q=q)
                    # Apply gain
                    gain_linear = 10 ** (gain / 20)
                    b = b * gain_linear
                else:
                    # Cut
                    b, a = signal.iirnotch(normalized_freq, Q=q)
            else:
                # No change
                b, a = [1], [1]
        elif filter_type == 'highpass':
            order = 2
            b, a = butter(order, normalized_freq, btype='high')
        elif filter_type == 'lowpass':
            order = 2
            b, a = butter(order, normalized_freq, btype='low')
        else:
            b, a = [1], [1]

        band['filter'] = (b, a)

    def process(self, audio_data: np.ndarray) -> np.ndarray:
        """Apply equalizer to audio data (optimized to avoid unnecessary copies)"""
        # Only copy if we need to modify (filters may modify in-place)
        output = audio_data
        needs_copy = any(
            band['filter'] is not None and abs(band['gain']) > 0.1 
            for band in self.bands.values()
        )
        
        if needs_copy:
            output = audio_data.copy()

        for band_name, band in self.bands.items():
            if band['filter'] is not None and abs(band['gain']) > 0.1:
                b, a = band['filter']
                try:
                    output = filtfilt(b, a, output)
                except Exception as e:
                    logger.warning(f"EQ filter error for band {band_name}: {e}")

        return output


class DSPProcessor:
    """Main DSP processor that combines all filters and enhancements"""

    def __init__(self, sample_rate: int = 48000, config: Optional[Dict] = None):
        self.sample_rate = sample_rate
        self.config = config or {}

        # Initialize processing modules
        self.noise_gate = NoiseGate(
            threshold=self.config.get('noise_gate_threshold', -40.0),
            sample_rate=sample_rate
        )

        self.agc = AutomaticGainControl(
            target_level=self.config.get('agc_target_level', -20.0),
            max_gain=self.config.get('agc_max_gain', 40.0),
            sample_rate=sample_rate
        )

        self.noise_reduction = SpectralNoiseReduction(
            sample_rate=sample_rate,
            alpha=self.config.get('noise_reduction_alpha', 2.0)
        )

        self.equalizer = AudioEqualizer(sample_rate=sample_rate)

        # Processing chain configuration
        self.enabled_modules = {
            'noise_gate': self.config.get('enable_noise_gate', False),
            'noise_reduction': self.config.get('enable_noise_reduction', False),
            'equalizer': self.config.get('enable_equalizer', False),
            'agc': self.config.get('enable_agc', True)
        }

        # Statistics
        self.stats = {
            'frames_processed': 0,
            'total_samples': 0,
            'average_level': 0.0,
            'peak_level': 0.0
        }

        self._lock = threading.Lock()

        logger.info(f"DSP Processor initialized - Sample Rate: {sample_rate}Hz")
        logger.info(f"Enabled modules: {[k for k, v in self.enabled_modules.items() if v]}")

    def update_config(self, config: Dict[str, Any]):
        """Update DSP configuration"""
        with self._lock:
            self.config.update(config)

            # Update noise gate
            if 'noise_gate_threshold' in config:
                self.noise_gate.threshold = config['noise_gate_threshold']

            # Update AGC
            if 'agc_target_level' in config:
                self.agc.target_level = config['agc_target_level']
            if 'agc_max_gain' in config:
                self.agc.max_gain = config['agc_max_gain']

            # Update noise reduction
            if 'noise_reduction_alpha' in config:
                self.noise_reduction.alpha = config['noise_reduction_alpha']

            # Update enabled modules
            for module in self.enabled_modules:
                if f'enable_{module}' in config:
                    self.enabled_modules[module] = config[f'enable_{module}']

            logger.info("DSP configuration updated")

    def set_eq_gain(self, band_name: str, gain_db: float):
        """Set equalizer gain for specific band"""
        with self._lock:
            self.equalizer.set_gain(band_name, gain_db)

    def process(self, audio_data: np.ndarray) -> np.ndarray:
        """Process audio data through DSP chain"""
        if len(audio_data) == 0:
            return audio_data

        with self._lock:
            try:
                # Convert to float if needed (in-place if possible)
                if audio_data.dtype != np.float32:
                    audio_data = audio_data.astype(np.float32, copy=False)

                # Normalize input (in-place if possible)
                input_max = np.max(np.abs(audio_data))
                if input_max > 1.0:
                    audio_data = np.divide(audio_data, input_max, out=audio_data)

                # Only copy if processing will modify data (optimization)
                needs_processing = any([
                    self.enabled_modules['noise_gate'],
                    self.enabled_modules['noise_reduction'],
                    self.enabled_modules['equalizer'],
                    self.enabled_modules['agc']
                ])
                
                # Use copy only if processing will modify
                output = audio_data.copy() if needs_processing else audio_data

                # Processing chain
                if self.enabled_modules['noise_gate']:
                    output = self.noise_gate.process(output)

                if self.enabled_modules['noise_reduction']:
                    output = self.noise_reduction.process(output)

                if self.enabled_modules['equalizer']:
                    output = self.equalizer.process(output)

                if self.enabled_modules['agc']:
                    output = self.agc.process(output)

                # Update statistics
                self._update_stats(output)

                # Prevent clipping (in-place division)
                output_max = np.max(np.abs(output))
                if output_max > 1.0:
                    output = np.divide(output, output_max, out=output)

                return output

            except Exception as e:
                logger.error(f"DSP processing error: {e}")
                return audio_data  # Return original on error

    def _update_stats(self, audio_data: np.ndarray):
        """Update processing statistics"""
        self.stats['frames_processed'] += 1
        self.stats['total_samples'] += len(audio_data)

        # Calculate levels
        rms = np.sqrt(np.mean(audio_data ** 2))
        peak = np.max(np.abs(audio_data))

        # Convert to dB
        rms_db = 20 * np.log10(rms + 1e-10)
        peak_db = 20 * np.log10(peak + 1e-10)

        # Update running averages
        alpha = 0.01  # Smoothing factor
        self.stats['average_level'] = (1 - alpha) * self.stats['average_level'] + alpha * rms_db
        self.stats['peak_level'] = max(self.stats['peak_level'], peak_db)

    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        with self._lock:
            return dict(self.stats)  # More efficient than .copy()

    def reset_stats(self):
        """Reset processing statistics"""
        with self._lock:
            self.stats = {
                'frames_processed': 0,
                'total_samples': 0,
                'average_level': 0.0,
                'peak_level': 0.0
            }

    def get_config(self) -> Dict[str, Any]:
        """Get current DSP configuration"""
        with self._lock:
            config = dict(self.config)  # More efficient than .copy()
            config['enabled_modules'] = dict(self.enabled_modules)
            return config


# Factory function for creating DSP processor
def create_dsp_processor(sample_rate: int = 48000, config: Optional[Dict] = None) -> DSPProcessor:
    """Create and configure DSP processor"""
    return DSPProcessor(sample_rate=sample_rate, config=config)