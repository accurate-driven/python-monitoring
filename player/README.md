# Screenshot Player

A GUI application to download and play screenshots from Backblaze B2 storage.

## Features

- **List Sessions**: View all available session zip files uploaded to B2
- **Download Sessions**: Download and extract session zip files from B2
- **Play Screenshots**: View screenshots in a timeline viewer with play/pause controls
- **Navigation**: Navigate through screenshots with first/prev/next/last buttons

## Requirements

- Python 3.7 or higher
- Required packages (see `requirements.txt`)

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file (copy from `.env.example`):
```bash
cp .env.example .env
```

3. Edit `.env` and add your B2 credentials:
```
B2_KEY_ID=your_b2_key_id_here
B2_KEY=your_b2_key_here
B2_BUCKET_NAME=your_bucket_name_here
```

## Usage

Run the player:
```bash
python player.py
```

### How to Use

1. **Refresh List**: Click "Refresh List" to fetch all available sessions from B2
2. **Download**: Select a session from the list and click "Download Selected"
3. **Load Session**: Click "Load Session" and select a downloaded session folder
4. **Play**: Use the play button to automatically play through screenshots
5. **Navigate**: Use First/Prev/Next/Last buttons to navigate manually

## Configuration

Edit `.env` to configure:

- `DOWNLOAD_DIR`: Directory where downloaded sessions are stored (default: `downloads`)
- `PLAYBACK_SPEED`: Playback speed multiplier (default: 1.0)
- `AUTO_PLAY`: Auto-play when session is loaded (default: false)

## File Structure

Downloaded sessions are extracted to:
```
downloads/
  session_20241129_120000/
    screenshots/
      *.jpg
    events.jsonl
    processes.jsonl
```

