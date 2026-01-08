"""
Test role classification integration without full dependencies.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'services'))

from role_classifier import RoleClassifier
from datetime import datetime
import uuid


class MockConnectionManager:
    """Mock ConnectionManager to test role classification integration."""
    
    def __init__(self):
        self.chat_history = []
        self.max_history = 10
        self.role_classifier = RoleClassifier()
    
    def add_history(self, role, text, source_info=None):
        """Add a message to the rolling chat history with role validation."""
        # Validate and correct role if needed
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
        
        # Add source info for debugging if provided
        if source_info:
            message['source_info'] = source_info
        
        self.chat_history.append(message)
        
        # Keep only the last N messages
        if len(self.chat_history) > self.max_history:
            self.chat_history = self.chat_history[-self.max_history:]
    
    def add_message_from_event(self, event_data, text, event_type=None, source="websocket"):
        """Add a message to history with automatic role classification based on event data."""
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
    
    def get_history(self):
        """Get the current rolling chat history."""
        return self.chat_history.copy()


def test_role_integration():
    """Test role classification integration."""
    manager = MockConnectionManager()
    
    # Test direct add_history with valid roles
    manager.add_history("USER", "Hello")
    manager.add_history("ASSISTANT", "Hi there")
    
    # Test add_history with invalid role (should be corrected)
    manager.add_history("INVALID", "This should be corrected")
    
    # Test add_message_from_event with textInput
    text_input_event = {
        "event": {
            "textInput": {
                "content": "User message via event"
            }
        }
    }
    manager.add_message_from_event(text_input_event, "User message via event", event_type="textInput")
    
    # Test add_message_from_event with textOutput
    text_output_event = {
        "event": {
            "textOutput": {
                "content": "Assistant response via event"
            }
        }
    }
    manager.add_message_from_event(text_output_event, "Assistant response via event", event_type="textOutput")
    
    # Get history and verify roles
    history = manager.get_history()
    
    print(f"Total messages in history: {len(history)}")
    for i, msg in enumerate(history):
        print(f"Message {i+1}: Role={msg['role']}, Text='{msg['text'][:30]}...', Source={msg.get('source_info', {}).get('event_type', 'N/A')}")
    
    # Verify role assignments
    assert history[0]['role'] == 'USER'  # "Hello"
    assert history[1]['role'] == 'ASSISTANT'  # "Hi there"
    assert history[2]['role'] == 'ASSISTANT'  # "INVALID" corrected to "ASSISTANT"
    assert history[3]['role'] == 'USER'  # textInput event
    assert history[4]['role'] == 'ASSISTANT'  # textOutput event
    
    # Verify timestamps are added
    for msg in history:
        assert 'timestamp' in msg
        assert msg['timestamp'].endswith('Z')
    
    # Verify source info is added for auto-classified messages
    assert 'source_info' in history[3]
    assert history[3]['source_info']['event_type'] == 'textInput'
    assert 'source_info' in history[4]
    assert history[4]['source_info']['event_type'] == 'textOutput'
    
    print("All role classification integration tests passed!")


if __name__ == "__main__":
    test_role_integration()