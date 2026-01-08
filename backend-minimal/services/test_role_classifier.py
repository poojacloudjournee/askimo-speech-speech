"""
Basic tests for RoleClassifier to verify functionality.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from role_classifier import RoleClassifier, MessageRole


def test_role_classifier():
    """Test basic RoleClassifier functionality."""
    classifier = RoleClassifier()
    
    # Test event type classification
    assert classifier.classify_message_role(event_type="textInput") == "USER"
    assert classifier.classify_message_role(event_type="textOutput") == "ASSISTANT"
    assert classifier.classify_message_role(event_type="toolUse") == "USER"
    assert classifier.classify_message_role(event_type="toolResult") == "ASSISTANT"
    
    # Test role validation
    assert classifier.validate_role("USER") == True
    assert classifier.validate_role("ASSISTANT") == True
    assert classifier.validate_role("INVALID") == False
    assert classifier.validate_role("") == False
    
    # Test role correction
    assert classifier.correct_invalid_role("USER") == "USER"
    assert classifier.correct_invalid_role("INVALID") == "ASSISTANT"
    
    # Test WebSocket event classification
    user_event = {"event": {"textInput": {"content": "Hello"}}}
    assert classifier.classify_websocket_event(user_event) == "USER"
    
    assistant_event = {"event": {"textOutput": {"content": "Hi there"}}}
    assert classifier.classify_websocket_event(assistant_event) == "ASSISTANT"
    
    # Test default role for ambiguous cases
    assert classifier.classify_message_role() == "ASSISTANT"
    
    print("All RoleClassifier tests passed!")


if __name__ == "__main__":
    test_role_classifier()