"""
Test enhanced WebSocket message handlers with role classification.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'services'))

from role_classifier import RoleClassifier
from datetime import datetime
import uuid
import json


class MockConnectionManager:
    """Mock ConnectionManager to test WebSocket handler enhancements."""
    
    def __init__(self):
        self.chat_history = []
        self.max_history = 10
        self.role_classifier = RoleClassifier()
        self.nova_client = None
        self.active_connection = None
    
    def add_history(self, role, text, source_info=None):
        """Add a message to the rolling chat history with role validation."""
        if not self.role_classifier.validate_role(role):
            print(f"Invalid role '{role}' provided to add_history. Correcting to valid role.")
            role = self.role_classifier.correct_invalid_role(role)
        
        content_name = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        message = {
            'role': role,
            'text': text,
            'contentName': content_name,
            'timestamp': timestamp
        }
        
        if source_info:
            message['source_info'] = source_info
        
        self.chat_history.append(message)
        
        if len(self.chat_history) > self.max_history:
            self.chat_history = self.chat_history[-self.max_history:]
    
    def add_message_from_event(self, event_data, text, event_type=None, source="websocket"):
        """Add a message to history with automatic role classification based on event data."""
        if event_type:
            role = self.role_classifier.classify_message_role(
                source=source,
                event_type=event_type,
                content=event_data
            )
        else:
            role = self.role_classifier.classify_websocket_event(event_data)
        
        source_info = {
            "source": source,
            "event_type": event_type,
            "has_event_data": bool(event_data)
        }
        
        self.add_history(role, text, source_info)
    
    def get_history(self):
        """Get the current rolling chat history."""
        return self.chat_history.copy()


def test_websocket_event_processing():
    """Test WebSocket event processing with role classification."""
    manager = MockConnectionManager()
    
    # Test textInput event (user message)
    text_input_event = {
        "event": {
            "textInput": {
                "content": "Hello, I need help with my room"
            }
        }
    }
    manager.add_message_from_event(text_input_event, "Hello, I need help with my room", event_type="textInput")
    
    # Test textOutput event (assistant response)
    text_output_event = {
        "event": {
            "textOutput": {
                "content": "I'd be happy to help you with your room!"
            }
        }
    }
    manager.add_message_from_event(text_output_event, "I'd be happy to help you with your room!", event_type="textOutput")
    
    # Test UI interaction event (user button click)
    ui_interaction_event = {
        "event": {
            "ui_interaction": {
                "type": "button_click"
            }
        }
    }
    manager.add_message_from_event(ui_interaction_event, "The user clicked a button", event_type="ui_interaction")
    
    # Test toolUse event (user tool request)
    tool_use_event = {
        "event": {
            "toolUse": {
                "toolName": "room_service",
                "content": "{\"request\": \"coffee\"}"
            }
        }
    }
    manager.add_message_from_event(tool_use_event, "User requested tool: room_service", event_type="toolUse")
    
    # Test toolResult event (assistant tool response)
    tool_result_event = {
        "event": {
            "toolResult": {
                "content": "{\"status\": \"success\"}"
            }
        }
    }
    manager.add_message_from_event(tool_result_event, "Tool room_service executed successfully", event_type="toolResult")
    
    # Get history and verify roles
    history = manager.get_history()
    
    print(f"Total messages in history: {len(history)}")
    for i, msg in enumerate(history):
        event_type = msg.get('source_info', {}).get('event_type', 'N/A')
        print(f"Message {i+1}: Role={msg['role']}, Event={event_type}, Text='{msg['text'][:40]}...'")
    
    # Verify role assignments
    assert history[0]['role'] == 'USER'      # textInput
    assert history[1]['role'] == 'ASSISTANT' # textOutput
    assert history[2]['role'] == 'USER'      # ui_interaction
    assert history[3]['role'] == 'USER'      # toolUse
    assert history[4]['role'] == 'ASSISTANT' # toolResult
    
    # Verify event types are tracked
    assert history[0]['source_info']['event_type'] == 'textInput'
    assert history[1]['source_info']['event_type'] == 'textOutput'
    assert history[2]['source_info']['event_type'] == 'ui_interaction'
    assert history[3]['source_info']['event_type'] == 'toolUse'
    assert history[4]['source_info']['event_type'] == 'toolResult'
    
    print("All WebSocket handler tests passed!")


def test_conversation_statistics():
    """Test that conversation statistics will be accurate with proper role classification."""
    manager = MockConnectionManager()
    
    # Add a mix of user and assistant messages
    user_messages = [
        ("textInput", "Hello"),
        ("ui_interaction", "Button clicked"),
        ("toolUse", "Tool requested"),
        ("textInput", "Another user message")
    ]
    
    assistant_messages = [
        ("textOutput", "Hi there!"),
        ("toolResult", "Tool completed"),
        ("textOutput", "How can I help?")
    ]
    
    # Add user messages
    for event_type, text in user_messages:
        event_data = {"event": {event_type: {"content": text}}}
        manager.add_message_from_event(event_data, text, event_type=event_type)
    
    # Add assistant messages
    for event_type, text in assistant_messages:
        event_data = {"event": {event_type: {"content": text}}}
        manager.add_message_from_event(event_data, text, event_type=event_type)
    
    history = manager.get_history()
    
    # Count messages by role
    user_count = sum(1 for msg in history if msg['role'] == 'USER')
    assistant_count = sum(1 for msg in history if msg['role'] == 'ASSISTANT')
    
    print(f"User messages: {user_count}, Assistant messages: {assistant_count}")
    
    # Verify counts
    assert user_count == len(user_messages)
    assert assistant_count == len(assistant_messages)
    assert user_count + assistant_count == len(history)
    
    print("Conversation statistics test passed!")


if __name__ == "__main__":
    test_websocket_event_processing()
    test_conversation_statistics()