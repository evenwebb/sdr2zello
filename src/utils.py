"""
Utility functions for sdr2zello
Common error handling and helper functions
"""

import logging
from typing import Callable, Any, Optional
from functools import wraps

logger = logging.getLogger(__name__)


def handle_api_errors(func: Callable) -> Callable:
    """
    Decorator for consistent API error handling
    
    Usage:
        @handle_api_errors
        async def my_endpoint():
            ...
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
            from fastapi import HTTPException
            raise HTTPException(status_code=500, detail=f"Error in {func.__name__}: {str(e)}")
    return wrapper


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers, returning default if denominator is zero"""
    if denominator == 0 or denominator is None:
        return default
    return numerator / denominator


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value between min and max"""
    return max(min_val, min(max_val, value))

