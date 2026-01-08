"""
Test enhanced S3 storage service with role validation and correction.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from s3_conversation_storage import S3StorageService
from datetime import datetime
import uuid


def test_role_validation_and_correction():
    """Test role validation and correction in S3 storage service."""
    # Create S3 service (disabled for testing)
    s3_service = S3StorageService(enabled=False)
    
    # Test chat history with mixed valid and invalid roles
    chat_history = [
        {
            'role': 'USER',
            'text': 'Hello, I need help',
            'contentName': str(uuid.uuid4()),
            'timestamp': '2025-12-19T10:00:00Z',
            'source_info': {'event_type': 'textInput', 'source': 'websocket'}
        },
        {
            'role': 'ASSISTANT',
            'text': 'How can I help you?',
            'contentName': str(uuid.uuid4()),
            'timestamp': '2025-12-19T10:00:05Z',
            'source_info': {'event_type': 'textOutput', 'source': 'websocket'}
        },
        {
            'role': 'INVALID_ROLE',  # This should be corrected
            'text': 'This has an invalid role',
            'contentName': str(uuid.uuid4()),
            'timestamp': '2025-12-19T10:00:10Z'
        },
        {
            'role': 'USER',
            'text': 'User requested tool: room_service',
            'contentName': str(uuid.uuid4()),
            'timestamp': '2025-12-19T10:00:15Z',
            'source_info': {'event_type': 'toolUse', 'source': 'websocket'}
        },
        {
            'role': 'ASSISTANT',
            'text': 'Tool room_service executed successfully',
            'contentName': str(uuid.uuid4()),
            'timestamp': '2025-12-19T10:00:20Z',
            'source_info': {'event_type': 'toolResult', 'source': 'websocket'}
        }
    ]
    
    metadata = {
        'start_time': '2025-12-19T10:00:00Z',
        'end_time': '2025-12-19T10:00:25Z',
        'duration_seconds': 25
    }
    
    # Test role validation and correction
    corrected_history = s3_service._validate_and_correct_roles(chat_history)
    
    print("Original vs Corrected Roles:")
    for i, (original, corrected) in enumerate(zip(chat_history, corrected_history)):
        orig_role = original.get('role')
        corr_role = corrected.get('role')
        print(f"Message {i+1}: {orig_role} -> {corr_role}")
    
    # Verify corrections
    assert corrected_history[0]['role'] == 'USER'
    assert corrected_history[1]['role'] == 'ASSISTANT'
    assert corrected_history[2]['role'] == 'ASSISTANT'  # INVALID_ROLE corrected to ASSISTANT
    assert corrected_history[3]['role'] == 'USER'
    assert corrected_history[4]['role'] == 'ASSISTANT'
    
    print("Role validation and correction test passed!")


def test_conversation_formatting():
    """Test enhanced conversation data formatting."""
    s3_service = S3StorageService(enabled=False)
    
    # Test chat history with proper roles
    chat_history = [
        {
            'role': 'USER',
            'text': 'Hello',
            'contentName': str(uuid.uuid4()),
            'timestamp': '2025-12-19T10:00:00Z'
        },
        {
            'role': 'ASSISTANT',
            'text': 'Hi there!',
            'contentName': str(uuid.uuid4()),
            'timestamp': '2025-12-19T10:00:05Z'
        },
        {
            'role': 'USER',
            'text': 'User requested tool: coffee_service',
            'contentName': str(uuid.uuid4()),
            'timestamp': '2025-12-19T10:00:10Z',
            'source_info': {'event_type': 'toolUse', 'source': 'websocket'}
        },
        {
            'role': 'ASSISTANT',
            'text': 'Tool coffee_service executed successfully',
            'contentName': str(uuid.uuid4()),
            'timestamp': '2025-12-19T10:00:15Z',
            'source_info': {'event_type': 'toolResult', 'source': 'websocket'}
        }
    ]
    
    metadata = {
        'start_time': '2025-12-19T10:00:00Z',
        'end_time': '2025-12-19T10:00:20Z',
        'duration_seconds': 20
    }
    
    # Format conversation data
    formatted_data = s3_service._format_conversation_data('test-session', chat_history, metadata)
    
    print(f"Formatted conversation metadata:")
    print(f"  Total messages: {formatted_data['metadata']['message_count']}")
    print(f"  User messages: {formatted_data['metadata']['user_messages']}")
    print(f"  Assistant messages: {formatted_data['metadata']['assistant_messages']}")
    print(f"  Tools used: {formatted_data['metadata']['tools_used']}")
    
    # Verify statistics
    assert formatted_data['metadata']['message_count'] == 4
    assert formatted_data['metadata']['user_messages'] == 2
    assert formatted_data['metadata']['assistant_messages'] == 2
    assert 'coffee_service' in formatted_data['metadata']['tools_used']
    
    print("Conversation formatting test passed!")


def test_conversation_validation():
    """Test conversation data validation."""
    s3_service = S3StorageService(enabled=False)
    
    # Test valid conversation data
    valid_conversation = {
        'session_id': 'test-session',
        'metadata': {
            'start_time': '2025-12-19T10:00:00Z',
            'end_time': '2025-12-19T10:00:10Z',
            'duration_seconds': 10,
            'message_count': 2,
            'user_messages': 1,
            'assistant_messages': 1,
            'tools_used': []
        },
        'conversation': [
            {
                'role': 'USER',
                'text': 'Hello',
                'contentName': str(uuid.uuid4()),
                'timestamp': '2025-12-19T10:00:00Z'
            },
            {
                'role': 'ASSISTANT',
                'text': 'Hi there!',
                'contentName': str(uuid.uuid4()),
                'timestamp': '2025-12-19T10:00:05Z'
            }
        ]
    }
    
    # Test invalid conversation data
    invalid_conversation = {
        'session_id': 'test-session',
        'metadata': {
            'start_time': '2025-12-19T10:00:00Z',
            'end_time': '2025-12-19T10:00:10Z',
            'duration_seconds': 10,
            'message_count': 2,
            'user_messages': 2,  # Wrong count
            'assistant_messages': 0,  # Wrong count
            'tools_used': []
        },
        'conversation': [
            {
                'role': 'INVALID_ROLE',  # Invalid role
                'text': 'Hello',
                'contentName': str(uuid.uuid4()),
                'timestamp': '2025-12-19T10:00:00Z'
            },
            {
                'role': 'ASSISTANT',
                'text': '',  # Empty text
                'contentName': str(uuid.uuid4()),
                'timestamp': '2025-12-19T10:00:05Z'
            }
        ]
    }
    
    # Validate valid conversation
    valid_results = s3_service.validate_conversation_data(valid_conversation)
    print(f"Valid conversation validation: {valid_results['is_valid']}")
    print(f"Valid conversation issues: {valid_results['issues']}")
    
    # Validate invalid conversation
    invalid_results = s3_service.validate_conversation_data(invalid_conversation)
    print(f"Invalid conversation validation: {invalid_results['is_valid']}")
    print(f"Invalid conversation issues: {invalid_results['issues']}")
    
    # Verify results
    assert valid_results['is_valid'] == True
    assert len(valid_results['issues']) == 0
    
    assert invalid_results['is_valid'] == False
    assert len(invalid_results['issues']) > 0
    
    print("Conversation validation test passed!")


if __name__ == "__main__":
    test_role_validation_and_correction()
    test_conversation_formatting()
    test_conversation_validation()