"""
Configuration management for Player
Loads settings from .env file
"""

import os
from pathlib import Path
from typing import Optional

# Try to load .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False


def _get_config_value(key: str, default, value_type=str):
    """Get config value from environment variables or default"""
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
    
    # Use default
    return default


class Config:
    """Configuration class that loads settings from environment variables"""
    
    # Backblaze B2 Configuration
    B2_KEY_ID: Optional[str] = _get_config_value('B2_KEY_ID', None, str)
    B2_KEY: Optional[str] = _get_config_value('B2_KEY', None, str)
    B2_BUCKET_NAME: Optional[str] = _get_config_value('B2_BUCKET_NAME', None, str)
    
    # Player Settings
    DOWNLOAD_DIR: str = _get_config_value('DOWNLOAD_DIR', str(Path.cwd() / "downloads"), str)
    PLAYBACK_SPEED: float = _get_config_value('PLAYBACK_SPEED', 1.0, float)  # Multiplier for screenshot interval
    AUTO_PLAY: bool = _get_config_value('AUTO_PLAY', False, bool)

