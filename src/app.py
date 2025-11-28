"""
FastAPI application factory and main app configuration
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from typing import List, Dict, Any
import json
import logging
from datetime import datetime, timedelta

from .config import get_settings
from .sdr import SDRManager
from .audio import AudioManager
from .database import init_db
from .api import router as api_router
from .models import Frequency, TransmissionLog
from .database import DatabaseManager, get_async_db

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for real-time updates"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        """Broadcast message to all connections in parallel"""
        if not self.active_connections:
            return
        
        # Create tasks for parallel execution
        tasks = []
        for connection in self.active_connections:
            tasks.append(self._send_safe(connection, message))
        
        # Execute all sends in parallel
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _send_safe(self, websocket: WebSocket, message: str):
        """Safely send message to a websocket, handling errors"""
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error broadcasting to WebSocket: {e}")
            # Remove dead connections
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)


# Global managers
manager = ConnectionManager()
sdr_manager = None
audio_manager = None

# Track active transmissions for end detection
active_transmissions: Dict[float, Dict[str, Any]] = {}

# Track active transmissions for end detection
active_transmissions: Dict[float, Dict[str, Any]] = {}


async def handle_transmission_event(transmission):
    """Handle transmission events from SDR manager"""
    try:
        # Get frequency details from database
        frequency_metadata = {}
        async with get_async_db() as db:
            from .models import Frequency
            freq_obj = db.query(Frequency).filter(Frequency.frequency == transmission.frequency).first()
            if freq_obj:
                frequency_metadata = {
                    'friendly_name': freq_obj.friendly_name or '',
                    'description': freq_obj.description or '',
                    'group': freq_obj.group or '',
                    'tags': freq_obj.tags or '',
                    'modulation': freq_obj.modulation or 'FM',
                    'priority': freq_obj.priority or 0
                }
        
        # Broadcast transmission start
        await manager.broadcast(json.dumps({
            'type': 'transmission_start',
            'frequency': transmission.frequency,
            'signal_strength': transmission.signal_strength,
            'timestamp': transmission.timestamp.isoformat(),
            'modulation': frequency_metadata.get('modulation', 'FM'),
            'description': frequency_metadata.get('description', '')
        }))

        # Prepare metadata for recording
        recording_metadata = {
            **frequency_metadata,
            'signal_strength': transmission.signal_strength,
            'timestamp': transmission.timestamp
        }

        # Start audio recording with metadata
        if audio_manager:
            await audio_manager.handle_transmission_start(transmission.frequency, recording_metadata)

        # Process audio data if available
        if transmission.audio_data is not None and len(transmission.audio_data) > 0:
            if audio_manager:
                await audio_manager.handle_transmission_audio(transmission.audio_data, transmission.signal_strength)
        
        # Save transmission to database first to get ID
        transmission_log_id = None
        async with get_async_db() as db:
            transmission_data = {
                'frequency': transmission.frequency,
                'signal_strength': transmission.signal_strength,
                'timestamp': transmission.timestamp,
                'modulation': frequency_metadata.get('modulation', 'FM'),
                'duration': transmission.duration,
                'zello_audio_enabled': audio_manager.audio_enabled if audio_manager else False
            }
            transmission_log = await DatabaseManager.create_transmission_log(db, transmission_data)
            transmission_log_id = transmission_log.id
        
        # Track active transmission
        active_transmissions[transmission.frequency] = {
            'start_time': transmission.timestamp,
            'metadata': recording_metadata,
            'last_signal': transmission.signal_strength,
            'peak_signal': transmission.signal_strength,
            'transmission_log_id': transmission_log_id
        }
        
        # Start monitoring for transmission end
        asyncio.create_task(monitor_transmission_end(transmission.frequency, recording_metadata))

        logger.info(f"Handled transmission event on {transmission.frequency / 1e6:.3f} MHz")

    except Exception as e:
        logger.error(f"Error handling transmission event: {e}")


async def handle_signal_strength_update(signal_data):
    """Handle signal strength updates from SDR manager"""
    try:
        # Broadcast signal strength update
        await manager.broadcast(json.dumps({
            'type': 'signal_strength',
            'frequency': signal_data['frequency'],
            'signal_strength': signal_data['signal_strength'],
            'timestamp': signal_data['timestamp']
        }))

        # Update current frequency if different
        if sdr_manager:
            await manager.broadcast(json.dumps({
                'type': 'frequency_update',
                'frequency': signal_data['frequency'],
                'timestamp': signal_data['timestamp']
            }))
        
        # Update active transmission tracking
        freq = signal_data['frequency']
        if freq in active_transmissions:
            active_transmissions[freq]['last_signal'] = signal_data['signal_strength']
            active_transmissions[freq]['peak_signal'] = max(
                active_transmissions[freq]['peak_signal'],
                signal_data['signal_strength']
            )

    except Exception as e:
        logger.error(f"Error handling signal strength update: {e}")


async def monitor_transmission_end(frequency: float, metadata: Dict[str, Any]):
    """Monitor for transmission end based on timeout and signal drop"""
    from .config import get_settings
    settings = get_settings()
    timeout = settings.transmission_timeout
    
    try:
        start_time = datetime.now()
        
        while True:
            await asyncio.sleep(0.5)  # Check every 500ms
            
            # Check if transmission is still active
            if frequency not in active_transmissions:
                break
            
            transmission_info = active_transmissions[frequency]
            elapsed = (datetime.now() - start_time).total_seconds()
            last_signal = transmission_info['last_signal']
            
            # End transmission if:
            # 1. Signal dropped below threshold for timeout period, OR
            # 2. Maximum duration exceeded (safety limit)
            if last_signal < settings.squelch_threshold:
                # Signal dropped - wait for timeout
                if elapsed >= timeout:
                    # Transmission ended
                    await end_transmission(frequency, transmission_info, metadata)
                    break
            else:
                # Signal still active - reset timeout
                start_time = datetime.now()
            
            # Safety limit: don't record longer than 5 minutes
            if elapsed > 300:
                await end_transmission(frequency, transmission_info, metadata)
                break
                
    except Exception as e:
        logger.error(f"Error monitoring transmission end: {e}")
        # Clean up on error
        if frequency in active_transmissions:
            del active_transmissions[frequency]


async def end_transmission(frequency: float, transmission_info: Dict[str, Any], metadata: Dict[str, Any]):
    """Handle transmission end"""
    try:
        if frequency not in active_transmissions:
            return
        
        start_time = transmission_info['start_time']
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Update metadata with final stats
        final_metadata = metadata.copy()
        final_metadata['signal_strength'] = transmission_info['last_signal']
        final_metadata['peak_signal_strength'] = transmission_info['peak_signal']
        
        # Get Zello status from audio manager
        zello_status = {
            'zello_sent': False,
            'zello_success': False,
            'zello_error': '',
            'zello_audio_enabled': False
        }
        
        if audio_manager:
            await audio_manager.handle_transmission_end(frequency, end_time, final_metadata)
            # Get Zello status from audio manager
            if hasattr(audio_manager, 'current_zello_status'):
                zello_status = audio_manager.current_zello_status.copy()
        
        # Update transmission log with Zello status and duration
        transmission_log_id = transmission_info.get('transmission_log_id')
        if transmission_log_id:
            async with get_async_db() as db:
                update_data = {
                    'duration': duration,
                    'zello_sent': zello_status.get('sent', False),
                    'zello_success': zello_status.get('success', False),
                    'zello_error': zello_status.get('error', ''),
                    'zello_audio_enabled': zello_status.get('audio_enabled', False)
                }
                await DatabaseManager.update_transmission_log(db, transmission_log_id, update_data)
        
        # Remove from active transmissions
        if frequency in active_transmissions:
            del active_transmissions[frequency]
            
    except Exception as e:
        logger.error(f"Error ending transmission: {e}")


async def handle_audio_completion(audio_data):
    """Handle completed audio transmission"""
    try:
        # Get metadata if available
        metadata = audio_data.get('metadata', {})
        
        # Broadcast transmission end with full metadata
        await manager.broadcast(json.dumps({
            'type': 'transmission_end',
            'frequency': audio_data['frequency'],
            'duration': audio_data['duration'],
            'timestamp': audio_data['timestamp'].isoformat(),
            'audio_file': audio_data.get('audio_file', ''),
            'description': metadata.get('description', ''),
            'group': metadata.get('group', ''),
            'signal_strength': metadata.get('signal_strength', 0.0),
            'modulation': metadata.get('modulation', 'FM')
        }))

        logger.info(f"Audio transmission completed: {audio_data['frequency'] / 1e6:.3f} MHz, {audio_data['duration']:.2f}s")

    except Exception as e:
        logger.error(f"Error handling audio completion: {e}")


async def create_app() -> FastAPI:
    """Application factory"""
    settings = get_settings()

    app = FastAPI(
        title="sdr2zello",
        description="RTL-SDR to Zello Bridge with Web Interface",
        version="1.0.0",
        debug=settings.debug
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else ["http://localhost:8000", "http://127.0.0.1:8000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"]
    )

    # Add security headers middleware
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if not settings.debug:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    # Initialize database
    await init_db()

    # Initialize managers
    global sdr_manager, audio_manager
    sdr_manager = SDRManager()
    audio_manager = AudioManager()

    # Set up callbacks for real-time communication
    sdr_manager.set_transmission_callback(handle_transmission_event)
    sdr_manager.set_signal_strength_callback(handle_signal_strength_update)
    audio_manager.set_transmission_callback(handle_audio_completion)

    # Mount static files
    try:
        app.mount("/static", StaticFiles(directory=settings.static_files_path), name="static")
    except RuntimeError:
        logger.warning("Static files directory not found, creating basic structure")

    # Setup templates
    templates = Jinja2Templates(directory=settings.templates_path if settings.templates_path else "templates")

    # Set manager references in API module
    from .api import set_managers
    set_managers(sdr_manager, audio_manager)

    # Include API routes
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        """Main dashboard"""
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/frequencies", response_class=HTMLResponse)
    async def frequencies_page(request: Request):
        """Frequencies management page"""
        return templates.TemplateResponse("frequencies.html", {"request": request})

    @app.get("/monitor", response_class=HTMLResponse)
    async def monitor_page(request: Request):
        """Real-time monitor page"""
        return templates.TemplateResponse("monitor.html", {"request": request})

    @app.get("/logs", response_class=HTMLResponse)
    async def logs_page(request: Request):
        """Transmission logs page"""
        return templates.TemplateResponse("logs.html", {"request": request})

    @app.get("/recordings", response_class=HTMLResponse)
    async def recordings_page(request: Request):
        """Recordings page"""
        return templates.TemplateResponse("recordings.html", {"request": request})

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint for real-time updates"""
        await manager.connect(websocket)
        try:
            while True:
                data = await websocket.receive_text()
                # Handle incoming WebSocket messages if needed
                # Only log at debug level to avoid exposing sensitive data
                logger.debug(f"Received WebSocket message (length: {len(data)})")
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    @app.on_event("startup")
    async def startup_event():
        """Initialize services on startup"""
        logger.info("Starting sdr2zello application")
        try:
            await sdr_manager.initialize()
            await audio_manager.initialize()
            logger.info("All managers initialized successfully")
        except Exception as e:
            logger.error(f"Error during startup: {e}")

    @app.on_event("shutdown")
    async def shutdown_event():
        """Cleanup on shutdown"""
        logger.info("Shutting down sdr2zello application")
        if sdr_manager:
            await sdr_manager.cleanup()
        if audio_manager:
            await audio_manager.cleanup()

    return app


async def broadcast_status_update(status_data: dict):
    """Broadcast status updates to all connected WebSocket clients"""
    message = json.dumps(status_data)
    await manager.broadcast(message)