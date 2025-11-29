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
        
        self.b2_treeview = ttk.Treeview(b2_tree_frame, columns=("size", "downloaded", "select"), show="tree headings", yscrollcommand=b2_scrollbar.set, height=10)
        self.b2_treeview.heading("#0", text="Session", anchor=tk.W)
        self.b2_treeview.heading("size", text="Size", anchor=tk.E)
        self.b2_treeview.heading("downloaded", text="Downloaded", anchor=tk.CENTER)
        self.b2_treeview.heading("select", text="Select", anchor=tk.CENTER)
        self.b2_treeview.column("#0", width=200, anchor=tk.W)
        self.b2_treeview.column("size", width=80, anchor=tk.E)
        self.b2_treeview.column("downloaded", width=80, anchor=tk.CENTER)
        self.b2_treeview.column("select", width=60, anchor=tk.CENTER)
        self.b2_treeview.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        b2_scrollbar.config(command=self.b2_treeview.yview)
        
        # Bind click on select column to toggle checkbox
        self.b2_treeview.bind('<Button-1>', self._on_b2_click)
        
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
        
        self.downloads_treeview = ttk.Treeview(downloads_tree_frame, columns=("start_time", "end_time", "select"), show="tree headings", yscrollcommand=downloads_scrollbar.set, height=10)
        self.downloads_treeview.heading("#0", text="Session", anchor=tk.W)
        self.downloads_treeview.heading("start_time", text="Start Time", anchor=tk.W)
        self.downloads_treeview.heading("end_time", text="End Time", anchor=tk.W)
        self.downloads_treeview.heading("select", text="Select", anchor=tk.CENTER)
        self.downloads_treeview.column("#0", width=180, anchor=tk.W)
        self.downloads_treeview.column("start_time", width=150, anchor=tk.W)
        self.downloads_treeview.column("end_time", width=150, anchor=tk.W)
        self.downloads_treeview.column("select", width=60, anchor=tk.CENTER)
        self.downloads_treeview.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        downloads_scrollbar.config(command=self.downloads_treeview.yview)
        
        # Bind click on select column to toggle checkbox
        self.downloads_treeview.bind('<Button-1>', self._on_downloads_click)
        
        # Buttons frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.grid(row=1, column=0, columnspan=2, pady=5)
        
        # B2 buttons
        b2_buttons_frame = ttk.Frame(buttons_frame)
        b2_buttons_frame.pack(side=tk.LEFT, padx=5)
        ttk.Button(b2_buttons_frame, text="Refresh B2 List", command=self.refresh_file_list).pack(side=tk.LEFT, padx=2)
        ttk.Button(b2_buttons_frame, text="Select All B2", command=self.select_all_b2).pack(side=tk.LEFT, padx=2)
        ttk.Button(b2_buttons_frame, text="Download Selected", command=self.download_selected).pack(side=tk.LEFT, padx=2)
        ttk.Button(b2_buttons_frame, text="Remove from B2", command=self.remove_from_b2).pack(side=tk.LEFT, padx=2)
        
        # Downloads buttons
        downloads_buttons_frame = ttk.Frame(buttons_frame)
        downloads_buttons_frame.pack(side=tk.LEFT, padx=5)
        ttk.Button(downloads_buttons_frame, text="Refresh Downloads", command=self.refresh_downloads_list).pack(side=tk.LEFT, padx=2)
        ttk.Button(downloads_buttons_frame, text="Select All Downloads", command=self.select_all_downloads).pack(side=tk.LEFT, padx=2)
        ttk.Button(downloads_buttons_frame, text="Load Session", command=self.load_session).pack(side=tk.LEFT, padx=2)
        ttk.Button(downloads_buttons_frame, text="Remove Downloads", command=self.remove_downloads).pack(side=tk.LEFT, padx=2)
        
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
    
    def _on_b2_click(self, event):
        """Handle click on B2 treeview to toggle checkbox"""
        region = self.b2_treeview.identify_region(event.x, event.y)
        if region == "cell":
            column = self.b2_treeview.identify_column(event.x)
            # Column #1 = size, #2 = downloaded, #3 = select
            if column == "#3":  # Select column
                item = self.b2_treeview.identify_row(event.y)
                if item:
                    current_values = list(self.b2_treeview.item(item, 'values'))
                    if len(current_values) >= 3:
                        # Toggle checkbox
                        current_select = current_values[2] if len(current_values) > 2 else ""
                        new_select = "☑" if current_select != "☑" else "☐"
                        current_values[2] = new_select
                        self.b2_treeview.item(item, values=tuple(current_values))
    
    def _on_downloads_click(self, event):
        """Handle click on Downloads treeview to toggle checkbox"""
        region = self.downloads_treeview.identify_region(event.x, event.y)
        if region == "cell":
            column = self.downloads_treeview.identify_column(event.x)
            # Column #1 = start_time, #2 = end_time, #3 = select
            if column == "#3":  # Select column
                item = self.downloads_treeview.identify_row(event.y)
                if item:
                    current_values = list(self.downloads_treeview.item(item, 'values'))
                    if len(current_values) >= 3:
                        # Toggle checkbox
                        current_select = current_values[2] if len(current_values) > 2 else ""
                        new_select = "☑" if current_select != "☑" else "☐"
                        current_values[2] = new_select
                        self.downloads_treeview.item(item, values=tuple(current_values))
    
    def select_all_b2(self):
        """Select or deselect all items in B2 list"""
        items = self.b2_treeview.get_children()
        if not items:
            return
        
        # Check if all are selected
        all_selected = True
        for item in items:
            values = self.b2_treeview.item(item, 'values')
            if len(values) >= 3 and values[2] != "☑":
                all_selected = False
                break
        
        # Toggle all: if all selected, deselect all; otherwise select all
        new_value = "☐" if all_selected else "☑"
        
        for item in items:
            current_values = list(self.b2_treeview.item(item, 'values'))
            if len(current_values) >= 3:
                current_values[2] = new_value
                self.b2_treeview.item(item, values=tuple(current_values))
    
    def select_all_downloads(self):
        """Select or deselect all items in Downloads list"""
        items = self.downloads_treeview.get_children()
        if not items:
            return
        
        # Check if all are selected
        all_selected = True
        for item in items:
            values = self.downloads_treeview.item(item, 'values')
            if len(values) >= 3 and values[2] != "☑":
                all_selected = False
                break
        
        # Toggle all: if all selected, deselect all; otherwise select all
        new_value = "☐" if all_selected else "☑"
        
        for item in items:
            current_values = list(self.downloads_treeview.item(item, 'values'))
            if len(current_values) >= 3:
                current_values[2] = new_value
                self.downloads_treeview.item(item, values=tuple(current_values))
    
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
                
                self.b2_treeview.insert("", tk.END, text=session_name, values=(size_text, downloaded_status, "☐"))
            
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
            
            self.downloads_treeview.insert("", tk.END, text=folder.name, values=(start_time, end_time, "☐"))
        
        self.status_label.config(text=f"Found {len(session_folders)} downloaded session(s)")
    
    def download_selected(self):
        """Download the selected files from B2"""
        selected_items = []
        for item in self.b2_treeview.get_children():
            values = self.b2_treeview.item(item, 'values')
            if len(values) >= 3 and values[2] == "☑":
                selected_items.append(item)
        
        if not selected_items:
            messagebox.showwarning("No Selection", "Please select sessions from B2 list to download")
            return
        
        count = len(selected_items)
        
        # Show progress dialog
        progress_window, progress_bar, status_label, cancelled = self._show_progress_dialog("Downloading from B2", count)
        
        try:
            download_dir = Path(Config.DOWNLOAD_DIR)
            download_dir.mkdir(parents=True, exist_ok=True)
            
            downloader = B2Downloader()
            downloaded_count = 0
            failed_count = 0
            
            for idx, item_id in enumerate(selected_items, 1):
                # Check if cancelled
                if cancelled['value']:
                    status_label.config(text="Cancelled!")
                    progress_window.update()
                    break
                
                session_name = self.b2_treeview.item(item_id, 'text')
                file_name = f"{session_name}.zip"
                zip_path = download_dir / file_name
                
                # Skip if already downloaded
                extract_dir = download_dir / session_name
                if extract_dir.exists():
                    status_label.config(text=f"Skipping {file_name} (already exists)... ({idx}/{count})")
                    progress_bar['value'] = idx
                    progress_window.update()
                    downloaded_count += 1
                    continue
                
                # Update progress
                status_label.config(text=f"Downloading {file_name}... ({idx}/{count})")
                progress_bar['value'] = idx - 1
                progress_window.update()
                
                try:
                    if downloader.download_file(file_name, zip_path):
                        # Check if cancelled before extraction
                        if cancelled['value']:
                            # Clean up downloaded zip
                            if zip_path.exists():
                                zip_path.unlink()
                            break
                        
                        # Extract zip file
                        status_label.config(text=f"Extracting {file_name}... ({idx}/{count})")
                        progress_window.update()
                        
                        extract_dir = download_dir / session_name
                        
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
                        downloaded_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    print(f"Error downloading/extracting {file_name}: {e}")
                    failed_count += 1
                    # Clean up zip file if it exists
                    if zip_path.exists():
                        try:
                            zip_path.unlink()
                        except:
                            pass
            
            # Update final status
            if cancelled['value']:
                status_label.config(text="Cancelled!")
            else:
                progress_bar['value'] = count
                status_label.config(text="Completed!")
            progress_window.update()
            
            # Refresh both lists
            self.refresh_downloads_list()
            self.refresh_file_list()  # Update "Downloaded" status in B2 list
            
            # Close progress window after a brief delay
            progress_window.after(500, progress_window.destroy)
            
            if cancelled['value']:
                messagebox.showinfo("Cancelled", f"Download cancelled. {downloaded_count} session(s) downloaded before cancellation.")
            elif failed_count == 0:
                messagebox.showinfo("Success", f"Successfully downloaded and extracted {downloaded_count} session(s)")
            else:
                messagebox.showwarning("Partial Success", f"Downloaded {downloaded_count} session(s), {failed_count} failed")
        except Exception as e:
            progress_window.destroy()
            messagebox.showerror("Error", f"Error downloading files: {e}")
            import traceback
            traceback.print_exc()
    
    def _show_progress_dialog(self, title: str, total: int) -> tuple:
        """Show progress dialog and return (window, progress_bar, status_label, cancelled_flag)"""
        progress_window = tk.Toplevel(self.root)
        progress_window.title(title)
        progress_window.geometry("400x150")
        progress_window.transient(self.root)
        progress_window.grab_set()
        
        # Center the window
        progress_window.update_idletasks()
        x = (progress_window.winfo_screenwidth() // 2) - (400 // 2)
        y = (progress_window.winfo_screenheight() // 2) - (150 // 2)
        progress_window.geometry(f"400x150+{x}+{y}")
        
        status_label = ttk.Label(progress_window, text="Starting...")
        status_label.pack(pady=10)
        
        progress_bar = ttk.Progressbar(progress_window, length=350, mode='determinate', maximum=total)
        progress_bar.pack(pady=5)
        
        # Cancel flag (shared between dialog and operations)
        cancelled = {'value': False}
        
        def on_cancel():
            cancelled['value'] = True
            status_label.config(text="Cancelling...")
            cancel_button.config(state='disabled')
        
        cancel_button = ttk.Button(progress_window, text="Cancel", command=on_cancel)
        cancel_button.pack(pady=5)
        
        progress_window.update()
        
        return progress_window, progress_bar, status_label, cancelled
    
    def remove_from_b2(self):
        """Remove selected sessions from B2"""
        selected_items = []
        for item in self.b2_treeview.get_children():
            values = self.b2_treeview.item(item, 'values')
            if len(values) >= 3 and values[2] == "☑":
                selected_items.append(item)
        
        if not selected_items:
            messagebox.showwarning("No Selection", "Please select sessions to remove from B2")
            return
        
        # Confirm deletion
        count = len(selected_items)
        if not messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete {count} session(s) from B2? This cannot be undone."):
            return
        
        # Show progress dialog
        progress_window, progress_bar, status_label, cancelled = self._show_progress_dialog("Removing from B2", count)
        
        try:
            downloader = B2Downloader()
            deleted_count = 0
            failed_count = 0
            
            for idx, item_id in enumerate(selected_items, 1):
                # Check if cancelled
                if cancelled['value']:
                    status_label.config(text="Cancelled!")
                    progress_window.update()
                    break
                
                session_name = self.b2_treeview.item(item_id, 'text')
                file_name = f"{session_name}.zip"
                
                # Update progress
                status_label.config(text=f"Deleting {file_name}... ({idx}/{count})")
                progress_bar['value'] = idx - 1
                progress_window.update()
                
                try:
                    # Delete file from B2
                    file_version = downloader.b2_bucket.get_file_info_by_name(file_name)
                    downloader.b2_bucket.delete_file_version(file_version.id_, file_name)
                    deleted_count += 1
                except Exception as e:
                    print(f"Error deleting {file_name} from B2: {e}")
                    failed_count += 1
            
            # Update final status
            if cancelled['value']:
                status_label.config(text="Cancelled!")
            else:
                progress_bar['value'] = count
                status_label.config(text="Completed!")
            progress_window.update()
            
            # Refresh list
            self.refresh_file_list()
            
            # Close progress window after a brief delay
            progress_window.after(500, progress_window.destroy)
            
            if cancelled['value']:
                messagebox.showinfo("Cancelled", f"Deletion cancelled. {deleted_count} session(s) deleted before cancellation.")
            elif failed_count == 0:
                messagebox.showinfo("Success", f"Successfully deleted {deleted_count} session(s) from B2")
            else:
                messagebox.showwarning("Partial Success", f"Deleted {deleted_count} session(s), {failed_count} failed")
        except Exception as e:
            progress_window.destroy()
            messagebox.showerror("Error", f"Error removing sessions from B2: {e}")
    
    def remove_downloads(self):
        """Remove selected sessions from downloads"""
        selected_items = []
        for item in self.downloads_treeview.get_children():
            values = self.downloads_treeview.item(item, 'values')
            if len(values) >= 3 and values[2] == "☑":
                selected_items.append(item)
        
        if not selected_items:
            messagebox.showwarning("No Selection", "Please select sessions to remove from downloads")
            return
        
        # Confirm deletion
        count = len(selected_items)
        if not messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete {count} downloaded session(s)? This cannot be undone."):
            return
        
        # Show progress dialog
        progress_window, progress_bar, status_label, cancelled = self._show_progress_dialog("Removing Downloads", count)
        
        try:
            download_dir = Path(Config.DOWNLOAD_DIR)
            deleted_count = 0
            failed_count = 0
            
            for idx, item_id in enumerate(selected_items, 1):
                # Check if cancelled
                if cancelled['value']:
                    status_label.config(text="Cancelled!")
                    progress_window.update()
                    break
                
                session_name = self.downloads_treeview.item(item_id, 'text')
                session_folder = download_dir / session_name
                
                # Update progress
                status_label.config(text=f"Deleting {session_name}... ({idx}/{count})")
                progress_bar['value'] = idx - 1
                progress_window.update()
                
                try:
                    if session_folder.exists():
                        shutil.rmtree(session_folder)
                        deleted_count += 1
                except Exception as e:
                    print(f"Error deleting {session_name}: {e}")
                    failed_count += 1
            
            # Update final status
            if cancelled['value']:
                status_label.config(text="Cancelled!")
            else:
                progress_bar['value'] = count
                status_label.config(text="Completed!")
            progress_window.update()
            
            # Refresh list
            self.refresh_downloads_list()
            
            # Close progress window after a brief delay
            progress_window.after(500, progress_window.destroy)
            
            if cancelled['value']:
                messagebox.showinfo("Cancelled", f"Deletion cancelled. {deleted_count} session(s) deleted before cancellation.")
            elif failed_count == 0:
                messagebox.showinfo("Success", f"Successfully deleted {deleted_count} session(s)")
            else:
                messagebox.showwarning("Partial Success", f"Deleted {deleted_count} session(s), {failed_count} failed")
        except Exception as e:
            progress_window.destroy()
            messagebox.showerror("Error", f"Error removing sessions: {e}")
    
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
        
        # Load events.jsonl to get screenshot metadata and group by timestamp
        events_file = session_folder / "events.jsonl"
        screenshot_groups = {}  # timestamp -> list of monitor files
        
        if events_file.exists():
            try:
                with open(events_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        event = json.loads(line.strip())
                        if event.get('type') == 'screenshot' and 'data' in event:
                            screenshot_data = event['data']
                            timestamp = screenshot_data.get('timestamp')
                            if timestamp and 'monitors' in screenshot_data:
                                monitor_files = []
                                for monitor in screenshot_data['monitors']:
                                    filename = monitor.get('filename')
                                    if filename:
                                        file_path = screenshots_dir / filename
                                        if file_path.exists():
                                            monitor_files.append({
                                                'path': file_path,
                                                'filename': filename,
                                                'monitor_index': monitor.get('monitor_index', 0)
                                            })
                                if monitor_files:
                                    # Sort by monitor index
                                    monitor_files.sort(key=lambda x: x['monitor_index'])
                                    screenshot_groups[timestamp] = monitor_files
            except Exception as e:
                print(f"Warning: Could not parse events.jsonl: {e}")
        
        # If no events.jsonl, group screenshots by timestamp prefix
        if not screenshot_groups:
            # Group files by timestamp (everything before _monitor_)
            grouped_by_timestamp = {}
            for screenshot_file in sorted(screenshots_dir.glob("*.jpg")):
                # Extract timestamp from filename: timestamp_monitor_N.jpg
                parts = screenshot_file.stem.split('_monitor_')
                if len(parts) == 2:
                    timestamp_prefix = parts[0]
                    monitor_index = int(parts[1])
                    
                    if timestamp_prefix not in grouped_by_timestamp:
                        grouped_by_timestamp[timestamp_prefix] = []
                    
                    grouped_by_timestamp[timestamp_prefix].append({
                        'path': screenshot_file,
                        'filename': screenshot_file.name,
                        'monitor_index': monitor_index
                    })
            
            # Convert to timestamp format
            for timestamp_prefix, monitor_files in grouped_by_timestamp.items():
                # Try to reconstruct timestamp from prefix
                timestamp = timestamp_prefix.replace('-', ':').replace('-', '.', 1)
                monitor_files.sort(key=lambda x: x['monitor_index'])
                screenshot_groups[timestamp] = monitor_files
        
        # Convert to list of screenshot groups
        self.screenshots = []
        for timestamp in sorted(screenshot_groups.keys()):
            self.screenshots.append({
                'timestamp': timestamp,
                'monitors': screenshot_groups[timestamp]
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
        """Display screenshot(s) at given index - shows all monitors side by side"""
        if not self.screenshots or index < 0 or index >= len(self.screenshots):
            return
        
        screenshot_group = self.screenshots[index]
        monitors = screenshot_group.get('monitors', [])
        
        if not monitors:
            self.image_label.config(text="No screenshots found")
            return
        
        try:
            # Load all monitor images
            images = []
            for monitor_info in monitors:
                img = Image.open(monitor_info['path'])
                images.append(img)
            
            if len(images) == 1:
                # Single monitor - display as before
                img = images[0]
            else:
                # Multiple monitors - combine horizontally
                # Calculate total width and max height
                total_width = sum(img.width for img in images)
                max_height = max(img.height for img in images)
                
                # Create combined image
                combined_img = Image.new('RGB', (total_width, max_height), color='black')
                x_offset = 0
                for img in images:
                    # Center vertically if heights differ
                    y_offset = (max_height - img.height) // 2
                    combined_img.paste(img, (x_offset, y_offset))
                    x_offset += img.width
                
                img = combined_img
            
            # Resize to fit window (max 1200x700 for combined images)
            max_width, max_height = 1200, 700
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            
            photo = ImageTk.PhotoImage(img)
            self.image_label.config(image=photo, text="")
            self.image_label.image = photo  # Keep a reference
            
            self.current_index = index
            self.update_progress()
        except Exception as e:
            print(f"Error displaying screenshot: {e}")
            import traceback
            traceback.print_exc()
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

