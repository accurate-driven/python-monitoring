"""
Configuration management for Time Tracker
Loads settings from .env file with defaults
"""

import os
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False


class Config:
    """Configuration class that loads settings from environment variables"""
    
    # Screenshot Settings
    SCREENSHOT_INTERVAL: float = float(os.getenv('SCREENSHOT_INTERVAL', '3.0'))
    SCREENSHOT_IDLE_INTERVAL: float = float(os.getenv('SCREENSHOT_IDLE_INTERVAL', '30.0'))  # When no activity
    SCREENSHOT_ACTIVITY_TIMEOUT: float = float(os.getenv('SCREENSHOT_ACTIVITY_TIMEOUT', '5.0'))  # Seconds of inactivity before switching to idle
    SCREENSHOT_QUALITY: int = int(os.getenv('SCREENSHOT_QUALITY', '50'))
    SCREENSHOT_SCALE: float = float(os.getenv('SCREENSHOT_SCALE', '1.0'))
    
    # Data Directory
    DATA_DIR: str = os.getenv('DATA_DIR', 't_data')
    
    # Folder Rotation Settings
    FOLDER_ROTATION_INTERVAL: int = int(os.getenv('FOLDER_ROTATION_INTERVAL', '180'))  # seconds
    FOLDER_MAX_SIZE_MB: int = int(os.getenv('FOLDER_MAX_SIZE_MB', '10'))  # MB
    
    # Backblaze B2 Configuration
    B2_KEY_ID: Optional[str] = os.getenv('B2_KEY_ID')
    B2_KEY: Optional[str] = os.getenv('B2_KEY')
    B2_BUCKET_NAME: Optional[str] = os.getenv('B2_BUCKET_NAME')
    UPLOAD_TO_B2: bool = os.getenv('UPLOAD_TO_B2', 'true').lower() == 'true'
    DELETE_AFTER_UPLOAD: bool = os.getenv('DELETE_AFTER_UPLOAD', 'false').lower() == 'true'
    
    @classmethod
    def get_folder_max_size_bytes(cls) -> int:
        """Calculate folder max size in bytes"""
        return cls.FOLDER_MAX_SIZE_MB * 1024 * 1024

