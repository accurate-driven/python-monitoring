"""
Configuration management for Time Tracker
Loads settings from embedded config (if built) or .env file with defaults
"""

import os
from typing import Optional

# Try to import embedded config (generated during build)
try:
    from config_values import EmbeddedConfig
    EMBEDDED_CONFIG_AVAILABLE = True
except ImportError:
    EMBEDDED_CONFIG_AVAILABLE = False
    EmbeddedConfig = None

# Try to load .env file (only used during development, not in built executable)
try:
    from dotenv import load_dotenv
    load_dotenv()
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False


def _get_config_value(key: str, default, value_type=str):
    """Get config value from embedded config, .env, or default"""
    # First try embedded config (from build)
    if EMBEDDED_CONFIG_AVAILABLE and hasattr(EmbeddedConfig, key):
        return getattr(EmbeddedConfig, key)
    
    # Then try environment variable (for development)
    env_value = os.getenv(key)
    if env_value is not None:
        if value_type == bool:
            return env_value.lower() == 'true'
        elif value_type == float:
            return float(env_value)
        elif value_type == int:
            return int(env_value)
        else:
            return env_value
    
    # Finally use default
    return default


class Config:
    """Configuration class that loads settings from embedded config or environment variables"""
    
    # Screenshot Settings
    SCREENSHOT_INTERVAL: float = _get_config_value('SCREENSHOT_INTERVAL', 3.0, float)
    SCREENSHOT_IDLE_INTERVAL: float = _get_config_value('SCREENSHOT_IDLE_INTERVAL', 30.0, float)
    SCREENSHOT_ACTIVITY_TIMEOUT: float = _get_config_value('SCREENSHOT_ACTIVITY_TIMEOUT', 5.0, float)
    SCREENSHOT_QUALITY: int = _get_config_value('SCREENSHOT_QUALITY', 50, int)
    SCREENSHOT_SCALE: float = _get_config_value('SCREENSHOT_SCALE', 1.0, float)
    
    # Data Directory
    DATA_DIR: str = _get_config_value('DATA_DIR', 't_data', str)
    
    # Folder Rotation Settings
    FOLDER_ROTATION_INTERVAL: int = _get_config_value('FOLDER_ROTATION_INTERVAL', 180, int)
    FOLDER_MAX_SIZE_MB: int = _get_config_value('FOLDER_MAX_SIZE_MB', 10, int)
    
    # Backblaze B2 Configuration
    B2_KEY_ID: Optional[str] = _get_config_value('B2_KEY_ID', None, str)
    B2_KEY: Optional[str] = _get_config_value('B2_KEY', None, str)
    B2_BUCKET_NAME: Optional[str] = _get_config_value('B2_BUCKET_NAME', None, str)
    UPLOAD_TO_B2: bool = _get_config_value('UPLOAD_TO_B2', True, bool)
    DELETE_AFTER_UPLOAD: bool = _get_config_value('DELETE_AFTER_UPLOAD', False, bool)
    
    @classmethod
    def get_folder_max_size_bytes(cls) -> int:
        """Calculate folder max size in bytes"""
        return cls.FOLDER_MAX_SIZE_MB * 1024 * 1024

