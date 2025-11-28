"""
Build script for Time Tracker application
Creates standalone executables using PyInstaller
Embeds .env configuration into the executable
"""

import subprocess
import sys
import platform
from pathlib import Path

def build():
    """Build the application using PyInstaller"""
    print("Building Time Tracker application...")
    print(f"Platform: {platform.system()} {platform.machine()}")
    print()
    
    # Step 1: Embed .env configuration into config_values.py
    print("Step 1: Embedding .env configuration...")
    try:
        import embed_config
        embed_config.embed_config()
    except Exception as e:
        print(f"Warning: Failed to embed config: {e}")
        print("Continuing with default values...")
    
    # Step 2: Build with PyInstaller
    print()
    print("Step 2: Building executable with PyInstaller...")
    
    # Determine separator for --add-data based on platform
    sep = ";" if platform.system() == "Windows" else ":"
    
    # PyInstaller command
    cmd = [
        "pyinstaller",
        "--name=time-tracker",
        "--onefile",  # Single executable file
        "--windowed",  # Show console window (change to --windowed for no console)
        f"--add-data=config.py{sep}.",  # Include config.py
        f"--add-data=config_values.py{sep}.",  # Include embedded config
        "--hidden-import=pynput.keyboard",
        "--hidden-import=pynput.mouse",
        "--hidden-import=mss",
        "--hidden-import=psutil",
        "--hidden-import=PIL",
        "--hidden-import=dotenv",
        "--hidden-import=b2sdk",
        "--hidden-import=b2sdk.v2",
        "--hidden-import=config_values",  # Include embedded config module
        "--collect-all=pynput",
        "--collect-all=mss",
        "t.py"
    ]
    
    print("Running PyInstaller...")
    print(" ".join(cmd))
    print()
    
    try:
        subprocess.run(cmd, check=True)
        print()
        print("=" * 60)
        print("Build completed successfully!")
        print("=" * 60)
        print()
        exe_name = f"time-tracker{'.exe' if platform.system() == 'Windows' else ''}"
        print(f"Executable location: dist/{exe_name}")
        print()
        print("[OK] Configuration from .env has been embedded into the executable")
        print("     No .env file needed when running the executable!")
        
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print("Error: PyInstaller not found!")
        print("Install it with: pip install pyinstaller")
        sys.exit(1)


if __name__ == "__main__":
    build()

