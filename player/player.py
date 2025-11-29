"""
Player Application
Downloads zip files from B2 and plays screenshots
"""

import os
import zipfile
import shutil
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import time
import threading

from config import Config

# Backblaze B2 imports
try:
    from b2sdk.v2 import InMemoryAccountInfo, B2Api
    from b2sdk.v2.exception import B2Error
    B2_AVAILABLE = True
except ImportError:
    B2_AVAILABLE = False
    print("Error: b2sdk not installed. Install with: pip install b2sdk")
    exit(1)


class B2Downloader:
    """Handles downloading files from Backblaze B2"""
    
    def __init__(self):
        self.b2_api: Optional[B2Api] = None
        self.b2_bucket = None
        self._init_b2()
    
    def _init_b2(self):
        """Initialize Backblaze B2 API"""
        if not B2_AVAILABLE:
            raise RuntimeError("b2sdk not installed")
        
        if not Config.B2_KEY_ID or not Config.B2_KEY or not Config.B2_BUCKET_NAME:
            raise RuntimeError("B2 credentials not configured. Please set B2_KEY_ID, B2_KEY, and B2_BUCKET_NAME in .env")
        
        info = InMemoryAccountInfo()
        self.b2_api = B2Api(info)
        self.b2_api.authorize_account("production", Config.B2_KEY_ID, Config.B2_KEY)
        self.b2_bucket = self.b2_api.get_bucket_by_name(Config.B2_BUCKET_NAME)
        print(f"Connected to B2 bucket: {Config.B2_BUCKET_NAME}")
    
    def list_files(self) -> List[Dict]:
        """List all zip files in the B2 bucket"""
        files = []
        try:
            for file_info, folder_name in self.b2_bucket.ls(recursive=False):
                if file_info.file_name.endswith('.zip'):
                    # Parse file info
                    file_data = {
                        'name': file_info.file_name,
                        'size': file_info.size,
                        'upload_timestamp': file_info.upload_timestamp / 1000,  # Convert to seconds
                        'upload_date': datetime.fromtimestamp(file_info.upload_timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S'),
                        'file_info': file_info.file_info if hasattr(file_info, 'file_info') else {}
                    }
                    files.append(file_data)
        except Exception as e:
            print(f"Error listing files: {e}")
            raise
        
        # Sort by upload timestamp (newest first)
        files.sort(key=lambda x: x['upload_timestamp'], reverse=True)
        return files
    
    def download_file(self, remote_path: str, local_path: Path) -> bool:
        """Download a file from B2"""
        try:
            print(f"Downloading {remote_path}...")
            downloaded_file = self.b2_bucket.download_file_by_name(remote_path)
            downloaded_file.save_to(str(local_path))
            print(f"✓ Downloaded {remote_path}")
            return True
        except Exception as e:
            print(f"✗ Error downloading {remote_path}: {e}")
            return False


class ScreenshotPlayer:
    """Plays screenshots from extracted session folders"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Screenshot Player")
        self.root.geometry("1200x800")
        
        self.current_session: Optional[Path] = None
        self.screenshots: List[Dict] = []
        self.current_index = 0
        self.is_playing = False
        self.playback_speed = Config.PLAYBACK_SPEED
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the user interface"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Lists frame (two columns)
        lists_frame = ttk.Frame(main_frame)
        lists_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        lists_frame.columnconfigure(0, weight=1)
        lists_frame.columnconfigure(1, weight=1)
        
        # Left: B2 files list
        b2_frame = ttk.LabelFrame(lists_frame, text="B2 Sessions (Remote)", padding="5")
        b2_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        b2_frame.columnconfigure(0, weight=1)
        b2_frame.rowconfigure(0, weight=1)
        
        # B2 Treeview with columns
        b2_tree_frame = ttk.Frame(b2_frame)
        b2_tree_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        b2_tree_frame.columnconfigure(0, weight=1)
        b2_tree_frame.rowconfigure(0, weight=1)
        
        b2_scrollbar = ttk.Scrollbar(b2_tree_frame)
        b2_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        self.b2_treeview = ttk.Treeview(b2_tree_frame, columns=("size", "downloaded"), show="tree headings", yscrollcommand=b2_scrollbar.set, height=10)
        self.b2_treeview.heading("#0", text="Session", anchor=tk.W)
        self.b2_treeview.heading("size", text="Size", anchor=tk.E)
        self.b2_treeview.heading("downloaded", text="Downloaded", anchor=tk.CENTER)
        self.b2_treeview.column("#0", width=250, anchor=tk.W)
        self.b2_treeview.column("size", width=100, anchor=tk.E)
        self.b2_treeview.column("downloaded", width=100, anchor=tk.CENTER)
        self.b2_treeview.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        b2_scrollbar.config(command=self.b2_treeview.yview)
        
        # Right: Downloaded files list
        downloads_frame = ttk.LabelFrame(lists_frame, text="Downloaded Sessions (Local)", padding="5")
        downloads_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 0))
        downloads_frame.columnconfigure(0, weight=1)
        downloads_frame.rowconfigure(0, weight=1)
        
        # Downloads Treeview with columns
        downloads_tree_frame = ttk.Frame(downloads_frame)
        downloads_tree_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        downloads_tree_frame.columnconfigure(0, weight=1)
        downloads_tree_frame.rowconfigure(0, weight=1)
        
        downloads_scrollbar = ttk.Scrollbar(downloads_tree_frame)
        downloads_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        self.downloads_treeview = ttk.Treeview(downloads_tree_frame, columns=("start_time", "end_time"), show="tree headings", yscrollcommand=downloads_scrollbar.set, height=10)
        self.downloads_treeview.heading("#0", text="Session", anchor=tk.W)
        self.downloads_treeview.heading("start_time", text="Start Time", anchor=tk.W)
        self.downloads_treeview.heading("end_time", text="End Time", anchor=tk.W)
        self.downloads_treeview.column("#0", width=200, anchor=tk.W)
        self.downloads_treeview.column("start_time", width=180, anchor=tk.W)
        self.downloads_treeview.column("end_time", width=180, anchor=tk.W)
        self.downloads_treeview.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        downloads_scrollbar.config(command=self.downloads_treeview.yview)
        
        # Buttons frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.grid(row=1, column=0, columnspan=2, pady=5)
        
        ttk.Button(buttons_frame, text="Refresh B2 List", command=self.refresh_file_list).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Download Selected", command=self.download_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Refresh Downloads", command=self.refresh_downloads_list).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Load Session", command=self.load_session).pack(side=tk.LEFT, padx=5)
        
        # Image display frame
        image_frame = ttk.LabelFrame(main_frame, text="Screenshot Viewer", padding="5")
        image_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        self.image_label = ttk.Label(image_frame, text="No image loaded")
        self.image_label.pack(expand=True, fill=tk.BOTH)
        
        # Control frame
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=3, column=0, columnspan=2, pady=5)
        
        ttk.Button(control_frame, text="⏮ First", command=self.first_screenshot).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="⏪ Prev", command=self.prev_screenshot).pack(side=tk.LEFT, padx=2)
        self.play_button = ttk.Button(control_frame, text="▶ Play", command=self.toggle_play)
        self.play_button.pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="⏩ Next", command=self.next_screenshot).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="⏭ Last", command=self.last_screenshot).pack(side=tk.LEFT, padx=2)
        
        # Status frame
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.status_label = ttk.Label(status_frame, text="Ready")
        self.status_label.pack(side=tk.LEFT)
        
        self.progress_label = ttk.Label(status_frame, text="")
        self.progress_label.pack(side=tk.RIGHT)
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1)  # Lists frame
        main_frame.rowconfigure(2, weight=1)  # Image frame
        lists_frame.rowconfigure(0, weight=1)
        image_frame.columnconfigure(0, weight=1)
        image_frame.rowconfigure(0, weight=1)
    
    def refresh_file_list(self):
        """Refresh the list of available files from B2"""
        try:
            self.status_label.config(text="Refreshing B2 file list...")
            downloader = B2Downloader()
            files = downloader.list_files()
            
            # Get list of downloaded session names
            downloaded_sessions = self._get_downloaded_session_names()
            
            # Clear existing items
            for item in self.b2_treeview.get_children():
                self.b2_treeview.delete(item)
            
            for file_info in files:
                session_name = file_info['name'].replace('.zip', '')
                is_downloaded = session_name in downloaded_sessions
                downloaded_status = "Yes" if is_downloaded else "No"
                size_mb = file_info['size'] / (1024 * 1024)
                size_text = f"{size_mb:.2f} MB"
                
                self.b2_treeview.insert("", tk.END, text=session_name, values=(size_text, downloaded_status))
            
            self.status_label.config(text=f"Found {len(files)} session(s) in B2")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to refresh B2 file list: {e}")
            self.status_label.config(text="Error refreshing B2 file list")
    
    def _get_downloaded_session_names(self) -> set:
        """Get set of downloaded session folder names"""
        download_dir = Path(Config.DOWNLOAD_DIR)
        if not download_dir.exists():
            return set()
        
        session_folders = [
            d.name for d in download_dir.iterdir() 
            if d.is_dir() and d.name.startswith("session_")
        ]
        return set(session_folders)
    
    def refresh_downloads_list(self):
        """Refresh the list of downloaded sessions"""
        download_dir = Path(Config.DOWNLOAD_DIR)
        if not download_dir.exists():
            # Clear existing items
            for item in self.downloads_treeview.get_children():
                self.downloads_treeview.delete(item)
            self.status_label.config(text="No downloads directory found")
            return
        
        # Find session folders
        session_folders = sorted(
            [d for d in download_dir.iterdir() if d.is_dir() and d.name.startswith("session_")],
            reverse=True
        )
        
        # Clear existing items
        for item in self.downloads_treeview.get_children():
            self.downloads_treeview.delete(item)
        
        for folder in session_folders:
            # Extract start_time and end_time from events.jsonl
            start_time = "Unknown"
            end_time = "Unknown"
            
            events_file = folder / "events.jsonl"
            if events_file.exists():
                try:
                    timestamps = []
                    with open(events_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            event = json.loads(line.strip())
                            if 'timestamp' in event:
                                timestamps.append(event['timestamp'])
                    
                    if timestamps:
                        # Parse timestamps
                        try:
                            start_dt = datetime.fromisoformat(timestamps[0].replace('Z', '+00:00'))
                            end_dt = datetime.fromisoformat(timestamps[-1].replace('Z', '+00:00'))
                            start_time = start_dt.strftime('%Y-%m-%d %H:%M:%S')
                            end_time = end_dt.strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            # Fallback: use first and last timestamp as-is
                            start_time = timestamps[0][:19] if len(timestamps[0]) > 19 else timestamps[0]
                            end_time = timestamps[-1][:19] if len(timestamps[-1]) > 19 else timestamps[-1]
                except Exception as e:
                    print(f"Warning: Could not parse events.jsonl for {folder.name}: {e}")
            
            self.downloads_treeview.insert("", tk.END, text=folder.name, values=(start_time, end_time))
        
        self.status_label.config(text=f"Found {len(session_folders)} downloaded session(s)")
    
    def download_selected(self):
        """Download the selected file from B2"""
        selection = self.b2_treeview.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a file from B2 list to download")
            return
        
        # Get session name from selected item
        item = self.b2_treeview.item(selection[0])
        session_name = item['text']
        file_name = f"{session_name}.zip"
        
        try:
            self.status_label.config(text=f"Downloading {file_name}...")
            download_dir = Path(Config.DOWNLOAD_DIR)
            download_dir.mkdir(parents=True, exist_ok=True)
            
            zip_path = download_dir / file_name
            
            downloader = B2Downloader()
            if downloader.download_file(file_name, zip_path):
                # Extract zip file
                self.status_label.config(text=f"Extracting {file_name}...")
                extract_dir = download_dir / file_name.replace('.zip', '')
                
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    # Extract all files
                    zip_ref.extractall(extract_dir)
                    
                    # If zip contains session_name/screenshots structure, move files up one level
                    # Check if there's a nested session folder
                    nested_session = None
                    for item in extract_dir.iterdir():
                        if item.is_dir() and item.name.startswith('session_'):
                            nested_session = item
                            break
                    
                    if nested_session:
                        # Move contents of nested session folder to extract_dir
                        for item in nested_session.iterdir():
                            dest = extract_dir / item.name
                            if item.is_dir():
                                if dest.exists():
                                    shutil.rmtree(dest)
                                shutil.move(str(item), str(dest))
                            else:
                                if dest.exists():
                                    dest.unlink()
                                shutil.move(str(item), str(dest))
                        # Remove empty nested folder
                        nested_session.rmdir()
                
                # Remove zip file after extraction
                zip_path.unlink()
                
                self.status_label.config(text=f"✓ Downloaded and extracted {file_name}")
                # Refresh both lists
                self.refresh_downloads_list()
                self.refresh_file_list()  # Update "Downloaded" status in B2 list
                messagebox.showinfo("Success", f"Downloaded and extracted {file_name}")
            else:
                self.status_label.config(text="Download failed")
                messagebox.showerror("Error", f"Failed to download {file_name}")
        except Exception as e:
            messagebox.showerror("Error", f"Error downloading file: {e}")
            self.status_label.config(text="Error")
    
    def load_session(self):
        """Load a session folder from downloads list"""
        selection = self.downloads_treeview.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a session from Downloads list to load")
            return
        
        download_dir = Path(Config.DOWNLOAD_DIR)
        if not download_dir.exists():
            messagebox.showwarning("No Downloads", "No downloads directory found.")
            return
        
        # Get session name from selected item
        item = self.downloads_treeview.item(selection[0])
        session_name = item['text']
        
        session_folder = download_dir / session_name
        if not session_folder.exists():
            messagebox.showerror("Error", f"Session folder not found: {session_name}")
            return
        
        self.load_session_folder(session_folder)
    
    def load_session_folder(self, session_folder: Path):
        """Load screenshots from a session folder"""
        self.current_session = session_folder
        screenshots_dir = session_folder / "screenshots"
        
        if not screenshots_dir.exists():
            messagebox.showerror("Error", f"No screenshots directory found in {session_folder.name}")
            return
        
        # Load events.jsonl to get screenshot metadata
        events_file = session_folder / "events.jsonl"
        screenshot_timestamps = {}
        
        if events_file.exists():
            try:
                with open(events_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        event = json.loads(line.strip())
                        if event.get('type') == 'screenshot' and 'data' in event:
                            screenshot_data = event['data']
                            timestamp = screenshot_data.get('timestamp')
                            if timestamp and 'monitors' in screenshot_data:
                                for monitor in screenshot_data['monitors']:
                                    filename = monitor.get('filename')
                                    if filename:
                                        screenshot_timestamps[filename] = timestamp
            except Exception as e:
                print(f"Warning: Could not parse events.jsonl: {e}")
        
        # Get all screenshot files
        self.screenshots = []
        for screenshot_file in sorted(screenshots_dir.glob("*.jpg")):
            timestamp = screenshot_timestamps.get(screenshot_file.name, "")
            self.screenshots.append({
                'path': screenshot_file,
                'filename': screenshot_file.name,
                'timestamp': timestamp
            })
        
        if not self.screenshots:
            messagebox.showwarning("No Screenshots", f"No screenshots found in {session_folder.name}")
            return
        
        self.current_index = 0
        self.is_playing = False
        self.display_screenshot(0)
        self.status_label.config(text=f"Loaded {len(self.screenshots)} screenshots from {session_folder.name}")
        self.update_progress()
    
    def display_screenshot(self, index: int):
        """Display screenshot at given index"""
        if not self.screenshots or index < 0 or index >= len(self.screenshots):
            return
        
        screenshot = self.screenshots[index]
        try:
            # Load and display image
            img = Image.open(screenshot['path'])
            
            # Resize to fit window (max 1000x700)
            max_width, max_height = 1000, 700
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            
            photo = ImageTk.PhotoImage(img)
            self.image_label.config(image=photo, text="")
            self.image_label.image = photo  # Keep a reference
            
            self.current_index = index
            self.update_progress()
        except Exception as e:
            print(f"Error displaying screenshot: {e}")
            self.image_label.config(text=f"Error loading image: {e}")
    
    def update_progress(self):
        """Update progress label"""
        if self.screenshots:
            self.progress_label.config(
                text=f"{self.current_index + 1} / {len(self.screenshots)}"
            )
    
    def first_screenshot(self):
        """Go to first screenshot"""
        self.is_playing = False
        self.display_screenshot(0)
    
    def prev_screenshot(self):
        """Go to previous screenshot"""
        self.is_playing = False
        if self.current_index > 0:
            self.display_screenshot(self.current_index - 1)
    
    def next_screenshot(self):
        """Go to next screenshot"""
        self.is_playing = False
        if self.current_index < len(self.screenshots) - 1:
            self.display_screenshot(self.current_index + 1)
    
    def last_screenshot(self):
        """Go to last screenshot"""
        self.is_playing = False
        if self.screenshots:
            self.display_screenshot(len(self.screenshots) - 1)
    
    def toggle_play(self):
        """Toggle play/pause"""
        if not self.screenshots:
            return
        
        self.is_playing = not self.is_playing
        if self.is_playing:
            self.play_button.config(text="⏸ Pause")
            self.play_loop()
        else:
            self.play_button.config(text="▶ Play")
    
    def play_loop(self):
        """Play screenshots automatically"""
        if not self.is_playing or not self.screenshots:
            return
        
        if self.current_index >= len(self.screenshots) - 1:
            # Reached end, stop playing
            self.is_playing = False
            self.play_button.config(text="▶ Play")
            return
        
        # Calculate delay based on screenshot interval (default 5 seconds, adjusted by playback speed)
        # Try to extract interval from events.jsonl or use default
        delay = 5.0 / self.playback_speed  # Default 5 seconds, adjusted by speed
        
        # Move to next screenshot
        self.current_index += 1
        self.display_screenshot(self.current_index)
        
        # Schedule next frame
        if self.is_playing:
            self.root.after(int(delay * 1000), self.play_loop)


def main():
    """Main entry point"""
    if not B2_AVAILABLE:
        print("Error: b2sdk not installed. Install with: pip install b2sdk")
        return
    
    # Check B2 configuration
    if not Config.B2_KEY_ID or not Config.B2_KEY or not Config.B2_BUCKET_NAME:
        print("Error: B2 credentials not configured.")
        print("Please create a .env file with:")
        print("B2_KEY_ID=your_key_id")
        print("B2_KEY=your_key")
        print("B2_BUCKET_NAME=your_bucket_name")
        return
    
    root = tk.Tk()
    app = ScreenshotPlayer(root)
    
    # Auto-refresh both lists on startup
    app.refresh_file_list()
    app.refresh_downloads_list()
    
    root.mainloop()


if __name__ == "__main__":
    main()

