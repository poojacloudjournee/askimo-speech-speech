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
from services.role_classifier import RoleClassifier

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

class ConnectionManager:
    def __init__(self, save_debug_audio=True):
        self.nova_client = None
        self.active_connection = None
        self.audio_content_started = False
        self.debug_input_file = None
        self.debug_output_file = None
        self.received_chunks = 0
        self.sent_chunks = 0
        self.current_content_name = None
        self.current_tool_use_id = None
        self.current_tool_name = None
        self.last_audio_chunk_time = 0  # Track timing of audio chunks
        self.audio_chunk_threshold = 0.1  # 100ms threshold for audio chunks
        self.save_debug_audio = save_debug_audio  # <--- New config option
        # --- Chat history ---
        self.chat_history = []  # List of dicts: {role, text, contentName}
        self.max_history = 50   # Increased rolling window size to capture more conversation
        # --- Message deduplication ---
        self.processed_messages = set()  # Track processed message hashes to prevent duplicates
        # --- Role classification ---
        self.role_classifier = RoleClassifier()
        self.current_speaker_role = None  # Track current speaker from contentStart events
        # --- Track current speaker role from contentStart events ---
        self.current_speaker_role = None  # Track who is currently speaking

    def add_history(self, role, text, source_info=None):
        """
        Add a message to the rolling chat history with role validation.
        
        Args:
            role: The role of the message sender ("USER" or "ASSISTANT")
            text: The message text content
            source_info: Optional dict with source information for debugging
        """
        # Validate and correct role if needed
        if not self.role_classifier.validate_role(role):
            logger.warning(f"Invalid role '{role}' provided to add_history. Correcting to valid role.")
            role = self.role_classifier.correct_invalid_role(role)
        
        content_name = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        message = {
            'role': role,
            'text': text,
            'contentName': content_name,
            'timestamp': timestamp
        }
        
        # Add source info for debugging if provided
        if source_info:
            message['source_info'] = source_info
        
        self.chat_history.append(message)
        
        # Keep only the last N messages
        if len(self.chat_history) > self.max_history:
            removed_messages = len(self.chat_history) - self.max_history
            self.chat_history = self.chat_history[-self.max_history:]
            logger.info(f"🗑️ Removed {removed_messages} old messages from history (keeping last {self.max_history})")
        
        logger.info(f"💬 Added to history: {role} - '{text[:100]}...' (Total: {len(self.chat_history)} messages)")
        logger.debug(f"Added message to history: role={role}, text_length={len(text)}, source={source_info}")

    def get_history(self):
        """Get the current rolling chat history."""
        return self.chat_history.copy()
    
    def add_message_from_event(self, event_data, text, event_type=None, source="websocket"):
        """
        Add a message to history with automatic role classification based on event data.
        
        Args:
            event_data: The event data structure
            text: The message text content
            event_type: Optional explicit event type
            source: The source of the message (default: "websocket")
        """
        # Classify the role based on event data
        if event_type:
            role = self.role_classifier.classify_message_role(
                source=source,
                event_type=event_type,
                content=event_data
            )
        else:
            role = self.role_classifier.classify_websocket_event(event_data)
        
        # Create source info for debugging
        source_info = {
            "source": source,
            "event_type": event_type,
            "has_event_data": bool(event_data)
        }
        
        # Add to history with classified role
        self.add_history(role, text, source_info)
        
        logger.debug(f"Auto-classified message: role={role}, event_type={event_type}, source={source}")

    def _create_debug_files(self):
        if not self.save_debug_audio:
            self.debug_input_file = None
            self.debug_output_file = None
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        input_path = os.path.join(DEBUG_DIR, f"input_{timestamp}.wav")
        output_path = os.path.join(DEBUG_DIR, f"output_{timestamp}.wav")

        # Create WAV file for input audio (16kHz)
        self.debug_input_file = wave.open(input_path, 'wb')
        self.debug_input_file.setnchannels(1)
        self.debug_input_file.setsampwidth(2)  # 16-bit
        self.debug_input_file.setframerate(16000)
        
        # Create WAV file for output audio (24kHz)
        self.debug_output_file = wave.open(output_path, 'wb')
        self.debug_output_file.setnchannels(1)
        self.debug_output_file.setsampwidth(2)  # 16-bit
        self.debug_output_file.setframerate(24000)

        logger.info(f"Created debug files: {input_path} and {output_path}")

    def _close_debug_files(self):
        if not self.save_debug_audio:
            self.debug_input_file = None
            self.debug_output_file = None
            return
        if self.debug_input_file:
            self.debug_input_file.close()
            self.debug_input_file = None
        if self.debug_output_file:
            self.debug_output_file.close()
            self.debug_output_file = None
        logger.info(f"Debug stats - Received chunks: {self.received_chunks}, Sent chunks: {self.sent_chunks}")
        self.received_chunks = 0
        self.sent_chunks = 0

    async def process_tool_use(self, tool_name, tool_use_content):
        """Process tool use requests and return results"""
        logger.info(f"Processing tool use: {tool_name}")
        
        try:
            # Use the tool manager to execute the tool
            result = await self.nova_client.tool_manager.execute_tool(tool_name, tool_use_content)
            return result
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            return {"error": f"Tool execution failed: {str(e)}"}

    async def handle_tool_use(self, event_data):
        """Handle tool use events"""
        try:
            tool_use = event_data["event"]["toolUse"]
            self.current_tool_use_id = tool_use["toolUseId"]
            self.current_tool_name = tool_use.get("toolName")
            tool_content = json.loads(tool_use.get("content", "{}"))
            
            # Add tool use to conversation history as USER message
            tool_use_text = f"User requested tool: {self.current_tool_name}"
            self.add_message_from_event(event_data, tool_use_text, event_type="toolUse")
            
            # Process the tool use
            result = await self.process_tool_use(self.current_tool_name, tool_content)
            logger.info(f"Tool result received from implementation: {result}")
            
            if "error" not in result:
                # Add tool result to conversation history as ASSISTANT message
                tool_result_text = f"Tool {self.current_tool_name} executed successfully"
                tool_result_event = {
                    "event": {
                        "toolResult": {
                            "promptName": tool_use["promptName"],
                            "contentName": str(uuid.uuid4()),
                            "content": json.dumps(result["model_result"])
                        }
                    }
                }
                self.add_message_from_event(tool_result_event, tool_result_text, event_type="toolResult")
                
                # Then prepare and send the UI result separately
                if "ui_result" in result:
                    tool_ui_result = {
                        "event": {
                            "toolUiOutput": result["ui_result"]
                        }
                    }
                
                if self.active_connection:
                    # Send model result first
                    logger.info("Sending model result")
                    await self.active_connection.send_text(json.dumps(tool_result_event))
                    
                    # Then send UI result if available
                    if "ui_result" in result:
                        logger.info(f"Sending UI result: {tool_ui_result}")
                        await self.active_connection.send_text(json.dumps(tool_ui_result))
                        logger.info("UI result sent")
            else:
                # Handle error case - add error to conversation history
                error_text = f"Tool {self.current_tool_name} failed: {result.get('error', 'Unknown error')}"
                error_result = {
                    "event": {
                        "toolResult": {
                            "promptName": tool_use["promptName"],
                            "contentName": str(uuid.uuid4()),
                            "content": json.dumps(result)
                        }
                    }
                }
                self.add_message_from_event(error_result, error_text, event_type="toolResult")
                
                if self.active_connection:
                    await self.active_connection.send_text(json.dumps(error_result))
                
        except Exception as e:
            logger.error(f"Error handling tool use: {e}")
            error_result = {
                "event": {
                    "toolResult": {
                        "promptName": tool_use["promptName"] if "toolUse" in event_data["event"] else str(uuid.uuid4()),
                        "contentName": str(uuid.uuid4()),
                        "content": json.dumps({"error": str(e)})
                    }
                }
            }
            if self.active_connection:
                await self.active_connection.send_text(json.dumps(error_result))

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connection = websocket
        logger.info("WebSocket connection accepted")
        
        self.nova_client = SimpleNovaSonic()
        await self.nova_client.start_session()
        logger.info("Nova Sonic session started")

        # --- Send conversation history after system prompt ---
        history = self.get_history()
        # Only include history starting with a USER message
        while history and history[0]['role'] != 'USER':
            history.pop(0)
        if history:
            for msg in history:
                content_name = msg['contentName']
                role = msg['role']
                text = msg['text']
                # Send contentStart
                content_start = {
                    "event": {
                        "contentStart": {
                            "promptName": self.nova_client.prompt_name,
                            "contentName": content_name,
                            "type": "TEXT",
                            "interactive": False,
                            "role": role,
                            "textInputConfiguration": {
                                "mediaType": "text/plain"
                            }
                        }
                    }
                }
                await self.nova_client.send_event(json.dumps(content_start))
                # Send textInput
                text_input = {
                    "event": {
                        "textInput": {
                            "promptName": self.nova_client.prompt_name,
                            "contentName": content_name,
                            "content": text
                        }
                    }
                }
                await self.nova_client.send_event(json.dumps(text_input))
                # Send contentEnd
                content_end = {
                    "event": {
                        "contentEnd": {
                            "promptName": self.nova_client.prompt_name,
                            "contentName": content_name
                        }
                    }
                }
                await self.nova_client.send_event(json.dumps(content_end))

    async def disconnect(self):
        if self.nova_client:
            logger.info("Stopping Nova Sonic session")
            if self.audio_content_started:
                await self.stop_audio()
            self.nova_client.is_active = False
            await self.nova_client.end_session()
            self.nova_client = None
        self._close_debug_files()
        self.active_connection = None

    async def receive_audio(self, audio_data: bytes):
        if self.nova_client and self.audio_content_started:
            try:
                current_time = time.time()
                time_since_last_chunk = current_time - self.last_audio_chunk_time
                
                # Only process audio if enough time has passed (prevent overwhelming the system)
                if time_since_last_chunk >= self.audio_chunk_threshold:
                    # Save input audio to debug file
                    if self.save_debug_audio and self.debug_input_file:
                        self.debug_input_file.writeframes(audio_data)
                        self.received_chunks += 1
                        if self.received_chunks % 100 == 0:
                            logger.info(f"Received {self.received_chunks} audio chunks")

                    # Send to Nova Sonic
                    await self.nova_client.send_audio_chunk(audio_data)
                    self.last_audio_chunk_time = current_time
                    logger.debug(f"Sent audio chunk of size {len(audio_data)} bytes")
            except Exception as e:
                logger.error(f"Error sending audio chunk: {e}")

    async def start_audio(self):
        if self.nova_client and not self.audio_content_started:
            try:
                logger.info("Starting audio input")
                self._create_debug_files()  # Create new debug files for this session
                
                # Generate new unique content name
                self.current_content_name = str(uuid.uuid4())
                logger.info(f"Using new content name: {self.current_content_name}")
                
                # Start audio with new content name
                self.nova_client.audio_content_name = self.current_content_name
                await self.nova_client.start_audio_input()
                self.audio_content_started = True
            except Exception as e:
                logger.error(f"Error starting audio input: {e}")

    async def stop_audio(self):
        if self.nova_client and self.audio_content_started:
            try:
                logger.info("Stopping audio input")
                await self.nova_client.end_audio_input()
                self.audio_content_started = False
                self.current_content_name = None
                self._close_debug_files()  # Close debug files when stopping
            except Exception as e:
                logger.error(f"Error stopping audio input: {e}")

    async def process_audio_responses(self):
        if not self.nova_client or not self.active_connection:
            return

        logger.info("Started processing audio responses")
        try:
            while self.nova_client.is_active:
                try:
                    # Use timeout to allow checking barge-in status
                    audio_data = await asyncio.wait_for(
                        self.nova_client.audio_queue.get(),
                        timeout=0.1
                    )
                    
                    if audio_data:
                        # Check if we're in a barge-in state
                        if self.nova_client.barge_in:
                            logger.info("Barge-in detected, skipping audio output")
                            continue

                        # Save output audio to debug file
                        if self.save_debug_audio and self.debug_output_file:
                            self.debug_output_file.writeframes(audio_data)
                            self.sent_chunks += 1
                            if self.sent_chunks % 10 == 0:
                                logger.info(f"Sent {self.sent_chunks} response chunks")

                        # Send audio in smaller chunks for better responsiveness
                        for i in range(0, len(audio_data), CHUNK_SIZE):
                            if self.nova_client.barge_in:
                                break
                            chunk = audio_data[i:min(i + CHUNK_SIZE, len(audio_data))]
                            await self.active_connection.send_bytes(chunk)
                            await asyncio.sleep(0.001)  # Small yield

                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error processing audio response: {e}")
                    await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Error in audio response processing loop: {e}")
        finally:
            logger.info("Stopped processing audio responses")

    async def process_events(self):
        if not self.nova_client or not self.active_connection:
            return
        try:
            while self.nova_client.is_active:
                try:
                    event_json = await asyncio.wait_for(
                        self.nova_client.event_queue.get(),
                        timeout=1.0
                    )
                    if event_json:
                        # Parse event data for role classification
                        event_data = json.loads(event_json)
                        
                        # Log all events for debugging
                        logger.info(f"🔍 Processing event: {list(event_data.get('event', {}).keys()) if 'event' in event_data else 'No event key'}")
                        
                        # Process different event types and add to conversation history
                        if 'event' in event_data:
                            event = event_data['event']
                            
                            # Handle text output (could be USER or ASSISTANT based on current speaker)
                            if 'textOutput' in event:
                                text_content = event['textOutput'].get('content', '')
                                if text_content.strip():  # Only add non-empty messages
                                    # Determine role based on current speaker from contentStart
                                    if self.current_speaker_role == 'USER':
                                        # This is user speech transcription
                                        self.add_message_from_event(event_data, text_content, event_type="textInput")
                                        logger.info(f"📝 Added USER message: {text_content[:50]}...")
                                    else:
                                        # This is assistant response (default)
                                        self.add_message_from_event(event_data, text_content, event_type="textOutput")
                                        logger.info(f"📝 Added ASSISTANT message: {text_content[:50]}...")
                                
                                if '{ "interrupted" : true }' in text_content:
                                    logger.info("Barge-in detected in event processing")
                                    self.nova_client.barge_in = True
                                    
                                    # Send barge-in event to frontend
                                    barge_in_event = {
                                        "event": {
                                            "toolUiOutput": {
                                                "type": "barge_in",
                                                "content": {
                                                    "status": "interrupted"
                                                }
                                            }
                                        }
                                    }
                                    await self.active_connection.send_text(json.dumps(barge_in_event))
                            # Handle user text input (transcribed speech)
                            elif 'textInput' in event:
                                text_content = event['textInput'].get('content', '')
                                if text_content.strip():  # Only add non-empty user messages
                                    # Add user message to history with automatic classification
                                    self.add_message_from_event(event_data, text_content, event_type="textInput")
                                    logger.info(f"📝 Added USER message: {text_content[:50]}...")
                            
                            # Handle content start events (track current speaker)
                            elif 'contentStart' in event:
                                content_start = event['contentStart']
                                role = content_start.get('role', 'UNKNOWN')
                                self.current_speaker_role = role  # Track who is currently speaking
                                logger.info(f"🎬 Content started - Role: {role}, ContentName: {content_start.get('contentName')}")
                                if role == 'USER':
                                    logger.info(f"👤 User content started: {content_start.get('contentName')}")
                            
                            # Handle content end events (reset speaker tracking)
                            elif 'contentEnd' in event:
                                logger.info(f"🏁 Content ended: {event['contentEnd'].get('contentName')}")
                                self.current_speaker_role = None  # Reset speaker tracking
                            
                            # Log any other event types we might be missing
                            else:
                                event_types = list(event.keys())
                                logger.info(f"❓ Unhandled event types: {event_types}")
                                
                        await self.active_connection.send_text(event_json)
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error processing event: {e}")
                    await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Error in event processing loop: {e}")
        finally:
            logger.info("Stopped processing events")

    async def handle_ui_interaction(self, interaction_data):
        """Handle UI interaction events by converting them to Nova Sonic events"""
        if not self.nova_client:
            logger.error("No Nova Sonic client available for handling UI interaction")
            return

        if interaction_data.get("type") == "button_click":
            # Add UI interaction to conversation history as USER message
            interaction_text = "The user clicked a button. Please acknowledge this action and respond both in text and speech."
            ui_event_data = {
                "event": {
                    "ui_interaction": interaction_data
                }
            }
            self.add_message_from_event(ui_event_data, interaction_text, event_type="ui_interaction")
            
            # Generate unique IDs for this interaction
            prompt_name = self.nova_client.prompt_name  # Use the existing prompt name
            content_name = f"button_click_{str(uuid.uuid4())}"
            
            # Send sequence of events to Nova Sonic
            events = [
                {
                    "event": {
                        "contentStart": {
                            "promptName": prompt_name,
                            "contentName": content_name,
                            "type": "TEXT",
                            "interactive": True,
                            "role": "USER",
                            "textInputConfiguration": {
                                "mediaType": "text/plain"
                            }
                        }
                    }
                },
                {
                    "event": {
                        "textInput": {
                            "promptName": prompt_name,
                            "contentName": content_name,
                            "content": interaction_text
                        }
                    }
                },
                {
                    "event": {
                        "contentEnd": {
                            "promptName": prompt_name,
                            "contentName": content_name
                        }
                    }
                }
            ]
            
            # Send events to Nova Sonic
            for event in events:
                try:
                    await self.nova_client.send_event(json.dumps(event))
                    logger.info(f"Sent UI interaction event to Nova Sonic: {event}")
                except Exception as e:
                    logger.error(f"Error sending event to Nova Sonic: {e}")
                    logger.exception(e)

# Default (does not save audio files)
SAVE_DEBUG_AUDIO = os.getenv('SAVE_DEBUG_AUDIO', 'false').lower() == 'true'
manager = ConnectionManager(save_debug_audio=SAVE_DEBUG_AUDIO)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    logger.info("New WebSocket connection request")
    await manager.connect(websocket)
    
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
        await manager.disconnect()

for r in app_routers:
    app.include_router(r)

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting FastAPI server")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info") 










