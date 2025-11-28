"""
Database configuration and initialization for sdr2zello
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import asynccontextmanager
from typing import Optional
from datetime import datetime
import logging

from .config import get_settings
from .models import Base

logger = logging.getLogger(__name__)

# Database engine and session
engine = None
SessionLocal = None


async def init_db():
    """Initialize database connection and create tables"""
    global engine, SessionLocal

    settings = get_settings()

    try:
        # Create engine
        engine = create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {}
        )

        # Create session factory
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        # Create all tables
        Base.metadata.create_all(bind=engine)

        logger.info(f"Database initialized: {settings.database_url}")

    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise


def get_db() -> Session:
    """Get database session"""
    if SessionLocal is None:
        raise RuntimeError("Database not initialized")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def get_async_db():
    """Get async database session context manager"""
    db = next(get_db())
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# Database utility functions
class DatabaseManager:
    """Database operations manager"""

    @staticmethod
    async def create_frequency(db: Session, frequency_data: dict):
        """Create a new frequency record"""
        from .models import Frequency

        frequency = Frequency(**frequency_data)
        db.add(frequency)
        db.commit()
        db.refresh(frequency)
        return frequency

    @staticmethod
    async def get_frequencies(db: Session, skip: int = 0, limit: int = 100):
        """Get all frequencies with pagination"""
        from .models import Frequency

        return db.query(Frequency).offset(skip).limit(limit).all()

    @staticmethod
    async def get_frequency_by_id(db: Session, frequency_id: int):
        """Get frequency by ID"""
        from .models import Frequency

        return db.query(Frequency).filter(Frequency.id == frequency_id).first()

    @staticmethod
    async def get_frequency_by_value(db: Session, frequency_value: float):
        """Get frequency by its value"""
        from .models import Frequency

        return db.query(Frequency).filter(Frequency.frequency == frequency_value).first()

    @staticmethod
    async def update_frequency(db: Session, frequency_id: int, update_data: dict):
        """Update frequency record"""
        from .models import Frequency

        frequency = db.query(Frequency).filter(Frequency.id == frequency_id).first()
        if frequency:
            for key, value in update_data.items():
                if hasattr(frequency, key) and value is not None:
                    setattr(frequency, key, value)
            db.commit()
            db.refresh(frequency)
        return frequency

    @staticmethod
    async def delete_frequency(db: Session, frequency_id: int):
        """Delete frequency record"""
        from .models import Frequency

        frequency = db.query(Frequency).filter(Frequency.id == frequency_id).first()
        if frequency:
            db.delete(frequency)
            db.commit()
        return frequency

    @staticmethod
    async def create_recording(db: Session, recording_data: dict):
        """Create a new recording record"""
        from .models import Recording

        recording = Recording(**recording_data)
        db.add(recording)
        db.commit()
        db.refresh(recording)
        return recording

    @staticmethod
    async def get_recordings(
        db: Session, 
        skip: int = 0, 
        limit: int = 100,
        favorite_only: bool = False,
        frequency: Optional[float] = None,
        group: Optional[str] = None,
        format: Optional[str] = None,
        search: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ):
        """Get recordings with filtering and search"""
        from .models import Recording

        query = db.query(Recording)

        # Apply filters
        if favorite_only:
            query = query.filter(Recording.is_favorite == True)
        
        if frequency is not None:
            query = query.filter(Recording.frequency_hz == frequency)
        
        if group:
            query = query.filter(Recording.group == group)
        
        if format:
            query = query.filter(Recording.format == format)
        
        if start_date:
            query = query.filter(Recording.timestamp >= start_date)
        
        if end_date:
            query = query.filter(Recording.timestamp <= end_date)
        
        # Search across multiple fields
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                (Recording.filename.ilike(search_term)) |
                (Recording.description.ilike(search_term)) |
                (Recording.group.ilike(search_term)) |
                (Recording.tags.ilike(search_term)) |
                (Recording.modulation.ilike(search_term))
            )

        # Order by timestamp (newest first)
        query = query.order_by(Recording.timestamp.desc())

        return query.offset(skip).limit(limit).all()

    @staticmethod
    async def get_recording_by_id(db: Session, recording_id: int):
        """Get recording by ID"""
        from .models import Recording

        return db.query(Recording).filter(Recording.id == recording_id).first()

    @staticmethod
    async def get_recording_by_filepath(db: Session, filepath: str):
        """Get recording by filepath"""
        from .models import Recording

        return db.query(Recording).filter(Recording.filepath == filepath).first()

    @staticmethod
    async def update_recording(db: Session, recording_id: int, update_data: dict):
        """Update recording record"""
        from .models import Recording

        recording = db.query(Recording).filter(Recording.id == recording_id).first()
        if recording:
            for key, value in update_data.items():
                if hasattr(recording, key) and value is not None:
                    setattr(recording, key, value)
            db.commit()
            db.refresh(recording)
        return recording

    @staticmethod
    async def delete_recording(db: Session, recording_id: int):
        """Delete recording record"""
        from .models import Recording

        recording = db.query(Recording).filter(Recording.id == recording_id).first()
        if recording:
            db.delete(recording)
            db.commit()
        return recording
        from .models import Frequency

        frequency = db.query(Frequency).filter(Frequency.id == frequency_id).first()
        if frequency:
            db.delete(frequency)
            db.commit()
            return True
        return False

    @staticmethod
    async def create_transmission_log(db: Session, log_data: dict):
        """Create transmission log entry"""
        from .models import TransmissionLog

        transmission = TransmissionLog(**log_data)
        db.add(transmission)
        db.commit()
        db.refresh(transmission)
        return transmission

    @staticmethod
    async def update_transmission_log(db: Session, transmission_id: int, update_data: dict):
        """Update transmission log entry"""
        from .models import TransmissionLog

        transmission = db.query(TransmissionLog).filter(TransmissionLog.id == transmission_id).first()
        if transmission:
            for key, value in update_data.items():
                setattr(transmission, key, value)
            db.commit()
            db.refresh(transmission)
            return transmission
        return None

    @staticmethod
    async def get_transmission_log_by_frequency_and_time(db: Session, frequency: float, timestamp: datetime, tolerance_seconds: int = 5):
        """Get transmission log by frequency and approximate timestamp"""
        from .models import TransmissionLog
        from datetime import timedelta

        time_start = timestamp - timedelta(seconds=tolerance_seconds)
        time_end = timestamp + timedelta(seconds=tolerance_seconds)

        return db.query(TransmissionLog).filter(
            TransmissionLog.frequency == frequency,
            TransmissionLog.timestamp >= time_start,
            TransmissionLog.timestamp <= time_end
        ).order_by(TransmissionLog.timestamp.desc()).first()

    @staticmethod
    async def get_transmission_logs(db: Session, skip: int = 0, limit: int = 100,
                                  frequency: float = None):
        """Get transmission logs with optional frequency filter"""
        from .models import TransmissionLog

        query = db.query(TransmissionLog)
        if frequency:
            query = query.filter(TransmissionLog.frequency == frequency)

        return query.order_by(TransmissionLog.timestamp.desc()).offset(skip).limit(limit).all()

    @staticmethod
    async def get_recent_transmissions(db: Session, hours: int = 24):
        """Get recent transmission logs"""
        from .models import TransmissionLog
        from datetime import datetime, timedelta

        cutoff_time = datetime.now() - timedelta(hours=hours)
        return db.query(TransmissionLog)\
                .filter(TransmissionLog.timestamp >= cutoff_time)\
                .order_by(TransmissionLog.timestamp.desc())\
                .all()

    @staticmethod
    async def create_system_log(db: Session, level: str, module: str, message: str, details: str = None):
        """Create system log entry"""
        from .models import SystemLog

        log_entry = SystemLog(
            level=level,
            module=module,
            message=message,
            details=details
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry

    @staticmethod
    async def get_system_logs(db: Session, skip: int = 0, limit: int = 100,
                            level: str = None):
        """Get system logs with optional level filter"""
        from .models import SystemLog

        query = db.query(SystemLog)
        if level:
            query = query.filter(SystemLog.level == level)

        return query.order_by(SystemLog.timestamp.desc()).offset(skip).limit(limit).all()

    @staticmethod
    async def get_frequency_statistics(db: Session):
        """Get frequency usage statistics"""
        from .models import TransmissionLog, Frequency
        from sqlalchemy import func

        # Get transmission counts per frequency
        stats = db.query(
            TransmissionLog.frequency,
            func.count(TransmissionLog.id).label('transmission_count'),
            func.avg(TransmissionLog.signal_strength).label('avg_signal_strength'),
            func.sum(TransmissionLog.duration).label('total_duration'),
            func.max(TransmissionLog.timestamp).label('last_transmission')
        ).group_by(TransmissionLog.frequency).all()

        return stats

    @staticmethod
    async def cleanup_old_logs(db: Session, days: int = 30):
        """Clean up old transmission and system logs"""
        from .models import TransmissionLog, SystemLog
        from datetime import datetime, timedelta

        cutoff_time = datetime.now() - timedelta(days=days)

        # Delete old transmission logs
        deleted_transmissions = db.query(TransmissionLog)\
                                .filter(TransmissionLog.timestamp < cutoff_time)\
                                .delete()

        # Delete old system logs
        deleted_system_logs = db.query(SystemLog)\
                            .filter(SystemLog.timestamp < cutoff_time)\
                            .delete()

        db.commit()

        logger.info(f"Cleaned up {deleted_transmissions} transmission logs and "
                   f"{deleted_system_logs} system logs older than {days} days")

        return deleted_transmissions + deleted_system_logs