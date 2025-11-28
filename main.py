#!/usr/bin/env python3
"""
sdr2zello - RTL-SDR to Zello Bridge
Main application entry point
"""

import asyncio
import signal
import sys
import logging
from pathlib import Path
import uvicorn
from src.app import create_app
from src.config import get_settings

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/sdr2zello.log', mode='a') if Path('logs').exists() else logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info("Shutdown signal received, stopping sdr2zello...")
    sys.exit(0)


async def main():
    """Main application entry point"""
    try:
        # Set up signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Create logs directory if it doesn't exist
        Path("logs").mkdir(exist_ok=True)

        logger.info("Starting sdr2zello...")
        
        settings = get_settings()
        app = await create_app()

        config = uvicorn.Config(
            app=app,
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level.lower(),
            reload=settings.debug
        )

        server = uvicorn.Server(config)
        await server.serve()

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
    except Exception as e:
        logger.error(f"Error starting application: {e}")
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nsdr2zello stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)