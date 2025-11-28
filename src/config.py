"""
Configuration management for sdr2zello
"""

from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List, Optional
import os
import yaml
from pathlib import Path


class Settings(BaseSettings):
    """Application settings"""

    # Server Configuration
    host: str = "localhost"
    port: int = 8000
    debug: bool = False
    log_level: str = "INFO"

    # RTL-SDR Configuration
    sdr_device_index: int = 0
    sdr_sample_rate: int = 2048000  # 2.048 MHz
    sdr_gain: float = 49.6  # dB, 'auto' for automatic gain

    # Audio Configuration
    audio_sample_rate: int = 48000
    audio_channels: int = 1  # Mono
    audio_chunk_size: int = 1024
    audio_device_name: str = ""  # Empty = default device

    # Scanning Configuration
    scan_delay: float = 0.1  # Seconds between frequency changes
    squelch_threshold: float = -50.0  # dBm
    transmission_timeout: float = 5.0  # Seconds to wait for transmission end
    
    # Priority-Based Scanning Configuration
    priority_scanning_enabled: bool = True  # Enable priority-based scanning
    priority_multiplier: float = 2.0  # How much priority affects scan frequency (2.0 = priority 50 scanned 2x more than priority 0)
    min_priority_weight: float = 0.5  # Minimum weight for lowest priority frequencies
    priority_scan_mode: str = "weighted"  # "weighted" (priority affects selection) or "round_robin" (equal time)

    # DSP and Audio Enhancement Configuration
    # Noise Gate Settings
    enable_noise_gate: bool = True
    noise_gate_threshold: float = -40.0  # dB threshold for noise gate
    noise_gate_attack_time: float = 0.001  # Attack time in seconds
    noise_gate_release_time: float = 0.1  # Release time in seconds

    # Automatic Gain Control (AGC) Settings
    enable_agc: bool = True
    agc_target_level: float = -20.0  # Target output level in dB
    agc_attack_time: float = 0.003  # AGC attack time in seconds
    agc_release_time: float = 0.1  # AGC release time in seconds
    agc_max_gain: float = 40.0  # Maximum gain in dB

    # Noise Reduction Settings
    enable_noise_reduction: bool = False  # Disabled by default (computationally intensive)
    noise_reduction_alpha: float = 2.0  # Over-subtraction factor (1.0-3.0)
    noise_reduction_frame_size: int = 1024  # Frame size for spectral processing

    # Equalizer Settings
    enable_equalizer: bool = False  # Disabled by default
    eq_sub_bass_gain: float = 0.0  # 60Hz high-pass filter
    eq_bass_gain: float = 0.0  # 200Hz gain
    eq_low_mid_gain: float = 0.0  # 500Hz gain
    eq_mid_gain: float = 0.0  # 1kHz gain
    eq_high_mid_gain: float = 0.0  # 2kHz gain
    eq_presence_gain: float = 0.0  # 4kHz gain
    eq_brilliance_gain: float = 0.0  # 8kHz gain
    eq_air_gain: float = 0.0  # 12kHz low-pass filter

    # Database Configuration
    database_url: str = "sqlite:///sdr2zello.db"

    # Frequency Lists (Default frequencies for testing)
    default_frequencies: List[float] = [
        # Aviation (AM)
        118.0e6,  # Tower frequency
        121.5e6,  # Emergency frequency
        122.8e6,  # Unicom

        # Amateur Radio (FM)
        145.5e6,  # 2m repeater
        446.0e6,  # 70cm repeater

        # General VHF/UHF (FM)
        155.16e6,  # Marine VHF
        162.55e6,  # Weather radio
    ]

    @classmethod
    def load_from_yaml(cls, config_path: str = "config.yaml") -> dict:
        """Load configuration from YAML file"""
        config_data = {}
        config_file = Path(config_path)
        
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    yaml_data = yaml.safe_load(f) or {}
                    
                # Flatten nested structure for Pydantic
                if 'server' in yaml_data:
                    config_data.update({
                        'host': yaml_data['server'].get('host', 'localhost'),
                        'port': yaml_data['server'].get('port', 8000),
                        'debug': yaml_data['server'].get('debug', False),
                        'log_level': yaml_data['server'].get('log_level', 'INFO'),
                    })
                
                if 'sdr' in yaml_data:
                    config_data.update({
                        'sdr_device_index': yaml_data['sdr'].get('device_index', 0),
                        'sdr_sample_rate': yaml_data['sdr'].get('sample_rate', 2048000),
                        'sdr_gain': yaml_data['sdr'].get('gain', 49.6),
                    })
                
                if 'audio' in yaml_data:
                    config_data.update({
                        'audio_sample_rate': yaml_data['audio'].get('sample_rate', 48000),
                        'audio_channels': yaml_data['audio'].get('channels', 1),
                        'audio_chunk_size': yaml_data['audio'].get('chunk_size', 1024),
                        'audio_device_name': yaml_data['audio'].get('device_name', ''),
                    })
                
                if 'scanning' in yaml_data:
                    config_data.update({
                        'scan_delay': yaml_data['scanning'].get('delay', 0.1),
                        'squelch_threshold': yaml_data['scanning'].get('squelch_threshold', -50.0),
                        'transmission_timeout': yaml_data['scanning'].get('transmission_timeout', 5.0),
                    })
                
                if 'priority_scanning' in yaml_data:
                    config_data.update({
                        'priority_scanning_enabled': yaml_data['priority_scanning'].get('enabled', True),
                        'priority_multiplier': yaml_data['priority_scanning'].get('multiplier', 2.0),
                        'min_priority_weight': yaml_data['priority_scanning'].get('min_priority_weight', 0.5),
                        'priority_scan_mode': yaml_data['priority_scanning'].get('scan_mode', 'weighted'),
                    })
                
                if 'recording' in yaml_data:
                    config_data['recordings_dir'] = yaml_data['recording'].get('directory', 'recordings')
                    config_data['recording_format'] = yaml_data['recording'].get('format', 'wav')
                    config_data['mp3_bitrate'] = yaml_data['recording'].get('mp3_bitrate', '192k')
                
                if 'dsp' in yaml_data:
                    dsp = yaml_data['dsp']
                    if 'noise_gate' in dsp:
                        ng = dsp['noise_gate']
                        config_data.update({
                            'enable_noise_gate': ng.get('enabled', True),
                            'noise_gate_threshold': ng.get('threshold', -40.0),
                            'noise_gate_attack_time': ng.get('attack_time', 0.001),
                            'noise_gate_release_time': ng.get('release_time', 0.1),
                        })
                    if 'agc' in dsp:
                        agc = dsp['agc']
                        config_data.update({
                            'enable_agc': agc.get('enabled', True),
                            'agc_target_level': agc.get('target_level', -20.0),
                            'agc_attack_time': agc.get('attack_time', 0.003),
                            'agc_release_time': agc.get('release_time', 0.1),
                            'agc_max_gain': agc.get('max_gain', 40.0),
                        })
                    if 'noise_reduction' in dsp:
                        nr = dsp['noise_reduction']
                        config_data.update({
                            'enable_noise_reduction': nr.get('enabled', False),
                            'noise_reduction_alpha': nr.get('alpha', 2.0),
                            'noise_reduction_frame_size': nr.get('frame_size', 1024),
                        })
                    if 'equalizer' in dsp:
                        eq = dsp['equalizer']
                        config_data.update({
                            'enable_equalizer': eq.get('enabled', False),
                            'eq_sub_bass_gain': eq.get('sub_bass_gain', 0.0),
                            'eq_bass_gain': eq.get('bass_gain', 0.0),
                            'eq_low_mid_gain': eq.get('low_mid_gain', 0.0),
                            'eq_mid_gain': eq.get('mid_gain', 0.0),
                            'eq_high_mid_gain': eq.get('high_mid_gain', 0.0),
                            'eq_presence_gain': eq.get('presence_gain', 0.0),
                            'eq_brilliance_gain': eq.get('brilliance_gain', 0.0),
                            'eq_air_gain': eq.get('air_gain', 0.0),
                        })
                
                if 'database' in yaml_data:
                    config_data['database_url'] = yaml_data['database'].get('url', 'sqlite:///sdr2zello.db')
                
                if 'default_frequencies' in yaml_data:
                    config_data['default_frequencies'] = yaml_data['default_frequencies']
                
                if 'paths' in yaml_data:
                    paths = yaml_data['paths']
                    config_data['static_files_path'] = paths.get('static_files', 'static')
                    config_data['templates_path'] = paths.get('templates', 'templates')
                    if 'recordings' in paths:
                        config_data['recordings_dir'] = paths['recordings']
                        
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Error loading config.yaml: {e}. Using defaults.")
        
        return config_data

    def get_dsp_config(self) -> dict:
        """Get DSP configuration as dictionary"""
        return {
            # Noise Gate
            'enable_noise_gate': self.enable_noise_gate,
            'noise_gate_threshold': self.noise_gate_threshold,
            'noise_gate_attack_time': self.noise_gate_attack_time,
            'noise_gate_release_time': self.noise_gate_release_time,

            # AGC
            'enable_agc': self.enable_agc,
            'agc_target_level': self.agc_target_level,
            'agc_attack_time': self.agc_attack_time,
            'agc_release_time': self.agc_release_time,
            'agc_max_gain': self.agc_max_gain,

            # Noise Reduction
            'enable_noise_reduction': self.enable_noise_reduction,
            'noise_reduction_alpha': self.noise_reduction_alpha,
            'noise_reduction_frame_size': self.noise_reduction_frame_size,

            # Equalizer
            'enable_equalizer': self.enable_equalizer,
        }

    def get_eq_config(self) -> dict:
        """Get equalizer band configuration as dictionary"""
        return {
            'sub_bass': self.eq_sub_bass_gain,
            'bass': self.eq_bass_gain,
            'low_mid': self.eq_low_mid_gain,
            'mid': self.eq_mid_gain,
            'high_mid': self.eq_high_mid_gain,
            'presence': self.eq_presence_gain,
            'brilliance': self.eq_brilliance_gain,
            'air': self.eq_air_gain,
        }

    # Web Interface
    static_files_path: str = "static"
    templates_path: str = "templates"
    recordings_dir: str = "recordings"
    
    # Recording Format
    recording_format: str = "wav"  # "wav" or "mp3"
    mp3_bitrate: str = "192k"      # MP3 bitrate: "128k", "192k", "256k", "320k"
    
    @field_validator('recording_format')
    @classmethod
    def validate_recording_format(cls, v):
        """Validate recording format is either 'wav' or 'mp3'"""
        if v.lower() not in ['wav', 'mp3']:
            raise ValueError("recording_format must be 'wav' or 'mp3'")
        return v.lower()
    
    @field_validator('mp3_bitrate')
    @classmethod
    def validate_mp3_bitrate(cls, v):
        """Validate MP3 bitrate format"""
        if not isinstance(v, str):
            v = str(v)
        # Remove 'k' suffix if present and validate
        bitrate_str = v.replace('k', '').replace('K', '')
        try:
            bitrate_value = int(bitrate_str)
            if bitrate_value not in [128, 192, 256, 320]:
                raise ValueError("mp3_bitrate must be one of: 128k, 192k, 256k, 320k")
        except ValueError:
            raise ValueError("mp3_bitrate must be a valid bitrate (e.g., '192k')")
        return v

    class Config:
        # Support both YAML config file and environment variables
        # Environment variables take precedence over config file
        env_prefix = "sdr2zello_"
        case_sensitive = False


# Global settings instance
_settings = None


def get_settings(config_path: str = "config.yaml") -> Settings:
    """Get global settings instance, loading from YAML config file"""
    global _settings
    if _settings is None:
        # Load from YAML config file first
        yaml_config = Settings.load_from_yaml(config_path)
        
        # Create settings instance with YAML config, env vars will override
        _settings = Settings(**yaml_config)
    return _settings