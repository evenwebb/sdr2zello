"""
Security utilities for sdr2zello
Provides path validation, input sanitization, and security helpers
"""

from pathlib import Path
from typing import Optional
import logging
import re

logger = logging.getLogger(__name__)


def validate_file_path(file_path: str, base_dir: str) -> Path:
    """
    Validate that a file path is within the base directory (prevents path traversal).
    
    Args:
        file_path: The file path to validate
        base_dir: The base directory that the file must be within
        
    Returns:
        Resolved Path object if valid
        
    Raises:
        ValueError: If the path is outside the base directory
    """
    try:
        base = Path(base_dir).resolve()
        file = Path(file_path).resolve()
        
        # Check if file is within base directory
        try:
            file.relative_to(base)
            return file
        except ValueError:
            raise ValueError(f"File path {file_path} is outside allowed directory {base_dir}")
            
    except Exception as e:
        logger.error(f"Path validation error: {e}")
        raise ValueError(f"Invalid file path: {file_path}")


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to prevent directory traversal and other attacks.
    
    Args:
        filename: The filename to sanitize
        
    Returns:
        Sanitized filename
    """
    # Remove path components
    filename = Path(filename).name
    
    # Remove any characters that aren't alphanumeric, dash, underscore, or dot
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    
    # Prevent hidden files and special names
    if filename.startswith('.') or filename in ['..', '.', '']:
        filename = f"file_{filename}"
    
    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:250] + ('.' + ext if ext else '')
    
    return filename


def validate_frequency(frequency: float) -> bool:
    """
    Validate frequency is within reasonable range.
    
    Args:
        frequency: Frequency in Hz
        
    Returns:
        True if valid, False otherwise
    """
    # Valid range: 0 to 10 GHz (reasonable for RTL-SDR)
    return 0.0 <= frequency <= 10e9


def validate_modulation(modulation: str) -> bool:
    """
    Validate modulation type.
    
    Args:
        modulation: Modulation type string
        
    Returns:
        True if valid, False otherwise
    """
    valid_modulations = {'AM', 'FM', 'USB', 'LSB', 'CW', 'NFM', 'WFM'}
    return modulation.upper() in valid_modulations


def sanitize_env_value(value: str) -> str:
    """
    Sanitize environment variable value to prevent injection.
    
    Args:
        value: Environment variable value
        
    Returns:
        Sanitized value
    """
    # Remove newlines and null bytes
    value = value.replace('\n', '').replace('\r', '').replace('\0', '')
    
    # Limit length
    if len(value) > 10000:
        value = value[:10000]
    
    return value


def validate_env_key(key: str) -> bool:
    """
    Validate environment variable key.
    
    Args:
        key: Environment variable key
        
    Returns:
        True if valid, False otherwise
    """
    # Must start with letter or underscore, followed by alphanumeric/underscore
    pattern = r'^[A-Za-z_][A-Za-z0-9_]*$'
    return bool(re.match(pattern, key)) and len(key) <= 100

