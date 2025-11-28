"""
Data models for sdr2zello application
"""

from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from pydantic import BaseModel, field_validator, Field
from typing import Optional, List
from datetime import datetime

Base = declarative_base()


# SQLAlchemy Models (Database)
class Frequency(Base):
    """Frequency database model"""
    __tablename__ = "frequencies"

    id = Column(Integer, primary_key=True, index=True)
    frequency = Column(Float, nullable=False, index=True)  # Frequency in Hz
    modulation = Column(String(10), nullable=False, default="FM")  # AM, FM, etc.
    friendly_name = Column(String(100), default="")  # User-friendly name for the frequency
    description = Column(String(255), default="")
    enabled = Column(Boolean, default=True)
    priority = Column(Integer, default=0)  # Scanning priority (higher = more frequent)
    group = Column(String(50), default="", index=True)  # Frequency group/tag (e.g., "Aviation", "Ham", "Marine")
    tags = Column(String(255), default="")  # Comma-separated tags for additional categorization
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class TransmissionLog(Base):
    """Transmission log database model"""
    __tablename__ = "transmission_logs"

    id = Column(Integer, primary_key=True, index=True)
    frequency = Column(Float, nullable=False, index=True)
    signal_strength = Column(Float, nullable=False)  # Signal strength in dBm
    timestamp = Column(DateTime, nullable=False, default=func.now(), index=True)
    duration = Column(Float, default=0.0)  # Transmission duration in seconds
    modulation = Column(String(10), nullable=False)
    description = Column(String(255), default="")
    audio_file_path = Column(String(500))  # Path to recorded audio file
    notes = Column(Text, default="")
    # Zello transmission status
    zello_sent = Column(Boolean, default=False)  # Whether audio was sent to Zello
    zello_success = Column(Boolean, default=False)  # Whether Zello transmission was successful
    zello_error = Column(String(500), default="")  # Error message if Zello transmission failed
    zello_audio_enabled = Column(Boolean, default=True)  # Whether audio was enabled at transmission time


class SystemLog(Base):
    """System log database model"""
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False, default=func.now(), index=True)
    level = Column(String(20), nullable=False)  # INFO, WARNING, ERROR, etc.
    module = Column(String(100), nullable=False)  # Module name
    message = Column(Text, nullable=False)
    details = Column(Text)  # Additional details/stack trace


class Recording(Base):
    """Recording database model - stores all recording metadata"""
    __tablename__ = "recordings"

    id = Column(Integer, primary_key=True, index=True)
    # File information
    filename = Column(String(500), nullable=False, index=True)
    filepath = Column(String(1000), nullable=False, unique=True)
    file_size_bytes = Column(Integer, default=0)
    format = Column(String(10), default="WAV")  # WAV, MP3
    bitrate = Column(String(10))  # For MP3: "128k", "192k", etc.
    
    # Recording metadata
    timestamp = Column(DateTime, nullable=False, default=func.now(), index=True)
    duration_seconds = Column(Float, nullable=False)
    sample_rate = Column(Integer, default=48000)
    channels = Column(Integer, default=1)
    bit_depth = Column(Integer, default=16)
    
    # Frequency information
    frequency_hz = Column(Float, nullable=False, index=True)
    frequency_mhz = Column(Float, nullable=False, index=True)
    friendly_name = Column(String(100), default="")  # User-friendly name for the frequency
    description = Column(String(255), default="")
    group = Column(String(50), default="", index=True)
    tags = Column(String(255), default="")
    modulation = Column(String(10), default="FM")
    priority = Column(Integer, default=0)
    
    # Signal information
    signal_strength_dbm = Column(Float, default=0.0)
    peak_signal_strength_dbm = Column(Float, default=0.0)
    squelch_threshold_dbm = Column(Float, default=-50.0)
    
    # Audio statistics
    max_amplitude = Column(Float)
    rms_level = Column(Float)
    peak_level_db = Column(Float)
    
    # User interaction
    is_favorite = Column(Boolean, default=False, index=True)
    notes = Column(Text, default="")
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), index=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


# Pydantic Models (API)
class FrequencyBase(BaseModel):
    """Base frequency model"""
    frequency: float = Field(..., ge=0.0, le=10e9, description="Frequency in Hz (0-10 GHz)")
    modulation: str = Field(default="FM", description="Modulation type")
    friendly_name: str = Field(default="", max_length=100, description="User-friendly name for the frequency")
    description: str = Field(default="", max_length=255, description="Frequency description")
    enabled: bool = Field(default=True, description="Whether frequency is enabled")
    priority: int = Field(default=0, ge=0, le=100, description="Scanning priority (0-100)")
    group: str = Field(default="", max_length=50, description="Frequency group/tag")
    tags: str = Field(default="", max_length=255, description="Comma-separated tags")

    @field_validator('modulation')
    @classmethod
    def validate_modulation(cls, v: str) -> str:
        """Validate modulation type"""
        valid_modulations = {'AM', 'FM', 'USB', 'LSB', 'CW', 'NFM', 'WFM'}
        v_upper = v.upper()
        if v_upper not in valid_modulations:
            raise ValueError(f"Invalid modulation type. Must be one of: {', '.join(valid_modulations)}")
        return v_upper

    @field_validator('description')
    @classmethod
    def validate_description(cls, v: str) -> str:
        """Sanitize description"""
        # Remove control characters and limit length
        v = ''.join(char for char in v if ord(char) >= 32 or char in '\n\r\t')
        return v[:255]


class FrequencyCreate(FrequencyBase):
    """Frequency creation model"""
    pass


class FrequencyUpdate(BaseModel):
    """Frequency update model"""
    frequency: Optional[float] = None
    modulation: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None


class FrequencyResponse(FrequencyBase):
    """Frequency response model"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TransmissionLogBase(BaseModel):
    """Base transmission log model"""
    frequency: float
    signal_strength: float
    duration: float = 0.0
    modulation: str = "FM"
    description: str = ""
    notes: str = ""
    zello_sent: bool = False
    zello_success: bool = False
    zello_error: str = ""
    zello_audio_enabled: bool = True


class TransmissionLogCreate(TransmissionLogBase):
    """Transmission log creation model"""
    timestamp: Optional[datetime] = None


class TransmissionLogResponse(TransmissionLogBase):
    """Transmission log response model"""
    id: int
    timestamp: datetime
    audio_file_path: Optional[str] = None

    class Config:
        from_attributes = True


class SystemLogResponse(BaseModel):
    """System log response model"""
    id: int
    timestamp: datetime
    level: str
    module: str
    message: str
    details: Optional[str] = None

    class Config:
        from_attributes = True


# Real-time data models
class SignalStrengthUpdate(BaseModel):
    """Real-time signal strength update"""
    frequency: float
    signal_strength: float
    timestamp: str


class ScannerStatus(BaseModel):
    """Scanner status update"""
    is_scanning: bool
    current_frequency: float
    scan_list_size: int
    sdr_connected: bool
    scan_index: int
    timestamp: str


class TransmissionAlert(BaseModel):
    """Real-time transmission alert"""
    frequency: float
    signal_strength: float
    timestamp: str
    modulation: str
    description: str
    duration: float = 0.0


# Configuration models
class AudioSettings(BaseModel):
    """Audio configuration settings"""
    sample_rate: int = 48000
    channels: int = 1
    chunk_size: int = 1024
    device_name: str = ""


class SDRSettings(BaseModel):
    """SDR configuration settings"""
    device_index: int = 0
    sample_rate: int = 2048000
    gain: float = 49.6
    squelch_threshold: float = -50.0


class ScanSettings(BaseModel):
    """Scanning configuration settings"""
    scan_delay: float = 0.1
    transmission_timeout: float = 5.0
    priority_multiplier: float = 2.0  # How much priority affects scan frequency


# Bulk operations
class FrequencyListImport(BaseModel):
    """Model for importing multiple frequencies"""
    frequencies: List[FrequencyCreate]
    overwrite_existing: bool = False


class FrequencyListExport(BaseModel):
    """Model for exporting frequency lists"""
    frequencies: List[FrequencyResponse]
    export_format: str = "json"  # json, csv, etc.


# Statistics models
class ScanningStats(BaseModel):
    """Scanning statistics"""
    total_scans: int
    transmissions_detected: int
    average_signal_strength: float
    most_active_frequency: float
    scan_duration: float  # Total scanning time in seconds
    frequencies_monitored: int


class FrequencyStats(BaseModel):
    """Per-frequency statistics"""
    frequency: float
    scan_count: int
    transmission_count: int
    average_signal_strength: float
    last_transmission: Optional[datetime] = None
    total_transmission_time: float = 0.0


# Recording models
class RecordingBase(BaseModel):
    """Base recording model"""
    filename: str
    filepath: str
    file_size_bytes: int = 0
    format: str = "WAV"
    bitrate: Optional[str] = None
    timestamp: datetime
    duration_seconds: float
    sample_rate: int = 48000
    channels: int = 1
    bit_depth: int = 16
    frequency_hz: float
    frequency_mhz: float
    friendly_name: str = ""
    description: str = ""
    group: str = ""
    tags: str = ""
    modulation: str = "FM"
    priority: int = 0
    signal_strength_dbm: float = 0.0
    peak_signal_strength_dbm: float = 0.0
    squelch_threshold_dbm: float = -50.0
    max_amplitude: Optional[float] = None
    rms_level: Optional[float] = None
    peak_level_db: Optional[float] = None
    is_favorite: bool = False
    notes: str = ""


class RecordingCreate(RecordingBase):
    """Recording creation model"""
    pass


class RecordingUpdate(BaseModel):
    """Recording update model"""
    is_favorite: Optional[bool] = None
    notes: Optional[str] = None
    description: Optional[str] = None


class RecordingResponse(RecordingBase):
    """Recording response model"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True