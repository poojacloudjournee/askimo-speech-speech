"""
Test the enhanced ConnectionManager with role classification.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import ConnectionManager
import json


def test_connection_manager_role_classification():
    """Test ConnectionManager with role classification."""
    manager = ConnectionManager(save_debug_audio=False)
    
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
        print(f"Message {i+1}: Role={msg['role']}, Text='{msg['text'][:30]}...', Timestamp={msg.get('timestamp', 'N/A')}")
    
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
    
    print("All ConnectionManager role classification tests passed!")


if __name__ == "__main__":
    test_connection_manager_role_classification()