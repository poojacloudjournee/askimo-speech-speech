"""
S3 Conversation Storage Service

This module provides S3 storage functionality for conversation history
without modifying existing code. It handles conversation data formatting,
S3 key generation, and upload operations with comprehensive error handling.
"""

import os
import json
import logging
import boto3
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any
from botocore.exceptions import ClientError, NoCredentialsError, BotoCoreError
from dotenv import load_dotenv
try:
    from .role_classifier import RoleClassifier
except ImportError:
    from role_classifier import RoleClassifier

# Load environment variables from .env file in backend directory
import pathlib
backend_dir = pathlib.Path(__file__).parent.parent
load_dotenv(backend_dir / '.env')

logger = logging.getLogger(__name__)


class S3StorageService:
    """
    Service for storing conversation history to AWS S3.
    
    This service handles:
    - S3 client initialization using existing AWS credentials
    - Conversation data formatting and validation
    - S3 key generation with hierarchical structure
    - Upload operations with error handling and retry logic
    - Configuration via environment variables
    """
    
    def __init__(self, bucket_name: Optional[str] = None, enabled: Optional[bool] = None):
        """
        Initialize S3 storage service.
        
        Args:
            bucket_name: S3 bucket name (defaults to 'strand112')
            enabled: Enable/disable S3 storage (defaults to env var S3_CONVERSATION_ENABLED)
        """
        # Configuration - use specific bucket and path
        self.bucket_name = bucket_name or 'strand112'
        self.s3_prefix = 'askimo-audio-output/conversations'  # Base path for conversations
        self.enabled = enabled if enabled is not None else os.getenv('S3_CONVERSATION_ENABLED', 'true').lower() == 'true'
        
        # S3 client initialization
        self.s3_client = None
        self._initialize_s3_client()
        
        # Role classifier for validation and correction
        self.role_classifier = RoleClassifier()
        
        # Validate configuration
        if self.enabled and not self.bucket_name:
            logger.warning("S3 storage enabled but no bucket name configured. Disabling S3 storage.")
            self.enabled = False
    
    def _initialize_s3_client(self) -> None:
        """
        Initialize S3 client using .env credentials.
        Loads AWS credentials from environment variables set by .env file.
        """
        if not self.enabled:
            return
            
        try:
            # Get AWS credentials from environment variables (loaded from .env)
            aws_access_key_id = os.getenv('aws_access_key_id')
            aws_secret_access_key = os.getenv('aws_secret_access_key')
            aws_session_token = os.getenv('aws_session_token')
            
            if not aws_access_key_id or not aws_secret_access_key:
                logger.error("AWS credentials not found in environment variables")
                self.enabled = False
                return
            
            # Create S3 client with explicit credentials
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                aws_session_token=aws_session_token,
                region_name='us-east-1'  # Default region
            )
            logger.info("S3 client initialized successfully with .env credentials")
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            self.enabled = False
    
    def _validate_s3_connectivity(self) -> bool:
        """
        Validate S3 connectivity and bucket accessibility.
        
        Returns:
            bool: True if S3 is accessible, False otherwise
        """
        if not self.enabled or not self.s3_client or not self.bucket_name:
            return False
            
        try:
            # Test bucket access with a simple head_bucket call
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"S3 bucket '{self.bucket_name}' is accessible")
            return True
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                logger.error(f"S3 bucket '{self.bucket_name}' does not exist")
            elif error_code == '403':
                logger.error(f"Access denied to S3 bucket '{self.bucket_name}'")
            else:
                logger.error(f"S3 bucket access error: {e}")
            return False
        except NoCredentialsError:
            logger.error("AWS credentials not found for S3 access")
            return False
        except Exception as e:
            logger.error(f"Unexpected error validating S3 connectivity: {e}")
            return False
    
    def _generate_s3_key(self, session_id: str, timestamp: datetime) -> str:
        """
        Generate hierarchical S3 key for conversation storage.
        
        Pattern: askimo-audio-output/conversations/{YYYY}/{MM}/{DD}/conversation_{YYYYMMDD}_{HHMMSS}_{session_id}.json
        
        Args:
            session_id: Unique session identifier
            timestamp: Conversation timestamp
            
        Returns:
            str: S3 key following the hierarchical pattern
        """
        # Use UTC timezone for consistent key generation
        utc_timestamp = timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp.astimezone(timezone.utc)
        
        # Extract date components
        year = utc_timestamp.strftime('%Y')
        month = utc_timestamp.strftime('%m')
        day = utc_timestamp.strftime('%d')
        date_str = utc_timestamp.strftime('%Y%m%d')
        time_str = utc_timestamp.strftime('%H%M%S')
        
        # Generate hierarchical key with the specified prefix
        key = f"{self.s3_prefix}/{year}/{month}/{day}/conversation_{date_str}_{time_str}_{session_id}.json"
        return key
    
    def _validate_and_correct_roles(self, chat_history: List[Dict]) -> List[Dict]:
        """
        Validate and correct role assignments in chat history.
        
        Args:
            chat_history: List of conversation messages
            
        Returns:
            List[Dict]: Chat history with validated and corrected roles
        """
        corrected_history = []
        corrections_made = 0
        
        for msg in chat_history:
            corrected_msg = msg.copy()
            original_role = msg.get('role', 'UNKNOWN')
            
            # Validate and correct role
            if not self.role_classifier.validate_role(original_role):
                corrected_role = self.role_classifier.correct_invalid_role(original_role)
                corrected_msg['role'] = corrected_role
                corrections_made += 1
                logger.warning(f"Corrected invalid role '{original_role}' to '{corrected_role}' for message: {msg.get('text', '')[:50]}...")
            
            corrected_history.append(corrected_msg)
        
        if corrections_made > 0:
            logger.info(f"Made {corrections_made} role corrections in conversation history")
        
        return corrected_history
    
    def _extract_tools_used(self, chat_history: List[Dict]) -> List[str]:
        """
        Extract list of tools used from conversation history.
        
        Args:
            chat_history: List of conversation messages
            
        Returns:
            List[str]: List of tool names used in the conversation
        """
        tools_used = set()
        
        for msg in chat_history:
            # Check source info for tool usage
            source_info = msg.get('source_info', {})
            if source_info.get('event_type') in ['toolUse', 'toolResult']:
                # Try to extract tool name from message text
                text = msg.get('text', '')
                if 'tool:' in text.lower():
                    # Extract tool name from text like "User requested tool: room_service"
                    parts = text.split('tool:')
                    if len(parts) > 1:
                        tool_name = parts[1].strip().split()[0]
                        tools_used.add(tool_name)
        
        return list(tools_used)
    
    def _format_conversation_data(self, session_id: str, chat_history: List[Dict], metadata: Dict) -> Dict:
        """
        Format conversation data for S3 storage with role validation and correction.
        
        Args:
            session_id: Unique session identifier
            chat_history: List of conversation messages
            metadata: Additional conversation metadata
            
        Returns:
            Dict: Formatted conversation data ready for JSON serialization
        """
        # Validate and correct roles in chat history
        validated_history = self._validate_and_correct_roles(chat_history)
        
        # Calculate accurate conversation statistics based on corrected roles
        user_messages = sum(1 for msg in validated_history if msg.get('role') == 'USER')
        assistant_messages = sum(1 for msg in validated_history if msg.get('role') == 'ASSISTANT')
        
        # Extract tools used from conversation
        tools_used = self._extract_tools_used(validated_history)
        
        # Format messages with validation
        conversation_messages = []
        for msg in validated_history:
            formatted_msg = {
                'role': msg.get('role', 'ASSISTANT'),  # Default to ASSISTANT if somehow still missing
                'text': msg.get('text', ''),
                'contentName': msg.get('contentName', ''),
                'timestamp': msg.get('timestamp', datetime.utcnow().isoformat() + 'Z')
            }
            
            # Include source info for debugging if present
            if 'source_info' in msg:
                formatted_msg['source_info'] = msg['source_info']
            
            conversation_messages.append(formatted_msg)
        
        # Build complete conversation data structure with accurate statistics
        conversation_data = {
            'session_id': session_id,
            'metadata': {
                'start_time': metadata.get('start_time', datetime.utcnow().isoformat() + 'Z'),
                'end_time': metadata.get('end_time', datetime.utcnow().isoformat() + 'Z'),
                'duration_seconds': metadata.get('duration_seconds', 0),
                'message_count': len(validated_history),
                'user_messages': user_messages,
                'assistant_messages': assistant_messages,
                'tools_used': tools_used,
                'role_corrections_made': len(chat_history) - len([msg for msg in chat_history if self.role_classifier.validate_role(msg.get('role', ''))])
            },
            'conversation': conversation_messages
        }
        
        # Log statistics for verification
        logger.info(f"Conversation statistics - Total: {len(validated_history)}, User: {user_messages}, Assistant: {assistant_messages}, Tools: {len(tools_used)}")
        
        return conversation_data
    
    def validate_conversation_data(self, conversation_data: Dict) -> Dict[str, Any]:
        """
        Validate conversation data integrity and return validation results.
        
        Args:
            conversation_data: Formatted conversation data
            
        Returns:
            Dict[str, Any]: Validation results with issues and statistics
        """
        validation_results = {
            'is_valid': True,
            'issues': [],
            'statistics': {},
            'role_distribution': {}
        }
        
        try:
            # Validate required fields
            required_fields = ['session_id', 'metadata', 'conversation']
            for field in required_fields:
                if field not in conversation_data:
                    validation_results['issues'].append(f"Missing required field: {field}")
                    validation_results['is_valid'] = False
            
            # Validate conversation messages
            conversation = conversation_data.get('conversation', [])
            role_counts = {'USER': 0, 'ASSISTANT': 0, 'INVALID': 0}
            
            for i, msg in enumerate(conversation):
                # Check required message fields
                if 'role' not in msg:
                    validation_results['issues'].append(f"Message {i+1} missing role field")
                    validation_results['is_valid'] = False
                    continue
                
                role = msg['role']
                if self.role_classifier.validate_role(role):
                    role_counts[role] += 1
                else:
                    role_counts['INVALID'] += 1
                    validation_results['issues'].append(f"Message {i+1} has invalid role: {role}")
                    validation_results['is_valid'] = False
                
                # Check for empty text
                if not msg.get('text', '').strip():
                    validation_results['issues'].append(f"Message {i+1} has empty text content")
            
            # Validate metadata statistics
            metadata = conversation_data.get('metadata', {})
            declared_user_count = metadata.get('user_messages', 0)
            declared_assistant_count = metadata.get('assistant_messages', 0)
            declared_total = metadata.get('message_count', 0)
            
            actual_user_count = role_counts['USER']
            actual_assistant_count = role_counts['ASSISTANT']
            actual_total = len(conversation)
            
            if declared_user_count != actual_user_count:
                validation_results['issues'].append(f"User message count mismatch: declared {declared_user_count}, actual {actual_user_count}")
                validation_results['is_valid'] = False
            
            if declared_assistant_count != actual_assistant_count:
                validation_results['issues'].append(f"Assistant message count mismatch: declared {declared_assistant_count}, actual {actual_assistant_count}")
                validation_results['is_valid'] = False
            
            if declared_total != actual_total:
                validation_results['issues'].append(f"Total message count mismatch: declared {declared_total}, actual {actual_total}")
                validation_results['is_valid'] = False
            
            # Set statistics
            validation_results['statistics'] = {
                'total_messages': actual_total,
                'user_messages': actual_user_count,
                'assistant_messages': actual_assistant_count,
                'invalid_roles': role_counts['INVALID'],
                'tools_used': len(metadata.get('tools_used', []))
            }
            
            validation_results['role_distribution'] = {
                'USER': actual_user_count,
                'ASSISTANT': actual_assistant_count,
                'INVALID': role_counts['INVALID']
            }
            
        except Exception as e:
            validation_results['is_valid'] = False
            validation_results['issues'].append(f"Validation error: {str(e)}")
        
        return validation_results
    
    async def upload_conversation(self, session_id: str, chat_history: List[Dict], metadata: Dict) -> bool:
        """
        Upload conversation to S3 with error handling and retry logic.
        
        Args:
            session_id: Unique session identifier
            chat_history: List of conversation messages
            metadata: Additional conversation metadata
            
        Returns:
            bool: True if upload successful, False otherwise
        """
        if not self.enabled:
            logger.debug("S3 storage disabled, skipping upload")
            return False
            
        if not self.s3_client or not self.bucket_name:
            logger.error("S3 client or bucket not configured")
            return False
            
        if not chat_history:
            logger.debug("No conversation history to upload")
            return False
        
        try:
            # Format conversation data with role validation and correction
            conversation_data = self._format_conversation_data(session_id, chat_history, metadata)
            
            # Validate conversation data integrity
            validation_results = self.validate_conversation_data(conversation_data)
            if not validation_results['is_valid']:
                logger.warning(f"Conversation validation issues found: {validation_results['issues']}")
                # Continue with upload but log the issues
            else:
                logger.debug("Conversation data validation passed")
            
            # Generate S3 key
            timestamp = datetime.fromisoformat(metadata.get('end_time', datetime.utcnow().isoformat()).replace('Z', '+00:00'))
            s3_key = self._generate_s3_key(session_id, timestamp)
            
            # Convert to JSON
            json_data = json.dumps(conversation_data, indent=2, ensure_ascii=False)
            
            # Set S3 object metadata for searchability
            s3_metadata = {
                'session-id': session_id,
                'message-count': str(conversation_data['metadata']['message_count']),
                'user-messages': str(conversation_data['metadata']['user_messages']),
                'assistant-messages': str(conversation_data['metadata']['assistant_messages']),
                'duration-seconds': str(conversation_data['metadata']['duration_seconds'])
            }
            
            # Upload to S3 with retry logic
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    self.s3_client.put_object(
                        Bucket=self.bucket_name,
                        Key=s3_key,
                        Body=json_data.encode('utf-8'),
                        ContentType='application/json',
                        Metadata=s3_metadata
                    )
                    
                    logger.info(f"Successfully uploaded conversation to S3: {s3_key}")
                    return True
                    
                except ClientError as e:
                    error_code = e.response['Error']['Code']
                    if attempt < max_retries - 1 and error_code in ['ServiceUnavailable', 'SlowDown']:
                        logger.warning(f"S3 upload attempt {attempt + 1} failed with {error_code}, retrying...")
                        continue
                    else:
                        logger.error(f"S3 upload failed after {attempt + 1} attempts: {e}")
                        return False
                        
        except json.JSONEncodeError as e:
            logger.error(f"Failed to serialize conversation data to JSON: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during S3 upload: {e}")
            return False
        
        return False
    
    def validate_startup_connectivity(self) -> bool:
        """
        Validate S3 connectivity during application startup.
        
        Returns:
            bool: True if S3 is properly configured and accessible
        """
        if not self.enabled:
            logger.info("S3 conversation storage is disabled")
            return True  # Not an error if disabled
            
        if not self.bucket_name:
            logger.error("S3 storage enabled but no bucket name configured")
            return False
            
        return self._validate_s3_connectivity()