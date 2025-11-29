# Building Time Tracker Application

This guide explains how to build a standalone executable for the Time Tracker application.

## Prerequisites

1. Install Python 3.7 or higher
2. Install build dependencies:
   ```bash
   pip install -r requirements-build.txt
   ```

## Building the Application

### Option 1: Using the build script (Recommended)

```bash
python build.py
```

This will create a single executable file in the `dist/` directory.

### Option 2: Using PyInstaller directly

```bash
# For Windows (console version - shows output)
pyinstaller --name=vmnetdch --onefile --console --add-data="config.py;." t.py

# For Windows (windowed version - no console)
pyinstaller --name=vmnetdch --onefile --windowed --add-data="config.py;." t.py

# For Linux/Mac (console version)
pyinstaller --name=vmnetdch --onefile --console --add-data="config.py:." t.py

# For Linux/Mac (windowed version)
pyinstaller --name=vmnetdch --onefile --windowed --add-data="config.py:." t.py
```

### Option 3: Using the spec file

```bash
pyinstaller build.spec
```

## Output

After building, you'll find:
- **Executable**: `dist/vmnetdch.exe` (Windows) or `dist/vmnetdch` (Linux/Mac)
- **Build files**: `build/` directory (can be deleted after building)

## Distribution

To distribute the application:

1. Copy the executable from `dist/` directory
2. That's it! The `.env` configuration is embedded in the executable

### Important Notes:

- **Configuration**: The `.env` file values are embedded into the executable during build
- **No .env needed**: Users don't need a `.env` file - everything is in the executable
- **Permissions**: On Linux/Mac, users may need to grant accessibility permissions for keyboard/mouse monitoring
- **Dependencies**: The executable is standalone and doesn't require Python to be installed
- **File Size**: The executable will be large (50-100MB) because it includes Python and all dependencies

## Platform-Specific Notes

### Windows
- The executable will be `vmnetdch.exe`
- No additional setup required
- May trigger antivirus warnings (false positive) due to keyboard/mouse monitoring

### Linux
- The executable will be `vmnetdch`
- May need to make it executable: `chmod +x vmnetdch`
- May need system packages for screenshots (scrot, etc.)

### macOS
- The executable will be `vmnetdch`
- May need to grant accessibility permissions in System Preferences
- May need to sign the executable for distribution

## Troubleshooting

### Build fails with "ModuleNotFoundError"
- Make sure all dependencies are installed: `pip install -r requirements.txt`
- Try adding the missing module to `hiddenimports` in `build.spec`

### Executable doesn't work
- Check if `.env` file exists in the same directory as the executable
- Run from command line to see error messages (use `--console` flag)
- Check file permissions (Linux/Mac)

### Antivirus flags the executable
- This is a false positive due to keyboard/mouse monitoring
- You may need to sign the executable or add it to antivirus exclusions

