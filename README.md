# Employee Time Tracking Application

A cross-platform time tracking application that monitors employee activity by:
- Capturing screenshots of all monitors every 2 seconds
- Recording keyboard and mouse events
- Tracking running processes/services

## Features

- **Multi-monitor Screenshot Capture**: Automatically captures screenshots from all connected monitors
- **Keyboard Monitoring**: Records all key presses and releases with timestamps
- **Mouse Activity Tracking**: Logs mouse clicks with coordinates and button information
- **Process Monitoring**: Tracks all running processes/services on the system
- **Cross-platform**: Works on Windows, Linux, and macOS

## Requirements

- Python 3.7 or higher
- Required packages (see `requirements.txt`)

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

**Note**: On Linux, you may need additional system packages:
```bash
# Ubuntu/Debian
sudo apt-get install python3-tk python3-dev

# For screenshots on Linux, you may need:
sudo apt-get install scrot
```

**Note**: On macOS, you may need to grant accessibility permissions:
- System Preferences → Security & Privacy → Privacy → Accessibility
- Add Terminal/Python to allowed apps

## Usage

Run the tracker:
```bash
python t.py
```

The application will:
- Start capturing screenshots every 2 seconds
- Begin monitoring keyboard and mouse events
- Track running processes every 5 seconds
- Save all data to the `t_data` directory

Press `Ctrl+C` to stop tracking.

## Data Storage

All tracking data is saved in the `t_data` directory:

- `screenshots/`: PNG images of all monitors with timestamps
- `events.jsonl`: JSON Lines file containing keyboard and mouse events
- `processes.jsonl`: JSON Lines file containing running processes snapshots

### Event Format

Each event in `events.jsonl`:
```json
{
  "type": "key_press",
  "timestamp": "2024-01-15T10:30:45.123456",
  "key": "a",
  "key_code": "Key.char('a')"
}
```

### Process Format

Each process snapshot in `processes.jsonl`:
```json
[
  {
    "pid": 1234,
    "name": "chrome.exe",
    "exe": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "username": "user",
    "status": "running",
    "create_time": 1234567890.0,
    "timestamp": "2024-01-15T10:30:45.123456"
  }
]
```

## Configuration

You can modify screenshot settings by editing `t.py`:

```python
tracker = TimeTracker(
    screenshot_interval=2.0,      # Interval in seconds between screenshots
    screenshot_quality=60,       # JPEG quality 1-100 (lower = smaller files, default: 60)
    screenshot_scale=0.7          # Scale factor 0.1-1.0 (lower = smaller files, default: 0.7)
)
```

**File Size Optimization:**
- **Quality**: Lower values (30-60) create much smaller files with acceptable quality
- **Scale**: Lower values (0.5-0.7) reduce resolution and file size significantly
- **Example**: `quality=50, scale=0.6` can reduce file size by 10-20x compared to full-size PNG
- Screenshots are saved as JPEG format (much smaller than PNG)

## Privacy & Legal Considerations

⚠️ **Important**: This application captures sensitive user data including:
- Screenshots of all monitors
- All keyboard input (including passwords if typed)
- Mouse activity
- Running processes

**Before deploying:**
1. Ensure you have proper legal authorization
2. Inform employees about monitoring
3. Comply with local privacy laws (GDPR, etc.)
4. Implement proper data encryption and access controls
5. Consider privacy-preserving alternatives (e.g., activity summaries instead of full screenshots)

## Platform-Specific Notes

### Windows
- Works out of the box
- May require running as administrator for some process information

### Linux
- Requires X11 or Wayland display server
- May need additional permissions for keyboard/mouse monitoring
- Install system packages as mentioned in Installation

### macOS
- Requires accessibility permissions (see Installation)
- May require running from Terminal with appropriate permissions

## Troubleshooting

**Screenshots not working:**
- Check display permissions
- On Linux, ensure X11/Wayland is running
- On macOS, grant screen recording permissions

**Keyboard/mouse events not captured:**
- On Linux, may need to run with appropriate permissions
- On macOS, grant accessibility permissions
- Check if another application is blocking input monitoring

**Process monitoring incomplete:**
- On Windows/Linux, may need administrator/root privileges
- Some processes may be hidden by the OS

## License

This is a monitoring tool. Use responsibly and in compliance with applicable laws and regulations.

