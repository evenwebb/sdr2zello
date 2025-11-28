"""
RTL-SDR Management and Frequency Scanning
"""

import asyncio
import numpy as np
import logging
import random
from typing import List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
import threading
import time

try:
    from rtlsdr import RtlSdr
except ImportError:
    RtlSdr = None
    logging.warning("pyrtlsdr not installed - running in simulation mode")

from .config import get_settings
from .models import Frequency, TransmissionLog

logger = logging.getLogger(__name__)


@dataclass
class TransmissionEvent:
    """Represents a detected transmission"""
    frequency: float
    signal_strength: float
    timestamp: datetime
    audio_data: Optional[np.ndarray] = None
    duration: float = 0.0


class SignalProcessor:
    """Signal processing utilities for transmission detection"""

    @staticmethod
    def calculate_power(samples: np.ndarray) -> float:
        """Calculate signal power in dBm"""
        if len(samples) == 0:
            return -100.0

        # Calculate power spectral density
        power = np.mean(np.abs(samples) ** 2)
        if power <= 0:
            return -100.0

        # Convert to dBm (approximate)
        power_dbm = 10 * np.log10(power) - 30
        return power_dbm

    @staticmethod
    def detect_transmission(samples: np.ndarray, threshold: float) -> bool:
        """Detect if samples contain an active transmission"""
        power = SignalProcessor.calculate_power(samples)
        return power > threshold

    @staticmethod
    def demodulate_fm(samples: np.ndarray) -> np.ndarray:
        """Simple FM demodulation"""
        if len(samples) < 2:
            return np.array([])

        # Calculate phase differences
        phase = np.unwrap(np.angle(samples))
        demod = np.diff(phase)

        # Normalize and convert to audio range
        if len(demod) > 0:
            demod = demod / np.max(np.abs(demod)) if np.max(np.abs(demod)) > 0 else demod
            demod = demod * 0.5  # Scale to reasonable audio level

        return demod

    @staticmethod
    def demodulate_am(samples: np.ndarray) -> np.ndarray:
        """Simple AM demodulation"""
        if len(samples) == 0:
            return np.array([])

        # Calculate magnitude and remove DC component
        demod = np.abs(samples)
        if len(demod) > 0:
            demod = demod - np.mean(demod)
            # Normalize
            if np.max(np.abs(demod)) > 0:
                demod = demod / np.max(np.abs(demod)) * 0.5

        return demod


class SDRManager:
    """Manages RTL-SDR device and frequency scanning"""

    def __init__(self):
        self.settings = get_settings()
        self.sdr_device: Optional[RtlSdr] = None
        self.is_scanning = False
        self.scan_task: Optional[asyncio.Task] = None
        self.current_frequency = 0.0
        self.scan_list: List[Frequency] = []
        self.transmission_callback: Optional[Callable] = None
        self.signal_strength_callback: Optional[Callable] = None

        # Scanning state
        self.scan_index = 0
        self.dwel_time = 0.0
        self.last_transmission_time = 0.0
        
        # Smart scanning state
        self.frequency_activity = {}  # Track activity per frequency
        self.frequency_last_signal = {}  # Track last signal strength
        self.quiet_skip_count = {}  # Count consecutive quiet scans
        self.smart_scanning_enabled = True
        self.adaptive_delay_enabled = True
        self.min_scan_delay = 0.05  # Minimum delay between scans
        self.max_scan_delay = 0.5  # Maximum delay between scans
        self.quiet_threshold = 3  # Skip frequency after N quiet scans
        
        # Priority-based scanning state
        self.priority_scanning_enabled = self.settings.priority_scanning_enabled
        self.priority_scan_queue = []  # Queue for priority-based scanning
        self.frequency_scan_count = {}  # Track how many times each frequency has been scanned
        self.priority_weights = {}  # Pre-calculated weights for each frequency

    async def initialize(self):
        """Initialize SDR device"""
        try:
            if RtlSdr is None:
                logger.warning("Running in simulation mode - no RTL-SDR available")
                self.sdr_device = None
                return

            self.sdr_device = RtlSdr(device_index=self.settings.sdr_device_index)
            self.sdr_device.sample_rate = self.settings.sdr_sample_rate
            self.sdr_device.gain = self.settings.sdr_gain

            # Load default frequencies
            await self._load_default_frequencies()

            logger.info(f"RTL-SDR initialized - Sample Rate: {self.settings.sdr_sample_rate}")
            logger.info(f"Gain: {self.settings.sdr_gain}, Device Index: {self.settings.sdr_device_index}")

        except Exception as e:
            logger.error(f"Failed to initialize RTL-SDR: {e}")
            self.sdr_device = None

    async def _load_default_frequencies(self):
        """Load default frequency list"""
        self.scan_list = []
        for i, freq in enumerate(self.settings.default_frequencies):
            # Determine modulation based on frequency band
            if 118e6 <= freq <= 137e6:  # Aviation band
                modulation = "AM"
                description = "Aviation"
            elif 144e6 <= freq <= 148e6 or 420e6 <= freq <= 450e6:  # Ham bands
                modulation = "FM"
                description = "Amateur Radio"
            else:
                modulation = "FM"
                description = "General"

            frequency = Frequency(
                id=i + 1,
                frequency=freq,
                modulation=modulation,
                description=description,
                enabled=True
            )
            self.scan_list.append(frequency)

        logger.info(f"Loaded {len(self.scan_list)} default frequencies")

    def set_transmission_callback(self, callback: Callable):
        """Set callback for transmission events"""
        self.transmission_callback = callback

    def set_signal_strength_callback(self, callback: Callable):
        """Set callback for signal strength updates"""
        self.signal_strength_callback = callback

    async def start_scanning(self):
        """Start frequency scanning"""
        if self.is_scanning:
            logger.warning("Scanning already in progress")
            return

        if not self.scan_list:
            logger.error("No frequencies to scan")
            return

        self.is_scanning = True
        self.scan_index = 0
        self.scan_task = asyncio.create_task(self._scan_loop())
        logger.info("Started frequency scanning")

    async def stop_scanning(self):
        """Stop frequency scanning"""
        if not self.is_scanning:
            return

        self.is_scanning = False
        if self.scan_task:
            self.scan_task.cancel()
            try:
                await self.scan_task
            except asyncio.CancelledError:
                pass

        logger.info("Stopped frequency scanning")

    async def _scan_loop(self):
        """Main scanning loop with smart scanning and priority-based algorithms"""
        try:
            # Initialize priority scanning if enabled
            if self.priority_scanning_enabled:
                self._initialize_priority_scanning()
            
            while self.is_scanning and self.scan_list:
                # Get next enabled frequency using smart selection
                enabled_frequencies = self._get_smart_frequency_list()
                if not enabled_frequencies:
                    await asyncio.sleep(1.0)
                    continue

                # Select frequency using priority-based or smart selection
                if self.priority_scanning_enabled:
                    frequency = self._select_priority_based_frequency(enabled_frequencies)
                else:
                    frequency = self._select_next_frequency(enabled_frequencies)
                
                self.current_frequency = frequency.frequency

                # Tune to frequency
                await self._tune_to_frequency(frequency)

                # Collect samples and check for transmission
                signal_strength = await self._check_for_transmission(frequency)

                # Update scanning state
                self._update_scanning_state(frequency, signal_strength)
                if self.priority_scanning_enabled:
                    self._update_priority_scanning_state(frequency)

                # Calculate adaptive delay
                scan_delay = self._calculate_adaptive_delay(frequency, signal_strength)
                await asyncio.sleep(scan_delay)

        except Exception as e:
            logger.error(f"Error in scan loop: {e}")
        finally:
            self.is_scanning = False

    def _get_smart_frequency_list(self) -> List[Frequency]:
        """Get list of frequencies to scan, excluding quiet ones if smart scanning is enabled"""
        enabled_frequencies = [f for f in self.scan_list if f.enabled]
        
        if not self.smart_scanning_enabled:
            return enabled_frequencies
        
        # Filter out frequencies that have been quiet for too long
        active_frequencies = []
        for freq in enabled_frequencies:
            freq_key = freq.frequency
            skip_count = self.quiet_skip_count.get(freq_key, 0)
            
            # Always include high priority frequencies
            if freq.priority >= 50:
                active_frequencies.append(freq)
            # Include others if not too quiet
            elif skip_count < self.quiet_threshold:
                active_frequencies.append(freq)
        
        return active_frequencies if active_frequencies else enabled_frequencies

    def _select_next_frequency(self, frequencies: List[Frequency]) -> Frequency:
        """Select next frequency using priority-weighted selection"""
        if not frequencies:
            return self.scan_list[0] if self.scan_list else None
        
        # Priority-based selection: higher priority = more likely to be selected
        if self.smart_scanning_enabled:
            # Calculate weights based on priority and recent activity
            weights = []
            for freq in frequencies:
                weight = max(1, freq.priority)  # Base weight from priority
                
                # Boost weight for recently active frequencies
                freq_key = freq.frequency
                if freq_key in self.frequency_activity:
                    activity = self.frequency_activity[freq_key]
                    weight += activity * 10  # Boost for activity
                
                weights.append(weight)
            
            # Weighted random selection
            return random.choices(frequencies, weights=weights, k=1)[0]
        else:
            # Round-robin selection
            self.scan_index = (self.scan_index + 1) % len(frequencies)
            return frequencies[self.scan_index % len(frequencies)]

    def _update_scanning_state(self, frequency: Frequency, signal_strength: float):
        """Update smart scanning state based on scan results"""
        freq_key = frequency.frequency
        
        # Update signal strength tracking
        self.frequency_last_signal[freq_key] = signal_strength
        
        # Check if transmission was detected
        is_active = signal_strength > self.settings.squelch_threshold
        
        if is_active:
            # Reset quiet count and increment activity
            self.quiet_skip_count[freq_key] = 0
            self.frequency_activity[freq_key] = self.frequency_activity.get(freq_key, 0) + 1
            # Decay activity over time
            if self.frequency_activity[freq_key] > 10:
                self.frequency_activity[freq_key] = 10
        else:
            # Increment quiet count
            self.quiet_skip_count[freq_key] = self.quiet_skip_count.get(freq_key, 0) + 1
            # Decay activity
            if freq_key in self.frequency_activity:
                self.frequency_activity[freq_key] = max(0, self.frequency_activity[freq_key] - 0.5)

    def _calculate_adaptive_delay(self, frequency: Frequency, signal_strength: float) -> float:
        """Calculate adaptive scan delay based on frequency activity"""
        if not self.adaptive_delay_enabled:
            return self.settings.scan_delay
        
        freq_key = frequency.frequency
        
        # Base delay from settings
        base_delay = self.settings.scan_delay
        
        # Reduce delay for active frequencies
        if signal_strength > self.settings.squelch_threshold:
            # Active frequency - scan more quickly
            return max(self.min_scan_delay, base_delay * 0.5)
        
        # Increase delay for quiet frequencies
        skip_count = self.quiet_skip_count.get(freq_key, 0)
        if skip_count > self.quiet_threshold:
            # Very quiet - scan less frequently
            return min(self.max_scan_delay, base_delay * (1 + skip_count * 0.2))
        
        # Normal delay
        return base_delay

    async def _tune_to_frequency(self, frequency: Frequency):
        """Tune SDR to specific frequency"""
        if self.sdr_device is None:
            return

        try:
            # Set center frequency
            self.sdr_device.center_freq = frequency.frequency
            await asyncio.sleep(0.01)  # Allow tuning to settle

        except Exception as e:
            logger.error(f"Error tuning to {frequency.frequency}: {e}")

    async def _check_for_transmission(self, frequency: Frequency) -> float:
        """Check for transmission on current frequency
        
        Returns:
            signal_strength: The detected signal strength in dBm
        """
        try:
            # Read samples
            if self.sdr_device is None:
                # Simulation mode - generate fake signal
                samples = self._generate_simulation_data(frequency)
            else:
                samples = self.sdr_device.read_samples(8192)

            # Calculate signal strength
            signal_strength = SignalProcessor.calculate_power(samples)

            # Send signal strength update
            if self.signal_strength_callback:
                await self.signal_strength_callback({
                    'frequency': frequency.frequency,
                    'signal_strength': signal_strength,
                    'timestamp': datetime.now().isoformat()
                })

            # Check for transmission
            is_transmission = SignalProcessor.detect_transmission(
                samples, self.settings.squelch_threshold
            )

            if is_transmission:
                logger.info(f"Transmission detected on {frequency.frequency / 1e6:.3f} MHz")
                await self._handle_transmission(frequency, samples, signal_strength)
            
            return signal_strength

        except Exception as e:
            logger.error(f"Error checking transmission on {frequency.frequency}: {e}")
            return -100.0  # Return very low signal strength on error

    def _generate_simulation_data(self, frequency: Frequency) -> np.ndarray:
        """Generate simulation data for testing"""
        # Simple noise with occasional "transmissions"
        samples = np.random.normal(0, 0.1, 8192) + 1j * np.random.normal(0, 0.1, 8192)

        # Simulate transmission every 30 seconds on first frequency
        current_time = time.time()
        if (frequency == self.scan_list[0] and
                int(current_time) % 30 < 2):  # 2-second transmission every 30 seconds
            # Add stronger signal to simulate transmission
            samples += (np.random.normal(0, 0.5, 8192) + 1j * np.random.normal(0, 0.5, 8192))

        return samples

    async def _handle_transmission(self, frequency: Frequency, samples: np.ndarray, signal_strength: float):
        """Handle detected transmission"""
        try:
            # Demodulate based on frequency type
            if frequency.modulation.upper() == "AM":
                audio_data = SignalProcessor.demodulate_am(samples)
            else:  # FM
                audio_data = SignalProcessor.demodulate_fm(samples)

            # Create transmission event
            transmission = TransmissionEvent(
                frequency=frequency.frequency,
                signal_strength=signal_strength,
                timestamp=datetime.now(),
                audio_data=audio_data
            )

            # Notify callback
            if self.transmission_callback:
                await self.transmission_callback(transmission)

        except Exception as e:
            logger.error(f"Error handling transmission: {e}")

    def get_status(self) -> dict:
        """Get current scanner status"""
        # Calculate priority statistics
        priority_stats = {}
        if self.priority_scanning_enabled and self.frequency_scan_count:
            enabled_freqs = [f for f in self.scan_list if f.enabled]
            if enabled_freqs:
                total_scans = sum(self.frequency_scan_count.values())
                for freq in enabled_freqs:
                    scan_count = self.frequency_scan_count.get(freq.frequency, 0)
                    weight = self.priority_weights.get(freq.frequency, 1.0)
                    expected_ratio = weight / sum(self.priority_weights.get(f.frequency, 1.0) for f in enabled_freqs) if enabled_freqs else 0
                    actual_ratio = scan_count / total_scans if total_scans > 0 else 0
                    priority_stats[freq.frequency] = {
                        'priority': freq.priority,
                        'scans': scan_count,
                        'weight': weight,
                        'expected_ratio': expected_ratio,
                        'actual_ratio': actual_ratio
                    }
        
        return {
            'is_scanning': self.is_scanning,
            'current_frequency': self.current_frequency,
            'scan_list_size': len(self.scan_list),
            'sdr_connected': self.sdr_device is not None,
            'scan_index': self.scan_index,
            'smart_scanning_enabled': self.smart_scanning_enabled,
            'adaptive_delay_enabled': self.adaptive_delay_enabled,
            'priority_scanning_enabled': self.priority_scanning_enabled,
            'priority_scan_mode': self.settings.priority_scan_mode,
            'active_frequencies': len([f for f in self.scan_list if f.enabled and 
                                      self.quiet_skip_count.get(f.frequency, 0) < self.quiet_threshold]),
            'priority_stats': priority_stats
        }
    
    def enable_smart_scanning(self):
        """Enable smart scanning algorithms"""
        self.smart_scanning_enabled = True
        logger.info("Smart scanning enabled")
    
    def disable_smart_scanning(self):
        """Disable smart scanning algorithms"""
        self.smart_scanning_enabled = False
        logger.info("Smart scanning disabled")
    
    def enable_adaptive_delay(self):
        """Enable adaptive scan delay"""
        self.adaptive_delay_enabled = True
        logger.info("Adaptive delay enabled")
    
    def disable_adaptive_delay(self):
        """Disable adaptive scan delay"""
        self.adaptive_delay_enabled = False
        logger.info("Adaptive delay disabled")
    
    def enable_priority_scanning(self):
        """Enable priority-based scanning"""
        self.priority_scanning_enabled = True
        self._initialize_priority_scanning()
        logger.info("Priority-based scanning enabled")
    
    def disable_priority_scanning(self):
        """Disable priority-based scanning"""
        self.priority_scanning_enabled = False
        logger.info("Priority-based scanning disabled")
    
    def set_priority_multiplier(self, multiplier: float):
        """Set priority multiplier (how much priority affects scan frequency)"""
        self.settings.priority_multiplier = max(1.0, min(10.0, multiplier))  # Clamp between 1.0 and 10.0
        if self.priority_scanning_enabled:
            self._initialize_priority_scanning()
        logger.info(f"Priority multiplier set to {self.settings.priority_multiplier}")
    
    def reset_scanning_state(self):
        """Reset smart scanning state"""
        self.frequency_activity.clear()
        self.frequency_last_signal.clear()
        self.quiet_skip_count.clear()
        self.frequency_scan_count.clear()
        if self.priority_scanning_enabled:
            self._initialize_priority_scanning()
        logger.info("Smart scanning state reset")
    
    def _initialize_priority_scanning(self):
        """Initialize priority-based scanning queue and weights"""
        enabled_frequencies = [f for f in self.scan_list if f.enabled]
        
        # Calculate priority weights for each frequency
        self.priority_weights = {}
        max_priority = max([f.priority for f in enabled_frequencies], default=100)
        
        for freq in enabled_frequencies:
            # Calculate weight: higher priority = higher weight
            # Weight = min_weight + (priority / max_priority) * (multiplier - min_weight)
            normalized_priority = freq.priority / max_priority if max_priority > 0 else 0.5
            weight = self.settings.min_priority_weight + (
                normalized_priority * (self.settings.priority_multiplier - self.settings.min_priority_weight)
            )
            self.priority_weights[freq.frequency] = weight
            self.frequency_scan_count[freq.frequency] = 0
        
        logger.info(f"Priority scanning initialized for {len(enabled_frequencies)} frequencies")
    
    def _select_priority_based_frequency(self, enabled_frequencies: List[Frequency]) -> Frequency:
        """Select next frequency based on priority weighting"""
        if not enabled_frequencies:
            return None
        
        # If priority scan mode is round_robin, use simple round-robin
        if self.settings.priority_scan_mode == "round_robin":
            self.scan_index = (self.scan_index + 1) % len(enabled_frequencies)
            return enabled_frequencies[self.scan_index]
        
        # Weighted selection based on priority
        # Calculate expected scan ratio for each frequency
        weights = []
        for freq in enabled_frequencies:
            weight = self.priority_weights.get(freq.frequency, 1.0)
            
            # Adjust weight based on how many times it's been scanned
            # Frequencies that have been scanned less relative to their priority get higher weight
            scan_count = self.frequency_scan_count.get(freq.frequency, 0)
            total_scans = sum(self.frequency_scan_count.values()) or 1
            
            # Calculate expected scans based on weight
            total_weight = sum(self.priority_weights.get(f.frequency, 1.0) for f in enabled_frequencies)
            expected_ratio = weight / total_weight if total_weight > 0 else 1.0 / len(enabled_frequencies)
            actual_ratio = scan_count / total_scans if total_scans > 0 else 0
            
            # Boost weight if frequency is under-scanned relative to its priority
            if actual_ratio < expected_ratio:
                weight *= (1.0 + (expected_ratio - actual_ratio) * 2.0)
            
            weights.append(max(0.1, weight))  # Ensure minimum weight
        
        # Weighted random selection
        selected = random.choices(enabled_frequencies, weights=weights, k=1)[0]
        return selected
    
    def _update_priority_scanning_state(self, frequency: Frequency):
        """Update priority scanning state after scanning a frequency"""
        freq_key = frequency.frequency
        self.frequency_scan_count[freq_key] = self.frequency_scan_count.get(freq_key, 0) + 1

    async def add_frequency(self, frequency: float, modulation: str = "FM", description: str = ""):
        """Add frequency to scan list"""
        new_freq = Frequency(
            frequency=frequency,
            modulation=modulation,
            description=description,
            enabled=True
        )
        self.scan_list.append(new_freq)
        logger.info(f"Added frequency: {frequency / 1e6:.3f} MHz ({modulation})")

    async def remove_frequency(self, frequency: float):
        """Remove frequency from scan list"""
        self.scan_list = [f for f in self.scan_list if f.frequency != frequency]
        logger.info(f"Removed frequency: {frequency / 1e6:.3f} MHz")

    async def cleanup(self):
        """Cleanup SDR resources"""
        await self.stop_scanning()
        if self.sdr_device:
            self.sdr_device.close()
        logger.info("SDR manager cleaned up")