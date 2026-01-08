"""
Role Classification Service

This module provides role classification functionality for conversation messages.
It determines whether messages should be assigned "USER" or "ASSISTANT" roles
based on their source and event type.
"""

import logging
from typing import Dict, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class MessageRole(Enum):
    """Enumeration of valid message roles."""
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class RoleClassifier:
    """
    Service for classifying message roles based on source and event type.
    
    This service handles:
    - Role classification based on message source and event type
    - Role validation to ensure only valid roles are used
    - Default role assignment for ambiguous cases
    - Logging of role assignment decisions for debugging
    """
    
    # Role classification rules mapping event types to roles
    ROLE_CLASSIFICATION_RULES = {
        # User-originated events
        "textInput": MessageRole.USER,
        "ui_interaction": MessageRole.USER,
        "toolUse": MessageRole.USER,
        "audio_transcription": MessageRole.USER,
        "button_click": MessageRole.USER,
        
        # Assistant-originated events
        "textOutput": MessageRole.ASSISTANT,
        "toolResult": MessageRole.ASSISTANT,
        "audio_response": MessageRole.ASSISTANT,
        "contentStart": MessageRole.ASSISTANT,
        "contentEnd": MessageRole.ASSISTANT,
    }
    
    # Default role for ambiguous cases
    DEFAULT_ROLE = MessageRole.ASSISTANT
    
    def __init__(self):
        """Initialize the role classifier."""
        logger.info("RoleClassifier initialized")
    
    def classify_message_role(
        self, 
        source: Optional[str] = None, 
        event_type: Optional[str] = None, 
        content: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Determine the appropriate role for a message based on its source and event type.
        
        Args:
            source: The source of the message (e.g., "websocket", "audio", "ui")
            event_type: The type of event (e.g., "textInput", "toolUse", "textOutput")
            content: Additional message content that might help with classification
            
        Returns:
            str: The role ("USER" or "ASSISTANT")
        """
        try:
            # First, try to classify based on event type
            if event_type and event_type in self.ROLE_CLASSIFICATION_RULES:
                role = self.ROLE_CLASSIFICATION_RULES[event_type]
                logger.debug(f"Classified message as {role.value} based on event_type: {event_type}")
                return role.value
            
            # Try to infer event type from content structure
            if content:
                inferred_event_type = self._infer_event_type_from_content(content)
                if inferred_event_type and inferred_event_type in self.ROLE_CLASSIFICATION_RULES:
                    role = self.ROLE_CLASSIFICATION_RULES[inferred_event_type]
                    logger.debug(f"Classified message as {role.value} based on inferred event_type: {inferred_event_type}")
                    return role.value
            
            # Try to classify based on source
            if source:
                role = self._classify_by_source(source)
                if role:
                    logger.debug(f"Classified message as {role.value} based on source: {source}")
                    return role.value
            
            # Default to ASSISTANT role for ambiguous cases
            logger.warning(f"Could not classify message role - using default {self.DEFAULT_ROLE.value}. "
                         f"Source: {source}, Event type: {event_type}")
            return self.DEFAULT_ROLE.value
            
        except Exception as e:
            logger.error(f"Error classifying message role: {e}. Using default role {self.DEFAULT_ROLE.value}")
            return self.DEFAULT_ROLE.value
    
    def _infer_event_type_from_content(self, content: Dict[str, Any]) -> Optional[str]:
        """
        Infer event type from message content structure.
        
        Args:
            content: Message content dictionary
            
        Returns:
            Optional[str]: Inferred event type or None if cannot be determined
        """
        if not isinstance(content, dict):
            return None
        
        # Check for event structure
        if "event" in content:
            event_data = content["event"]
            if isinstance(event_data, dict):
                # Look for specific event types
                for event_type in ["textInput", "textOutput", "toolUse", "toolResult", 
                                 "ui_interaction", "contentStart", "contentEnd"]:
                    if event_type in event_data:
                        return event_type
        
        # Check for direct event type indicators
        if "type" in content:
            event_type = content["type"]
            if event_type in self.ROLE_CLASSIFICATION_RULES:
                return event_type
        
        return None
    
    def _classify_by_source(self, source: str) -> Optional[MessageRole]:
        """
        Classify message role based on source information.
        
        Args:
            source: The source of the message
            
        Returns:
            Optional[MessageRole]: The classified role or None if cannot be determined
        """
        source_lower = source.lower()
        
        # User-originated sources
        if any(keyword in source_lower for keyword in ["user", "input", "ui", "button", "click"]):
            return MessageRole.USER
        
        # Assistant-originated sources
        if any(keyword in source_lower for keyword in ["assistant", "output", "response", "system"]):
            return MessageRole.ASSISTANT
        
        return None
    
    def validate_role(self, role: str) -> bool:
        """
        Validate that a role is one of the allowed values.
        
        Args:
            role: The role string to validate
            
        Returns:
            bool: True if the role is valid, False otherwise
        """
        if not isinstance(role, str):
            logger.warning(f"Role validation failed: role is not a string: {type(role)}")
            return False
        
        try:
            MessageRole(role)
            return True
        except ValueError:
            logger.warning(f"Role validation failed: invalid role '{role}'. "
                         f"Valid roles are: {[r.value for r in MessageRole]}")
            return False
    
    def get_valid_roles(self) -> list[str]:
        """
        Get a list of all valid role values.
        
        Returns:
            list[str]: List of valid role strings
        """
        return [role.value for role in MessageRole]
    
    def correct_invalid_role(self, role: str) -> str:
        """
        Correct an invalid role by returning a valid default role.
        
        Args:
            role: The potentially invalid role
            
        Returns:
            str: A valid role (either the original if valid, or the default)
        """
        if self.validate_role(role):
            return role
        
        logger.warning(f"Correcting invalid role '{role}' to default role '{self.DEFAULT_ROLE.value}'")
        return self.DEFAULT_ROLE.value
    
    def classify_websocket_event(self, event_data: Dict[str, Any]) -> str:
        """
        Classify role for WebSocket event messages.
        
        Args:
            event_data: The WebSocket event data
            
        Returns:
            str: The classified role
        """
        try:
            # Extract event type from WebSocket event structure
            if "event" in event_data and isinstance(event_data["event"], dict):
                event = event_data["event"]
                
                # Check for specific event types
                for event_type in self.ROLE_CLASSIFICATION_RULES.keys():
                    if event_type in event:
                        role = self.ROLE_CLASSIFICATION_RULES[event_type]
                        logger.debug(f"Classified WebSocket event as {role.value} based on event type: {event_type}")
                        return role.value
            
            # Fallback to general classification
            return self.classify_message_role(
                source="websocket",
                event_type=None,
                content=event_data
            )
            
        except Exception as e:
            logger.error(f"Error classifying WebSocket event: {e}. Using default role.")
            return self.DEFAULT_ROLE.value
    
    def get_classification_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the classification rules.
        
        Returns:
            Dict[str, Any]: Statistics about classification rules and valid roles
        """
        user_events = [event for event, role in self.ROLE_CLASSIFICATION_RULES.items() 
                      if role == MessageRole.USER]
        assistant_events = [event for event, role in self.ROLE_CLASSIFICATION_RULES.items() 
                           if role == MessageRole.ASSISTANT]
        
        return {
            "total_rules": len(self.ROLE_CLASSIFICATION_RULES),
            "user_event_types": user_events,
            "assistant_event_types": assistant_events,
            "valid_roles": self.get_valid_roles(),
            "default_role": self.DEFAULT_ROLE.value
        }