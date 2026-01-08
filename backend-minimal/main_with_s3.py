"""
Nova Sonic Main Application with S3 Conversation Storage

This is the main application file that integrates S3 conversation storage
with the existing Nova Sonic functionality. It uses the ConversationStorageWrapper
to add S3 storage without modifying the original ConnectionManager.
"""

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from nova_sonic_simple import SimpleNovaSonic
import logging
import os
import wave
from datetime import datetime
import uuid
import json
import time
from api.apps import routers as app_routers

# Import S3 conversation storage components
from services.conversation_wrapper import ConversationStorageWrapper
from services.s3_conversation_storage import S3StorageService

# Import original ConnectionManager
from main import ConnectionManager

CHUNK_SIZE = 4096

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create debug directory if it doesn't exist
DEBUG_DIR = "debug_audio"
os.makedirs(DEBUG_DIR, exist_ok=True)

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize S3 storage service for startup validation
s3_service = S3StorageService()

# Validate S3 connectivity during startup
@app.on_event("startup")
async def startup_event():
    """Validate S3 connectivity during application startup."""
    logger.info("Starting Nova Sonic with S3 Conversation Storage...")
    
    if s3_service.enabled:
        connectivity = s3_service.validate_startup_connectivity()
        if connectivity:
            logger.info(f"✅ S3 conversation storage ready: s3://{s3_service.bucket_name}/{s3_service.s3_prefix}/")
        else:
            logger.warning("⚠️  S3 connectivity validation failed - conversations will not be stored")
    else:
        logger.info("S3 conversation storage is disabled")

# Create ConnectionManager with S3 wrapper
SAVE_DEBUG_AUDIO = os.getenv('SAVE_DEBUG_AUDIO', 'false').lower() == 'true'
base_manager = ConnectionManager(save_debug_audio=SAVE_DEBUG_AUDIO)
manager = ConversationStorageWrapper(base_manager)

# Log wrapper initialization
logger.info(f"🔧 ConversationStorageWrapper initialized")
logger.info(f"🔧 S3 Storage enabled: {manager.s3_storage.enabled}")
logger.info(f"🔧 S3 Bucket: {manager.s3_storage.bucket_name}")
logger.info(f"🔧 S3 Prefix: {manager.s3_storage.s3_prefix}")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    logger.info("New WebSocket connection request")
    await manager.wrap_connect(websocket)
    
    # Send tool configurations
    tool_configs = manager.nova_client.tool_manager.get_tool_configs() if manager.nova_client else []
    await websocket.send_text(json.dumps({
        "event": {
            "init": {
                "toolConfigs": tool_configs
            }
        }
    }))
    
    # Start processing audio responses and events in background
    process_task = asyncio.create_task(manager.process_audio_responses())
    event_task = asyncio.create_task(manager.process_events())
    
    try:
        while True:
            message = await websocket.receive()
            
            if "bytes" in message:
                # Handle audio data
                audio_data = message["bytes"]
                logger.debug(f"Received audio data of size {len(audio_data)} bytes")
                await manager.receive_audio(audio_data)
            elif "text" in message:
                # Parse the message to check for different event types
                try:
                    event_data = json.loads(message["text"])
                    logger.info(f"Received text message: {event_data}")
                    
                    if "event" in event_data:
                        event = event_data["event"]
                        if "ui_interaction" in event:
                            logger.info(f"Handling UI interaction: {event['ui_interaction']}")
                            await manager.handle_ui_interaction(event["ui_interaction"])
                        elif "toolUse" in event:
                            logger.info(f"Handling tool use: {event['toolUse']}")
                            await manager.handle_tool_use(event_data)
                        elif "textInput" in event:
                            # Add user message to history with automatic classification
                            user_text = event["textInput"].get("content", "")
                            manager.add_message_from_event(event_data, user_text, event_type="textInput")
                        else:
                            # Handle string commands
                            command = message["text"]
                            if command == "start_audio":
                                await manager.start_audio()
                            elif command == "stop_audio":
                                await manager.stop_audio()
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse message: {e}")
                    # Handle as regular command if not JSON
                    command = message["text"]
                    if command == "start_audio":
                        await manager.start_audio()
                    elif command == "stop_audio":
                        await manager.stop_audio()
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        logger.exception(e)  # This will print the full stack trace
    finally:
        logger.info("Cleaning up WebSocket connection")
        process_task.cancel()
        event_task.cancel()
        await manager.wrap_disconnect()  # Use wrapper's disconnect method

# Health check endpoint that includes S3 connectivity status
@app.get("/health")
async def health_check():
    """Health check endpoint with S3 connectivity status."""
    s3_status = "disabled"
    if s3_service.enabled:
        connectivity = s3_service._validate_s3_connectivity()
        s3_status = "connected" if connectivity else "error"
    
    return {
        "status": "healthy",
        "s3_conversation_storage": {
            "enabled": s3_service.enabled,
            "status": s3_status,
            "bucket": s3_service.bucket_name if s3_service.enabled else None,
            "prefix": s3_service.s3_prefix if s3_service.enabled else None
        },
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }



# Include API routers
for r in app_routers:
    app.include_router(r)

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Nova Sonic with S3 Conversation Storage")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")