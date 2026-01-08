"""
S3 Configuration Management

This module provides configuration management for S3 conversation storage,
including environment variable validation and default settings.
"""

import os
from typing import Optional, Dict, Any
from dotenv import load_dotenv
import pathlib

# Load environment variables from .env file in backend directory
backend_dir = pathlib.Path(__file__).parent.parent
load_dotenv(backend_dir / '.env')


class S3Config:
    """Configuration class for S3 conversation storage."""
    
    # Default configuration values
    DEFAULT_BUCKET = 'strand112'
    DEFAULT_PREFIX = 'askimo-audio-output/conversations'
    DEFAULT_REGION = 'us-east-1'
    DEFAULT_ENABLED = True
    
    @classmethod
    def get_config(cls) -> Dict[str, Any]:
        """
        Get complete S3 configuration from environment variables.
        
        Returns:
            Dict containing all S3 configuration settings
        """
        return {
            'enabled': cls.is_enabled(),
            'bucket_name': cls.get_bucket_name(),
            'prefix': cls.get_prefix(),
            'region': cls.get_region(),
            'credentials': cls.get_credentials()
        }
    
    @classmethod
    def is_enabled(cls) -> bool:
        """Check if S3 conversation storage is enabled."""
        return os.getenv('S3_CONVERSATION_ENABLED', str(cls.DEFAULT_ENABLED)).lower() == 'true'
    
    @classmethod
    def get_bucket_name(cls) -> str:
        """Get S3 bucket name."""
        return os.getenv('S3_CONVERSATION_BUCKET', cls.DEFAULT_BUCKET)
    
    @classmethod
    def get_prefix(cls) -> str:
        """Get S3 key prefix for conversations."""
        return os.getenv('S3_CONVERSATION_PREFIX', cls.DEFAULT_PREFIX)
    
    @classmethod
    def get_region(cls) -> str:
        """Get AWS region."""
        return os.getenv('AWS_REGION', cls.DEFAULT_REGION)
    
    @classmethod
    def get_credentials(cls) -> Dict[str, Optional[str]]:
        """Get AWS credentials from environment variables."""
        return {
            'aws_access_key_id': os.getenv('aws_access_key_id'),
            'aws_secret_access_key': os.getenv('aws_secret_access_key'),
            'aws_session_token': os.getenv('aws_session_token')
        }
    
    @classmethod
    def validate_config(cls) -> Dict[str, Any]:
        """
        Validate S3 configuration and return validation results.
        
        Returns:
            Dict containing validation results and any issues found
        """
        issues = []
        config = cls.get_config()
        
        if config['enabled']:
            # Check required settings
            if not config['bucket_name']:
                issues.append("S3_CONVERSATION_BUCKET is required when S3 storage is enabled")
            
            # Check credentials
            creds = config['credentials']
            if not creds['aws_access_key_id']:
                issues.append("aws_access_key_id is required")
            if not creds['aws_secret_access_key']:
                issues.append("aws_secret_access_key is required")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'config': config
        }


def print_config_summary():
    """Print a summary of the current S3 configuration."""
    validation = S3Config.validate_config()
    config = validation['config']
    
    print("S3 Conversation Storage Configuration")
    print("=" * 40)
    print(f"Enabled: {config['enabled']}")
    print(f"Bucket: {config['bucket_name']}")
    print(f"Prefix: {config['prefix']}")
    print(f"Region: {config['region']}")
    print(f"Has Access Key: {'Yes' if config['credentials']['aws_access_key_id'] else 'No'}")
    print(f"Has Secret Key: {'Yes' if config['credentials']['aws_secret_access_key'] else 'No'}")
    print(f"Has Session Token: {'Yes' if config['credentials']['aws_session_token'] else 'No'}")
    
    if validation['valid']:
        print("\n✅ Configuration is valid")
    else:
        print("\n❌ Configuration issues found:")
        for issue in validation['issues']:
            print(f"  - {issue}")
    
    print("=" * 40)


if __name__ == "__main__":
    print_config_summary()