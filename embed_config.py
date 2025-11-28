"""
Script to embed .env configuration into the executable during build
Reads .env file and generates config_values.py with hardcoded values
"""

import os
from pathlib import Path

def embed_config():
    """Read .env and create config_values.py with embedded values"""
    env_file = Path(".env")
    config_values_file = Path("config_values.py")
    
    if not env_file.exists():
        print("Warning: .env file not found. Using defaults.")
        return
    
    # Read .env file
    env_vars = {}
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            # Parse key=value
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")  # Remove quotes if present
                if key:  # Only add if key is not empty
                    env_vars[key] = value
    
    # Generate config_values.py
    config_content = '''"""
Embedded configuration values (generated from .env during build)
This file is auto-generated - do not edit manually
"""

from typing import Optional

class EmbeddedConfig:
    """Embedded configuration values from .env file"""
'''
    
    # Add each config value
    for key, value in env_vars.items():
        # Determine Python type
        if value.lower() in ('true', 'false'):
            python_value = value.lower() == 'true'
            config_content += f'    {key}: bool = {python_value}\n'
        elif value.replace('.', '', 1).replace('-', '', 1).isdigit():
            # It's a number
            if '.' in value:
                config_content += f'    {key}: float = {value}\n'
            else:
                config_content += f'    {key}: int = {value}\n'
        else:
            # It's a string
            config_content += f'    {key}: Optional[str] = {repr(value)}\n'
    
    # Write config_values.py
    with open(config_values_file, 'w', encoding='utf-8') as f:
        f.write(config_content)
    
    print(f"[OK] Embedded configuration from .env into config_values.py")
    print(f"     Found {len(env_vars)} configuration values")


if __name__ == "__main__":
    embed_config()

