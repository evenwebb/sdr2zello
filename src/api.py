"""
API routes for sdr2zello web interface
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import logging
import os

from .database import get_db, DatabaseManager
from .models import (
    FrequencyCreate, FrequencyUpdate, FrequencyResponse,
    TransmissionLogCreate, TransmissionLogResponse,
    SystemLogResponse, AudioSettings, SDRSettings,
    ScanSettings,
    SignalStrengthUpdate, ScannerStatus, TransmissionAlert,
    TransmissionLog, Frequency,
    RecordingResponse, RecordingUpdate, Recording
)
from .security import validate_file_path, sanitize_filename

logger = logging.getLogger(__name__)

router = APIRouter()

# Global references (will be set by main app)
sdr_manager = None
audio_manager = None


def set_managers(sdr_mgr, audio_mgr):
    """Set global manager references"""
    global sdr_manager, audio_manager
    sdr_manager = sdr_mgr
    audio_manager = audio_mgr


# Frequency Management Endpoints
@router.get("/frequencies", response_model=List[FrequencyResponse])
async def get_frequencies(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    enabled_only: bool = Query(False),
    group: Optional[str] = Query(None, description="Filter by frequency group"),
    tag: Optional[str] = Query(None, description="Filter by tag (searches in tags field)"),
    db: Session = Depends(get_db)
):
    """Get all frequencies with optional filtering"""
    try:
        # Filter in database for better performance
        query = db.query(Frequency)
        if enabled_only:
            query = query.filter(Frequency.enabled == True)
        if group:
            query = query.filter(Frequency.group == group)
        if tag:
            query = query.filter(Frequency.tags.contains(tag))
        frequencies = query.offset(skip).limit(limit).all()
        return frequencies
    except Exception as e:
        logger.error(f"Error getting frequencies: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving frequencies")


@router.post("/frequencies", response_model=FrequencyResponse)
async def create_frequency(
    frequency: FrequencyCreate,
    db: Session = Depends(get_db)
):
    """Create a new frequency"""
    try:
        # Check if frequency already exists
        existing = await DatabaseManager.get_frequency_by_value(db, frequency.frequency)
        if existing:
            raise HTTPException(status_code=400, detail="Frequency already exists")

        # Create new frequency
        new_frequency = await DatabaseManager.create_frequency(db, frequency.dict())

        # Update SDR manager scan list if available
        if sdr_manager:
            await sdr_manager.add_frequency(
                frequency.frequency, frequency.modulation, frequency.description
            )

        return new_frequency

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating frequency: {e}")
        raise HTTPException(status_code=500, detail="Error creating frequency")


@router.put("/frequencies/{frequency_id}", response_model=FrequencyResponse)
async def update_frequency(
    frequency_id: int,
    frequency: FrequencyUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing frequency"""
    try:
        updated_frequency = await DatabaseManager.update_frequency(
            db, frequency_id, frequency.dict(exclude_unset=True)
        )

        if not updated_frequency:
            raise HTTPException(status_code=404, detail="Frequency not found")

        return updated_frequency

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating frequency: {e}")
        raise HTTPException(status_code=500, detail="Error updating frequency")


@router.delete("/frequencies/{frequency_id}")
async def delete_frequency(
    frequency_id: int,
    db: Session = Depends(get_db)
):
    """Delete a frequency"""
    try:
        # Get frequency details before deletion
        frequency = await DatabaseManager.get_frequency_by_id(db, frequency_id)
        if not frequency:
            raise HTTPException(status_code=404, detail="Frequency not found")

        # Delete from database
        success = await DatabaseManager.delete_frequency(db, frequency_id)
        if not success:
            raise HTTPException(status_code=500, detail="Error deleting frequency")

        # Remove from SDR manager scan list if available
        if sdr_manager:
            await sdr_manager.remove_frequency(frequency.frequency)

        return {"message": "Frequency deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting frequency: {e}")
        raise HTTPException(status_code=500, detail="Error deleting frequency")


# Scanner Control Endpoints
@router.post("/scanner/start")
async def start_scanner():
    """Start frequency scanning"""
    try:
        if not sdr_manager:
            raise HTTPException(status_code=503, detail="SDR manager not available")

        await sdr_manager.start_scanning()
        return {"message": "Scanner started successfully"}

    except Exception as e:
        logger.error(f"Error starting scanner: {e}")
        raise HTTPException(status_code=500, detail="Error starting scanner")


@router.post("/scanner/stop")
async def stop_scanner():
    """Stop frequency scanning"""
    try:
        if not sdr_manager:
            raise HTTPException(status_code=503, detail="SDR manager not available")

        await sdr_manager.stop_scanning()
        return {"message": "Scanner stopped successfully"}

    except Exception as e:
        logger.error(f"Error stopping scanner: {e}")
        raise HTTPException(status_code=500, detail="Error stopping scanner")


@router.get("/scanner/status", response_model=ScannerStatus)
async def get_scanner_status():
    """Get current scanner status"""
    try:
        if not sdr_manager:
            raise HTTPException(status_code=503, detail="SDR manager not available")

        status = sdr_manager.get_status()
        status['timestamp'] = datetime.now().isoformat()
        return status

    except Exception as e:
        logger.error(f"Error getting scanner status: {e}")
        raise HTTPException(status_code=500, detail="Error getting scanner status")


@router.post("/scanner/smart-scanning/enable")
async def enable_smart_scanning():
    """Enable smart scanning algorithms"""
    try:
        if not sdr_manager:
            raise HTTPException(status_code=503, detail="SDR manager not available")
        sdr_manager.enable_smart_scanning()
        return {"message": "Smart scanning enabled"}
    except Exception as e:
        logger.error(f"Error enabling smart scanning: {e}")
        raise HTTPException(status_code=500, detail="Error enabling smart scanning")


@router.post("/scanner/smart-scanning/disable")
async def disable_smart_scanning():
    """Disable smart scanning algorithms"""
    try:
        if not sdr_manager:
            raise HTTPException(status_code=503, detail="SDR manager not available")
        sdr_manager.disable_smart_scanning()
        return {"message": "Smart scanning disabled"}
    except Exception as e:
        logger.error(f"Error disabling smart scanning: {e}")
        raise HTTPException(status_code=500, detail="Error disabling smart scanning")


@router.post("/scanner/smart-scanning/reset")
async def reset_smart_scanning():
    """Reset smart scanning state"""
    try:
        if not sdr_manager:
            raise HTTPException(status_code=503, detail="SDR manager not available")
        sdr_manager.reset_scanning_state()
        return {"message": "Smart scanning state reset"}
    except Exception as e:
        logger.error(f"Error resetting smart scanning: {e}")
        raise HTTPException(status_code=500, detail="Error resetting smart scanning")


# Priority-Based Scanning Endpoints
@router.post("/scanner/priority-scanning/enable")
async def enable_priority_scanning():
    """Enable priority-based scanning"""
    try:
        if not sdr_manager:
            raise HTTPException(status_code=503, detail="SDR manager not available")
        sdr_manager.enable_priority_scanning()
        return {"message": "Priority-based scanning enabled"}
    except Exception as e:
        logger.error(f"Error enabling priority scanning: {e}")
        raise HTTPException(status_code=500, detail="Error enabling priority scanning")


@router.post("/scanner/priority-scanning/disable")
async def disable_priority_scanning():
    """Disable priority-based scanning"""
    try:
        if not sdr_manager:
            raise HTTPException(status_code=503, detail="SDR manager not available")
        sdr_manager.disable_priority_scanning()
        return {"message": "Priority-based scanning disabled"}
    except Exception as e:
        logger.error(f"Error disabling priority scanning: {e}")
        raise HTTPException(status_code=500, detail="Error disabling priority scanning")


@router.post("/scanner/priority-scanning/multiplier")
async def set_priority_multiplier(multiplier: float = Query(..., ge=1.0, le=10.0)):
    """Set priority multiplier (1.0-10.0, default 2.0)
    
    Higher values mean priority has more effect on scan frequency.
    Example: multiplier=2.0 means priority 50 is scanned 2x more than priority 0.
    """
    try:
        if not sdr_manager:
            raise HTTPException(status_code=503, detail="SDR manager not available")
        sdr_manager.set_priority_multiplier(multiplier)
        return {"message": f"Priority multiplier set to {multiplier}"}
    except Exception as e:
        logger.error(f"Error setting priority multiplier: {e}")
        raise HTTPException(status_code=500, detail="Error setting priority multiplier")


@router.get("/scanner/priority-stats")
async def get_priority_statistics():
    """Get priority-based scanning statistics"""
    try:
        if not sdr_manager:
            raise HTTPException(status_code=503, detail="SDR manager not available")
        
        status = sdr_manager.get_status()
        priority_stats = status.get('priority_stats', {})
        
        # Calculate summary statistics
        if priority_stats:
            total_scans = sum(stat['scans'] for stat in priority_stats.values())
            avg_priority = sum(stat['priority'] for stat in priority_stats.values()) / len(priority_stats)
            
            return {
                "priority_scanning_enabled": status.get('priority_scanning_enabled', False),
                "priority_scan_mode": status.get('priority_scan_mode', 'weighted'),
                "total_scans": total_scans,
                "average_priority": avg_priority,
                "frequency_stats": priority_stats,
                "summary": {
                    "high_priority_frequencies": len([s for s in priority_stats.values() if s['priority'] >= 50]),
                    "medium_priority_frequencies": len([s for s in priority_stats.values() if 25 <= s['priority'] < 50]),
                    "low_priority_frequencies": len([s for s in priority_stats.values() if s['priority'] < 25])
                }
            }
        else:
            return {
                "priority_scanning_enabled": status.get('priority_scanning_enabled', False),
                "message": "No priority statistics available yet. Start scanning to collect data."
            }
            
    except Exception as e:
        logger.error(f"Error getting priority statistics: {e}")
        raise HTTPException(status_code=500, detail="Error getting priority statistics")


# Audio Control Endpoints
@router.post("/audio/enable")
async def enable_audio():
    """Enable audio output to Zello"""
    try:
        if not audio_manager:
            raise HTTPException(status_code=503, detail="Audio manager not available")

        audio_manager.enable_audio()
        return {"message": "Audio output enabled"}

    except Exception as e:
        logger.error(f"Error enabling audio: {e}")
        raise HTTPException(status_code=500, detail="Error enabling audio")


@router.post("/audio/disable")
async def disable_audio():
    """Disable audio output to Zello"""
    try:
        if not audio_manager:
            raise HTTPException(status_code=503, detail="Audio manager not available")

        audio_manager.disable_audio()
        return {"message": "Audio output disabled"}

    except Exception as e:
        logger.error(f"Error disabling audio: {e}")
        raise HTTPException(status_code=500, detail="Error disabling audio")


@router.get("/audio/status")
async def get_audio_status():
    """Get audio system status"""
    try:
        if not audio_manager:
            raise HTTPException(status_code=503, detail="Audio manager not available")

        return audio_manager.get_status()

    except Exception as e:
        logger.error(f"Error getting audio status: {e}")
        raise HTTPException(status_code=500, detail="Error getting audio status")


# Transmission Log Endpoints
@router.get("/transmissions", response_model=List[TransmissionLogResponse])
async def get_transmissions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    frequency: Optional[float] = Query(None),
    hours: Optional[int] = Query(None, ge=1, le=168),  # Max 1 week
    db: Session = Depends(get_db)
):
    """Get transmission logs with optional filtering"""
    try:
        if hours:
            transmissions = await DatabaseManager.get_recent_transmissions(db, hours)
        else:
            transmissions = await DatabaseManager.get_transmission_logs(
                db, skip, limit, frequency
            )
        return transmissions

    except Exception as e:
        logger.error(f"Error getting transmissions: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving transmissions")


@router.get("/transmissions/{transmission_id}/audio")
async def get_transmission_audio(transmission_id: int, db: Session = Depends(get_db)):
    """Get audio file for a transmission"""
    try:
        # Use model class instead of string query
        transmission = db.query(TransmissionLog).filter(TransmissionLog.id == transmission_id).first()
        if not transmission or not transmission.audio_file_path:
            raise HTTPException(status_code=404, detail="Audio file not found")

        # Validate file path to prevent path traversal attacks
        from .config import get_settings
        settings = get_settings()
        recordings_dir = getattr(settings, 'recordings_dir', 'recordings')
        
        try:
            validated_path = validate_file_path(transmission.audio_file_path, recordings_dir)
        except ValueError as e:
            logger.warning(f"Invalid file path detected: {e}")
            raise HTTPException(status_code=403, detail="Invalid file path")

        if not validated_path.exists():
            raise HTTPException(status_code=404, detail="Audio file not found on disk")

        return FileResponse(
            str(validated_path),
            media_type="audio/wav",
            filename=sanitize_filename(f"transmission_{transmission_id}.wav")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting transmission audio: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving audio file")


# System Log Endpoints
@router.get("/logs/system", response_model=List[SystemLogResponse])
async def get_system_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    level: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get system logs with optional level filtering"""
    try:
        logs = await DatabaseManager.get_system_logs(db, skip, limit, level)
        return logs

    except Exception as e:
        logger.error(f"Error getting system logs: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving system logs")


# Settings Management Endpoints
@router.get("/settings")
async def get_settings():
    """Get current application settings"""
    try:
        from .config import get_settings
        settings = get_settings()

        # Convert settings to dictionary
        settings_dict = {
            'sdr_device_index': settings.sdr_device_index,
            'sdr_sample_rate': settings.sdr_sample_rate,
            'sdr_gain': settings.sdr_gain,
            'squelch_threshold': settings.squelch_threshold,
            'audio_sample_rate': settings.audio_sample_rate,
            'audio_channels': settings.audio_channels,
            'audio_chunk_size': settings.audio_chunk_size,
            'audio_device_name': settings.audio_device_name,
            'scan_delay': settings.scan_delay,
            'transmission_timeout': settings.transmission_timeout,
            'log_level': settings.log_level,
            'debug': settings.debug,
            'host': settings.host,
            'port': settings.port
        }

        return settings_dict

    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving settings")


@router.post("/settings")
async def update_settings(settings_data: dict):
    """Update application settings"""
    try:
        from .config import get_settings

        current_settings = get_settings()

        # Update config file
        config_file_path = "config.yaml"
        config_updates = {}

        # Map frontend settings to config keys
        setting_mappings = {
            'sdr_device_index': 'sdr_device_index',
            'sdr_sample_rate': 'sdr_sample_rate',
            'sdr_gain': 'sdr_gain',
            'squelch_threshold': 'squelch_threshold',
            'audio_sample_rate': 'audio_sample_rate',
            'audio_channels': 'audio_channels',
            'audio_chunk_size': 'audio_chunk_size',
            'audio_device_name': 'audio_device_name',
            'scan_delay': 'scan_delay',
            'transmission_timeout': 'transmission_timeout',
            'log_level': 'log_level',
            'host': 'host',
            'port': 'port',
            'debug': 'debug',
        }

        # Prepare config updates
        for setting_key, config_key in setting_mappings.items():
            if setting_key in settings_data:
                config_updates[config_key] = settings_data[setting_key]

        # Update config.yaml file
        await update_config_file(config_file_path, config_updates)

        # Reload settings
        from .config import _settings
        import sys
        sys.modules['src.config']._settings = None  # Force reload
        updated_settings = get_settings()

        # Update runtime settings where possible
        if sdr_manager and 'squelch_threshold' in settings_data:
            sdr_manager.settings.squelch_threshold = settings_data['squelch_threshold']

        if sdr_manager and 'scan_delay' in settings_data:
            sdr_manager.settings.scan_delay = settings_data['scan_delay']

        return {"message": "Settings updated successfully"}

    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating settings: {str(e)}")


async def update_config_file(config_path: str, updates: dict):
    """Update YAML config file with new values (atomic write for safety)"""
    import yaml
    import tempfile
    import shutil
    from pathlib import Path
    
    # File locking (Unix only, Windows will skip)
    try:
        import fcntl
        HAS_FCNTL = True
    except ImportError:
        HAS_FCNTL = False

    # Read existing config file
    config_file = Path(config_path)
    config_data = {}
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                config_data = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Error reading config file: {e}")
            config_data = {}

    # Ensure structure exists
    if 'server' not in config_data:
        config_data['server'] = {}
    if 'sdr' not in config_data:
        config_data['sdr'] = {}
    if 'audio' not in config_data:
        config_data['audio'] = {}
    if 'scanning' not in config_data:
        config_data['scanning'] = {}

    # Map settings to YAML structure
    setting_mappings = {
        'host': ('server', 'host'),
        'port': ('server', 'port'),
        'debug': ('server', 'debug'),
        'log_level': ('server', 'log_level'),
        'sdr_device_index': ('sdr', 'device_index'),
        'sdr_sample_rate': ('sdr', 'sample_rate'),
        'sdr_gain': ('sdr', 'gain'),
        'audio_sample_rate': ('audio', 'sample_rate'),
        'audio_channels': ('audio', 'channels'),
        'audio_chunk_size': ('audio', 'chunk_size'),
        'audio_device_name': ('audio', 'device_name'),
        'scan_delay': ('scanning', 'delay'),
        'squelch_threshold': ('scanning', 'squelch_threshold'),
        'transmission_timeout': ('scanning', 'transmission_timeout'),
    }

    # Update config data
    for setting_key, (section, key) in setting_mappings.items():
        if setting_key in updates:
            # Type conversion
            value = updates[setting_key]
            if setting_key in ['port', 'sdr_device_index', 'audio_sample_rate', 'audio_channels', 'audio_chunk_size']:
                value = int(value)
            elif setting_key in ['sdr_sample_rate', 'sdr_gain', 'scan_delay', 'squelch_threshold', 'transmission_timeout']:
                value = float(value)
            elif setting_key == 'debug':
                value = bool(value) if isinstance(value, str) else value
            config_data[section][key] = value

    # Atomic write: write to temp file, then rename (with file locking on Unix)
    temp_file = Path(config_path + '.tmp')
    try:
        with open(temp_file, 'w') as f:
            if HAS_FCNTL:
                try:
                    # Try to acquire exclusive lock (non-blocking, Unix only)
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (OSError, BlockingIOError):
                    # Lock unavailable - continue without lock (better than failing)
                    pass
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        # Atomic rename (works on Unix and Windows)
        if config_file.exists():
            shutil.move(str(temp_file), str(config_file))
        else:
            temp_file.rename(config_file)
    except Exception as e:
        # Clean up temp file on error
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass
        raise


@router.get("/settings/defaults")
async def get_default_settings():
    """Get default application settings"""
    defaults = {
        'sdr_device_index': 0,
        'sdr_sample_rate': 2048000,
        'sdr_gain': 49.6,
        'squelch_threshold': -50.0,
        'audio_sample_rate': 48000,
        'audio_channels': 1,
        'audio_chunk_size': 1024,
        'audio_device_name': '',
        'scan_delay': 0.1,
        'transmission_timeout': 5.0,
        'log_level': 'INFO',
        'enable_recording': False,
        'enable_notifications': True,
        'enable_sound_alerts': True,
        'max_log_entries': 1000,
        'auto_cleanup_days': 30,
        'priority_multiplier': 2.0
    }
    return defaults


# Version Management Endpoints
@router.get("/versions")
async def get_version_information():
    """Get version information for all components"""
    try:
        from .version_checker import get_version_checker

        version_checker = get_version_checker()
        versions = await version_checker.get_all_versions()

        return versions

    except Exception as e:
        logger.error(f"Error getting version information: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving version information")


@router.get("/versions/updates")
async def check_for_updates():
    """Check for available updates"""
    try:
        from .version_checker import get_version_checker

        version_checker = get_version_checker()
        update_info = await version_checker.check_for_updates()

        return update_info

    except Exception as e:
        logger.error(f"Error checking for updates: {e}")
        raise HTTPException(status_code=500, detail="Error checking for updates")


@router.post("/versions/refresh")
async def refresh_version_cache():
    """Force refresh of version information cache"""
    try:
        from .version_checker import get_version_checker

        version_checker = get_version_checker()
        # Force cache refresh
        version_checker.last_check = None
        versions = await version_checker.get_all_versions()

        return {"message": "Version cache refreshed", "versions": versions}

    except Exception as e:
        logger.error(f"Error refreshing version cache: {e}")
        raise HTTPException(status_code=500, detail="Error refreshing version information")


@router.post("/install/{component}")
async def install_component(component: str):
    """Install a component (Linux-only: zello, pulseaudio, audio_cable) - SECURED"""
    try:
        import subprocess
        import os
        import shutil
        from pathlib import Path

        # Validate component name (allowlist)
        allowed_components = {"zello", "pulseaudio", "audio_cable", "audiocable"}
        component_lower = component.lower()
        if component_lower not in allowed_components:
            raise HTTPException(
                status_code=400, 
                detail=f"Unknown component: {component}. Available: {', '.join(sorted(allowed_components))}"
            )

        # Validate and resolve script path securely
        script_dir = Path(__file__).parent.parent.resolve()
        script_path = script_dir / "setup.py"
        
        # Security: Ensure script is within project directory
        project_root = Path(__file__).parent.parent.resolve()
        if not script_path.resolve().is_relative_to(project_root):
            raise HTTPException(status_code=403, detail="Invalid script path")
        
        if not script_path.exists():
            raise HTTPException(status_code=404, detail="Setup script not found")

        # Use absolute paths and validate Python executable
        python_exe = os.environ.get("PYTHON", "python3")
        if not python_exe or not shutil.which(python_exe):
            python_exe = "python3"

        if component_lower == "zello":
            # Install Zello for Linux - use absolute paths
            result = subprocess.run(
                [python_exe, str(script_path), "--install-zello"],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(project_root),
                env=os.environ.copy()  # Don't inherit potentially unsafe env vars
            )

            if result.returncode == 0:
                return {"message": "Zello installed successfully via Snap/Flatpak", "success": True}
            else:
                error_msg = result.stderr[:200] if result.stderr else "Unknown error"
                return {
                    "message": f"Zello installation failed: {error_msg}. Try: sudo snap install zello-unofficial",
                    "success": False
                }

        elif component_lower in ["pulseaudio", "audio_cable", "audiocable"]:
            # Install PulseAudio virtual devices - use absolute paths
            result = subprocess.run(
                [python_exe, str(script_path), "--install-audio-cable"],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(project_root),
                env=os.environ.copy()
            )

            if result.returncode == 0:
                return {"message": "PulseAudio virtual devices configured successfully", "success": True}
            else:
                error_msg = result.stderr[:200] if result.stderr else "Unknown error"
                return {
                    "message": f"PulseAudio setup failed: {error_msg}. Check if PulseAudio is installed",
                    "success": False
                }

    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Installation timeout - the process took too long")
    except Exception as e:
        logger.error(f"Error installing {component}: {e}")
        raise HTTPException(status_code=500, detail=f"Error installing {component}: {str(e)}")


@router.post("/update/{component}")
async def update_component(component: str):
    """Update a component to the latest version"""
    try:
        # For most components, update is the same as install (they install latest)
        return await install_component(component)

    except Exception as e:
        logger.error(f"Error updating {component}: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating {component}: {str(e)}")


# Maintenance Endpoints
@router.post("/maintenance/cleanup")
async def cleanup_old_data(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """Clean up old logs and data"""
    try:
        deleted_count = await DatabaseManager.cleanup_old_logs(db, days)
        return {"message": f"Cleaned up {deleted_count} old records"}

    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise HTTPException(status_code=500, detail="Error during cleanup")


# Frequency Groups Endpoints
@router.get("/frequencies/groups")
async def get_frequency_groups(db: Session = Depends(get_db)):
    """Get list of all frequency groups"""
    try:
        groups = db.query(Frequency.group).distinct().all()
        # Filter out empty strings and return as list
        group_list = [g[0] for g in groups if g[0] and g[0].strip()]
        return {"groups": sorted(group_list)}
    except Exception as e:
        logger.error(f"Error getting frequency groups: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving frequency groups")


@router.get("/frequencies/tags")
async def get_frequency_tags(db: Session = Depends(get_db)):
    """Get list of all frequency tags"""
    try:
        all_tags = set()
        frequencies = db.query(Frequency.tags).filter(Frequency.tags != "").all()
        for (tags_str,) in frequencies:
            if tags_str:
                tags = [tag.strip() for tag in tags_str.split(",") if tag.strip()]
                all_tags.update(tags)
        return {"tags": sorted(list(all_tags))}
    except Exception as e:
        logger.error(f"Error getting frequency tags: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving frequency tags")


# Health Monitoring Endpoints
@router.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    try:
        import psutil
        import time
        from datetime import datetime
        
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": time.time() - (getattr(health_check, '_start_time', time.time())),
            "system": {
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage('/').percent if hasattr(psutil, 'disk_usage') else None
            },
            "services": {}
        }
        
        # Check SDR manager
        if sdr_manager:
            health_status["services"]["sdr"] = {
                "connected": sdr_manager.sdr_device is not None,
                "scanning": sdr_manager.is_scanning,
                "frequencies_loaded": len(sdr_manager.scan_list)
            }
        else:
            health_status["services"]["sdr"] = {"status": "not_initialized"}
        
        # Check audio manager
        if audio_manager:
            health_status["services"]["audio"] = {
                "enabled": audio_manager.audio_enabled,
                "device_initialized": audio_manager.virtual_device.pyaudio_instance is not None if audio_manager.virtual_device else False
            }
        else:
            health_status["services"]["audio"] = {"status": "not_initialized"}
        
        # Determine overall health
        if health_status["system"]["cpu_percent"] > 90 or health_status["system"]["memory_percent"] > 90:
            health_status["status"] = "degraded"
        
        return health_status
        
    except Exception as e:
        logger.error(f"Error in health check: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/health/detailed")
async def detailed_health_check(db: Session = Depends(get_db)):
    """Detailed health check with database and system metrics"""
    try:
        import psutil
        from datetime import datetime, timedelta
        
        health = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "system": {
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "cpu_count": psutil.cpu_count(),
                "memory": {
                    "total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
                    "available_gb": round(psutil.virtual_memory().available / (1024**3), 2),
                    "percent": psutil.virtual_memory().percent,
                    "used_gb": round(psutil.virtual_memory().used / (1024**3), 2)
                }
            },
            "database": {},
            "services": {}
        }
        
        # Database health
        try:
            from .models import Frequency, TransmissionLog
            freq_count = db.query(Frequency).count()
            recent_transmissions = db.query(TransmissionLog).filter(
                TransmissionLog.timestamp >= datetime.now() - timedelta(hours=24)
            ).count()
            
            health["database"] = {
                "status": "healthy",
                "frequencies": freq_count,
                "recent_transmissions_24h": recent_transmissions
            }
        except Exception as e:
            health["database"] = {"status": "error", "error": str(e)}
            health["status"] = "degraded"
        
        # SDR service health
        if sdr_manager:
            health["services"]["sdr"] = {
                "status": "healthy" if sdr_manager.sdr_device else "no_device",
                "scanning": sdr_manager.is_scanning,
                "current_frequency": sdr_manager.current_frequency,
                "frequencies_loaded": len(sdr_manager.scan_list)
            }
        else:
            health["services"]["sdr"] = {"status": "not_initialized"}
        
        # Audio service health
        if audio_manager:
            health["services"]["audio"] = {
                "status": "healthy",
                "enabled": audio_manager.audio_enabled,
                "device_initialized": audio_manager.virtual_device.pyaudio_instance is not None if audio_manager.virtual_device else False
            }
        else:
            health["services"]["audio"] = {"status": "not_initialized"}
        
        return health
        
    except Exception as e:
        logger.error(f"Error in detailed health check: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# Recording Management Endpoints
@router.get("/recordings", response_model=List[RecordingResponse])
async def get_recordings(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    favorite_only: bool = Query(False),
    frequency: Optional[float] = Query(None, description="Filter by frequency in Hz"),
    group: Optional[str] = Query(None, description="Filter by frequency group"),
    format: Optional[str] = Query(None, description="Filter by format (WAV, MP3)"),
    search: Optional[str] = Query(None, description="Search in filename, description, group, tags, modulation"),
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    db: Session = Depends(get_db)
):
    """Get all recordings with filtering and search"""
    try:
        # Parse dates if provided
        start_dt = None
        end_dt = None
        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format. Use ISO format.")
        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date format. Use ISO format.")

        recordings = await DatabaseManager.get_recordings(
            db=db,
            skip=skip,
            limit=limit,
            favorite_only=favorite_only,
            frequency=frequency,
            group=group,
            format=format,
            search=search,
            start_date=start_dt,
            end_date=end_dt
        )
        return recordings
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving recordings: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving recordings")


@router.get("/recordings/{recording_id}", response_model=RecordingResponse)
async def get_recording(recording_id: int, db: Session = Depends(get_db)):
    """Get a specific recording by ID"""
    try:
        recording = await DatabaseManager.get_recording_by_id(db, recording_id)
        if not recording:
            raise HTTPException(status_code=404, detail="Recording not found")
        return recording
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving recording: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving recording")


@router.get("/recordings/{recording_id}/stream")
async def stream_recording(recording_id: int, db: Session = Depends(get_db)):
    """Stream audio recording file"""
    try:
        recording = await DatabaseManager.get_recording_by_id(db, recording_id)
        if not recording:
            raise HTTPException(status_code=404, detail="Recording not found")
        
        # Validate file path
        from .config import get_settings
        settings = get_settings()
        recordings_dir = getattr(settings, 'recordings_dir', 'recordings')
        if not validate_file_path(recording.filepath, recordings_dir):
            raise HTTPException(status_code=403, detail="Invalid file path")
        
        if not os.path.exists(recording.filepath):
            raise HTTPException(status_code=404, detail="Recording file not found")
        
        # Determine media type
        media_type = "audio/mpeg" if recording.format == "MP3" else "audio/wav"
        
        return FileResponse(
            recording.filepath,
            media_type=media_type,
            filename=recording.filename,
            headers={"Content-Disposition": f'inline; filename="{recording.filename}"'}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming recording: {e}")
        raise HTTPException(status_code=500, detail="Error streaming recording")


@router.get("/recordings/{recording_id}/download")
async def download_recording(recording_id: int, db: Session = Depends(get_db)):
    """Download recording file"""
    try:
        recording = await DatabaseManager.get_recording_by_id(db, recording_id)
        if not recording:
            raise HTTPException(status_code=404, detail="Recording not found")
        
        # Validate file path
        from .config import get_settings
        settings = get_settings()
        recordings_dir = getattr(settings, 'recordings_dir', 'recordings')
        if not validate_file_path(recording.filepath, recordings_dir):
            raise HTTPException(status_code=403, detail="Invalid file path")
        
        if not os.path.exists(recording.filepath):
            raise HTTPException(status_code=404, detail="Recording file not found")
        
        # Determine media type
        media_type = "audio/mpeg" if recording.format == "MP3" else "audio/wav"
        
        return FileResponse(
            recording.filepath,
            media_type=media_type,
            filename=recording.filename,
            headers={"Content-Disposition": f'attachment; filename="{recording.filename}"'}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading recording: {e}")
        raise HTTPException(status_code=500, detail="Error downloading recording")


@router.patch("/recordings/{recording_id}", response_model=RecordingResponse)
async def update_recording(
    recording_id: int,
    update_data: RecordingUpdate,
    db: Session = Depends(get_db)
):
    """Update recording (favorite, notes, description)"""
    try:
        recording = await DatabaseManager.update_recording(
            db, recording_id, update_data.model_dump(exclude_unset=True)
        )
        if not recording:
            raise HTTPException(status_code=404, detail="Recording not found")
        return recording
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating recording: {e}")
        raise HTTPException(status_code=500, detail="Error updating recording")


@router.delete("/recordings/{recording_id}")
async def delete_recording(recording_id: int, db: Session = Depends(get_db)):
    """Delete a recording and its file"""
    try:
        recording = await DatabaseManager.get_recording_by_id(db, recording_id)
        if not recording:
            raise HTTPException(status_code=404, detail="Recording not found")
        
        # Delete file if it exists
        if os.path.exists(recording.filepath):
            try:
                os.remove(recording.filepath)
                # Also try to delete JSON metadata file
                json_path = recording.filepath.rsplit('.', 1)[0] + '.json'
                if os.path.exists(json_path):
                    os.remove(json_path)
            except Exception as e:
                logger.warning(f"Failed to delete recording file: {e}")
        
        # Delete database record
        await DatabaseManager.delete_recording(db, recording_id)
        return {"message": "Recording deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting recording: {e}")
        raise HTTPException(status_code=500, detail="Error deleting recording")


@router.get("/recordings/stats/summary")
async def get_recording_stats(db: Session = Depends(get_db)):
    """Get recording statistics summary"""
    try:
        from .models import Recording
        from sqlalchemy import func
        
        total_recordings = db.query(Recording).count()
        total_duration = db.query(func.sum(Recording.duration_seconds)).scalar() or 0.0
        total_size = db.query(func.sum(Recording.file_size_bytes)).scalar() or 0
        favorite_count = db.query(Recording).filter(Recording.is_favorite == True).count()
        
        # Get recordings by format
        wav_count = db.query(Recording).filter(Recording.format == "WAV").count()
        mp3_count = db.query(Recording).filter(Recording.format == "MP3").count()
        
        # Get most recorded frequency
        most_recorded = db.query(
            Recording.frequency_hz,
            func.count(Recording.id).label('count')
        ).group_by(Recording.frequency_hz).order_by(func.count(Recording.id).desc()).first()
        
        return {
            "total_recordings": total_recordings,
            "total_duration_hours": round(total_duration / 3600, 2),
            "total_size_gb": round(total_size / (1024**3), 2),
            "favorite_count": favorite_count,
            "wav_count": wav_count,
            "mp3_count": mp3_count,
            "most_recorded_frequency": most_recorded[0] if most_recorded else None,
            "most_recorded_count": most_recorded[1] if most_recorded else 0
        }
    except Exception as e:
        logger.error(f"Error getting recording stats: {e}")
        raise HTTPException(status_code=500, detail="Error getting recording stats")