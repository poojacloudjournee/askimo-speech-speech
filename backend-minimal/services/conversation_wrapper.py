"""
Conversation Storage Wrapper

This module provides a wrapper around the existing ConnectionManager
to add S3 conversation storage functionality without modifying existing code.
It handles session tracking and triggers S3 uploads when conversations end.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import WebSocket

from .s3_conversation_storage import S3StorageService

logger = logging.getLogger(__name__)


class ConversationStorageWrapper:
    """
    Wrapper for ConnectionManager that adds S3 conversation storage.
    
    This wrapper preserves all existing ConnectionManager functionality
    while adding automatic S3 storage of conversation history when
    sessions end.
    """
    
    def __init__(self, connection_manager):
        """
        Initialize the conversation storage wrapper.
        
        Args:
            connection_manager: The existing ConnectionManager instance
        """
        self.connection_manager = connection_manager
        self.s3_storage = S3StorageService()
        
        # Session tracking
        self.session_id: Optional[str] = None
        self.session_start_time: Optional[datetime] = None
        
        logger.info(f"ConversationStorageWrapper initialized (S3 enabled: {self.s3_storage.enabled})")
    
    def generate_session_id(self) -> str:
        """
        Generate a unique session identifier.
        
        Returns:
            str: UUID-based session identifier
        """
        return str(uuid.uuid4())
    
    async def wrap_connect(self, websocket: WebSocket):
        """
        Wrap the ConnectionManager connect method with session tracking.
        
        Args:
            websocket: WebSocket connection
        """
        # Generate session tracking info
        self.session_id = self.generate_session_id()
        self.session_start_time = datetime.now(timezone.utc)
        
        logger.info(f"Starting conversation session: {self.session_id}")
        
        # Call original connect method
        return await self.connection_manager.connect(websocket)
    
    async def wrap_disconnect(self):
        """
        Wrap the ConnectionManager disconnect method with S3 storage.
        
        This method stores the conversation to S3 before calling the
        original disconnect method.
        """
        session_end_time = datetime.now(timezone.utc)
        
        logger.info(f"🔍 Disconnect called for session: {self.session_id}")
        logger.info(f"🔍 S3 enabled: {self.s3_storage.enabled}")
        logger.info(f"🔍 Chat history length: {len(self.connection_manager.chat_history) if self.connection_manager.chat_history else 0}")
        
        # Store conversation to S3 before disconnecting
        if self.s3_storage.enabled and self.session_id and self.connection_manager.chat_history:
            logger.info(f"📤 Storing conversation to S3 for session: {self.session_id}")
            await self._store_conversation_to_s3(session_end_time)
        else:
            logger.warning(f"⚠️  Skipping S3 storage - S3 enabled: {self.s3_storage.enabled}, Session ID: {self.session_id is not None}, Chat history: {len(self.connection_manager.chat_history) if self.connection_manager.chat_history else 0} messages")
        
        # Call original disconnect method
        result = await self.connection_manager.disconnect()
        
        # Clean up session tracking
        self.session_id = None
        self.session_start_time = None
        
        return result
    

    
    async def _store_conversation_to_s3(self, end_time: datetime):
        """
        Store the current conversation to S3.
        
        Args:
            end_time: When the conversation session ended
        """
        if not self.session_id or not self.session_start_time:
            logger.warning("Cannot store conversation: missing session tracking info")
            return
        
        try:
            logger.info(f"🔍 Starting S3 storage for session {self.session_id}")
            
            # Calculate session duration
            duration_seconds = int((end_time - self.session_start_time).total_seconds())
            
            # Prepare metadata
            metadata = {
                'start_time': self.session_start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'duration_seconds': duration_seconds
            }
            
            logger.info(f"🔍 Session metadata: {metadata}")
            
            # Get conversation history from ConnectionManager
            chat_history = self.connection_manager.get_history()
            
            logger.info(f"🔍 Retrieved chat history: {len(chat_history)} messages")
            for i, msg in enumerate(chat_history):
                logger.info(f"   Message {i+1}: {msg.get('role', 'UNKNOWN')} - {msg.get('text', '')[:50]}...")
            
            if not chat_history:
                logger.info(f"No conversation history to store for session {self.session_id}")
                return
            
            # Upload to S3
            logger.info(f"📤 Uploading to S3...")
            success = await self.s3_storage.upload_conversation(
                session_id=self.session_id,
                chat_history=chat_history,
                metadata=metadata
            )
            
            if success:
                logger.info(f"✅ Successfully stored conversation {self.session_id} to S3 ({len(chat_history)} messages)")
            else:
                logger.warning(f"❌ Failed to store conversation {self.session_id} to S3")
                
        except Exception as e:
            logger.error(f"❌ Error storing conversation to S3: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Don't raise the exception - conversation functionality should continue
    
    # Delegate all other methods to the wrapped ConnectionManager
    def __getattr__(self, name):
        """
        Delegate all other method calls to the wrapped ConnectionManager.
        
        This ensures that all existing ConnectionManager functionality
        remains available through the wrapper.
        """
        return getattr(self.connection_manager, name)