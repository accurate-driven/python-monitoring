"""
Time Tracking Application
Captures screenshots, monitors keyboard/mouse events, and tracks running processes
"""

import time
import threading
import json
import platform
import zipfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import queue

from config import Config

try:
    import mss
    from pynput import keyboard, mouse
    import psutil
    from PIL import Image, ImageDraw
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Please install requirements: pip install -r requirements.txt")
    exit(1)

# Backblaze B2 imports (optional)
try:
    from b2sdk.v2 import InMemoryAccountInfo, B2Api
    from b2sdk.v2.exception import B2Error
    B2_AVAILABLE = True
except ImportError:
    B2_AVAILABLE = False
    print("Warning: b2sdk not installed. B2 upload functionality disabled.")
    print("Install with: pip install b2sdk")

# Platform-specific imports for lock screen detection
if platform.system() == "Windows":
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        pass
elif platform.system() == "Linux":
    try:
        import subprocess
    except ImportError:
        pass
elif platform.system() == "Darwin":  # macOS
    try:
        import subprocess
    except ImportError:
        pass


class TimeTracker:
    def __init__(self, screenshot_interval: Optional[float] = None, data_dir: Optional[str] = None,
                 screenshot_quality: Optional[int] = None, screenshot_scale: Optional[float] = None,
                 b2_key_id: Optional[str] = None, b2_key: Optional[str] = None,
                 b2_bucket_name: Optional[str] = None, upload_to_b2: Optional[bool] = None,
                 delete_after_upload: Optional[bool] = None):
        """
        Initialize the time tracker
        
        Args:
            screenshot_interval: Interval in seconds between screenshots (uses Config.SCREENSHOT_INTERVAL if None)
            data_dir: Directory to store tracking data (uses Config.DATA_DIR if None)
            screenshot_quality: JPEG quality 1-100 (uses Config.SCREENSHOT_QUALITY if None)
            screenshot_scale: Scale factor 0.1-1.0 (uses Config.SCREENSHOT_SCALE if None)
            b2_key_id: Backblaze B2 Application Key ID (uses Config.B2_KEY_ID if None)
            b2_key: Backblaze B2 Application Key (uses Config.B2_KEY if None)
            b2_bucket_name: Backblaze B2 Bucket Name (uses Config.B2_BUCKET_NAME if None)
            upload_to_b2: Enable automatic upload to B2 (uses Config.UPLOAD_TO_B2 if None)
            delete_after_upload: Delete local folder after successful upload (uses Config.DELETE_AFTER_UPLOAD if None)
        """
        # Use Config values if parameters are None
        self.screenshot_interval = screenshot_interval if screenshot_interval is not None else Config.SCREENSHOT_INTERVAL
        self.screenshot_quality = max(1, min(100, screenshot_quality if screenshot_quality is not None else Config.SCREENSHOT_QUALITY))
        self.screenshot_scale = max(0.1, min(1.0, screenshot_scale if screenshot_scale is not None else Config.SCREENSHOT_SCALE))
        self.data_dir = Path(data_dir if data_dir is not None else Config.DATA_DIR)
        self.data_dir.mkdir(exist_ok=True)
        
        # Folder rotation settings from Config
        self.folder_rotation_interval = Config.FOLDER_ROTATION_INTERVAL
        self.folder_max_size_mb = Config.FOLDER_MAX_SIZE_MB
        self.folder_max_size_bytes = Config.get_folder_max_size_bytes()
        
        # Current session folder tracking
        self.current_session_dir: Optional[Path] = None
        self.session_start_time: Optional[datetime] = None
        self._session_lock = threading.RLock()  # Reentrant lock for thread-safe folder rotation
        self.previous_session_dir: Optional[Path] = None  # Initialize before calling _create_new_session_folder
        
        # Initialize first session folder
        self._create_new_session_folder()
        
        # State
        self.running = False
        self.screenshot_thread: Optional[threading.Thread] = None
        self.keyboard_listener: Optional[keyboard.Listener] = None
        self.mouse_listener: Optional[mouse.Listener] = None
        
        # Event queues for thread-safe logging
        self.event_queue = queue.Queue()
        self.process_queue = queue.Queue()
        
        # Statistics
        self.stats = {
            "screenshots_taken": 0,
            "key_events": 0,
            "mouse_clicks": 0,
            "start_time": None,
        }
        
        # Lock screen state
        self.is_locked = False
        self.last_lock_check = None
        
        # Process tracking for change detection
        self.previous_processes: Dict[int, Dict] = {}  # pid -> process info
        
        # Backblaze B2 upload configuration (use Config if None)
        self.b2_key_id = b2_key_id if b2_key_id is not None else Config.B2_KEY_ID
        self.b2_key = b2_key if b2_key is not None else Config.B2_KEY
        self.b2_bucket_name = b2_bucket_name if b2_bucket_name is not None else Config.B2_BUCKET_NAME
        upload_to_b2_value = upload_to_b2 if upload_to_b2 is not None else Config.UPLOAD_TO_B2
        self.upload_to_b2 = upload_to_b2_value and B2_AVAILABLE
        self.delete_after_upload = delete_after_upload if delete_after_upload is not None else Config.DELETE_AFTER_UPLOAD
        self.b2_api: Optional[B2Api] = None
        self.b2_bucket = None
        
        # Track completed folders for upload
        self.completed_folders_queue = queue.Queue()
        
        # Initialize B2 if configured
        if self.upload_to_b2 and self.b2_key_id and self.b2_key and self.b2_bucket_name:
            try:
                self._init_b2()
                print("B2 upload enabled and configured")
            except Exception as e:
                print(f"Warning: Failed to initialize B2: {e}")
                self.upload_to_b2 = False
        elif self.upload_to_b2:
            print("Warning: B2 credentials not provided. Upload disabled.")
            self.upload_to_b2 = False
        
        # Queue existing session folders for upload on startup
        if self.upload_to_b2:
            self._queue_existing_folders_for_upload()
    
    def _get_folder_size(self, folder_path: Path) -> int:
        """Calculate total size of folder in bytes"""
        total_size = 0
        try:
            for file_path in folder_path.rglob('*'):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
        except Exception:
            pass
        return total_size
    
    def _queue_existing_folders_for_upload(self):
        """Queue all existing session folders for upload on startup"""
        if not self.data_dir.exists():
            return
        
        # Find all session folders
        session_folders = []
        for item in self.data_dir.iterdir():
            if item.is_dir() and item.name.startswith("session_"):
                # Skip the current session folder
                if item != self.current_session_dir:
                    session_folders.append(item)
        
        if session_folders:
            print(f"Found {len(session_folders)} existing session folder(s) to upload")
            for folder in sorted(session_folders):
                if folder.exists():
                    print(f"  Queueing: {folder.name}")
                    self.completed_folders_queue.put(folder)
        else:
            print("No existing session folders found to upload")
    
    def _init_b2(self):
        """Initialize Backblaze B2 API"""
        if not B2_AVAILABLE:
            raise RuntimeError("b2sdk not installed")
        
        info = InMemoryAccountInfo()
        self.b2_api = B2Api(info)
        self.b2_api.authorize_account("production", self.b2_key_id, self.b2_key)
        self.b2_bucket = self.b2_api.get_bucket_by_name(self.b2_bucket_name)
        print(f"Connected to B2 bucket: {self.b2_bucket_name}")
    
    def _compress_folder_to_zip(self, folder_path: Path) -> Optional[Path]:
        """Compress a folder to a zip file"""
        try:
            zip_path = folder_path.parent / f"{folder_path.name}.zip"
            print(f"Compressing {folder_path.name} to {zip_path.name}...")
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add all files in the folder to zip
                for file_path in folder_path.rglob('*'):
                    if file_path.is_file():
                        # Get relative path for zip archive (relative to folder_path)
                        arcname = file_path.relative_to(folder_path)
                        # Preserve folder structure in zip: session_name/relative_path
                        arcname = f"{folder_path.name}/{arcname}"
                        zipf.write(file_path, arcname)
            
            zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
            print(f"✓ Compressed {folder_path.name} to {zip_path.name} ({zip_size_mb:.2f} MB)")
            return zip_path
            
        except Exception as e:
            print(f"✗ Error compressing folder {folder_path.name}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _upload_folder_to_b2(self, folder_path: Path) -> bool:
        """Compress and upload a session folder to Backblaze B2"""
        if not self.b2_api or not self.b2_bucket:
            print("Error: B2 API or bucket not initialized")
            return False
        
        try:
            folder_name = folder_path.name
            
            # Step 1: Compress folder to zip
            zip_path = self._compress_folder_to_zip(folder_path)
            if not zip_path or not zip_path.exists():
                print(f"✗ Failed to create zip for {folder_name}")
                return False
            
            # Step 2: Upload zip file to B2
            try:
                zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
                print(f"Uploading {zip_path.name} to B2 ({zip_size_mb:.2f} MB)...")
                
                file_info = {
                    'uploaded_at': datetime.now().isoformat(),
                    'original_folder': folder_name,
                    'compressed': 'true'
                }
                
                remote_path = f"{folder_name}.zip"
                self.b2_bucket.upload_local_file(
                    local_file=str(zip_path),
                    file_name=remote_path,
                    file_info=file_info
                )
                
                print(f"✓ Successfully uploaded {zip_path.name} to B2")
                
                # Step 3: Delete folder and zip after successful upload
                try:
                    shutil.rmtree(folder_path)
                    print(f"✓ Deleted folder: {folder_name}")
                except Exception as e:
                    print(f"⚠ Failed to delete folder {folder_name}: {e}")
                
                try:
                    zip_path.unlink()
                    print(f"✓ Deleted zip: {zip_path.name}")
                except Exception as e:
                    print(f"⚠ Failed to delete zip {zip_path.name}: {e}")
                
                return True
                
            except Exception as e:
                print(f"✗ Error uploading zip {zip_path.name} to B2: {e}")
                import traceback
                traceback.print_exc()
                # Clean up zip file if upload failed
                try:
                    if zip_path.exists():
                        zip_path.unlink()
                        print(f"Cleaned up zip file after failed upload")
                except:
                    pass
                return False
                
        except Exception as e:
            print(f"✗ Error processing folder {folder_path.name}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _create_new_session_folder(self):
        """Create a new session folder with timestamp"""
        # If we have a previous session folder and upload is enabled, queue it for upload
        if self.previous_session_dir and self.previous_session_dir.exists() and self.upload_to_b2:
            print(f"Queueing folder for B2 upload: {self.previous_session_dir.name}")
            self.completed_folders_queue.put(self.previous_session_dir)
        
        # Ensure parent data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_folder = self.data_dir / f"session_{timestamp}"
        
        # Create folder and subdirectories with parents=True to ensure all exist
        session_folder.mkdir(parents=True, exist_ok=True)
        (session_folder / "screenshots").mkdir(parents=True, exist_ok=True)
        
        # Verify folder was actually created
        if not session_folder.exists():
            raise RuntimeError(f"Failed to create session folder: {session_folder}")
        
        # Update previous session before setting new current
        self.previous_session_dir = self.current_session_dir
        self.current_session_dir = session_folder
        self.session_start_time = datetime.now()
        
        print(f"Created new session folder: {session_folder.name}")
    
    def _check_and_rotate_folder(self):
        """Check if folder rotation is needed and create new folder if necessary"""
        with self._session_lock:
            # If folder doesn't exist, create a new one
            if not self.current_session_dir or not self.current_session_dir.exists():
                self._create_new_session_folder()
                return
            
            if not self.session_start_time:
                self.session_start_time = datetime.now()
                return
            
            # Check time-based rotation
            elapsed_seconds = (datetime.now() - self.session_start_time).total_seconds()
            if elapsed_seconds >= self.folder_rotation_interval:
                minutes = self.folder_rotation_interval / 60
                print(f"Rotating folder: {elapsed_seconds:.0f} seconds elapsed ({minutes:.0f} min limit)")
                self._create_new_session_folder()
                return
            
            # Check size-based rotation
            try:
                folder_size = self._get_folder_size(self.current_session_dir)
                if folder_size >= self.folder_max_size_bytes:
                    size_mb = folder_size / (1024 * 1024)
                    print(f"Rotating folder: {size_mb:.2f} MB reached ({self.folder_max_size_mb} MB limit)")
                    self._create_new_session_folder()
                    return
            except Exception:
                # If we can't check size (folder might be deleted), create new folder
                self._create_new_session_folder()
                return
    
    def _ensure_session_folder_exists(self):
        """Ensure current session folder and subdirectories exist (must be called within lock)"""
        if not self.current_session_dir or not self.current_session_dir.exists():
            self._create_new_session_folder()
        else:
            # Ensure screenshots subdirectory exists
            screenshots_dir = self.current_session_dir / "screenshots"
            screenshots_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_screenshots_dir(self) -> Path:
        """Get current screenshots directory, rotating if needed"""
        with self._session_lock:
            self._check_and_rotate_folder()
            self._ensure_session_folder_exists()
            screenshots_dir = self.current_session_dir / "screenshots"
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            return screenshots_dir
    
    def _get_events_file(self) -> Path:
        """Get current events file path, rotating if needed"""
        with self._session_lock:
            self._check_and_rotate_folder()
            self._ensure_session_folder_exists()
            return self.current_session_dir / "events.jsonl"
    
    def _get_processes_file(self) -> Path:
        """Get current processes file path, rotating if needed"""
        with self._session_lock:
            self._check_and_rotate_folder()
            self._ensure_session_folder_exists()
            return self.current_session_dir / "processes.jsonl"
    
    def draw_cursor(self, img: Image.Image, cursor_x: int, cursor_y: int, monitor_left: int, monitor_top: int):
        """Draw mouse cursor on the screenshot"""
        try:
            # Calculate cursor position relative to this monitor
            rel_x = cursor_x - monitor_left
            rel_y = cursor_y - monitor_top
            
            # Check if cursor is within this monitor's bounds
            if 0 <= rel_x < img.width and 0 <= rel_y < img.height:
                draw = ImageDraw.Draw(img)
                
                # Draw a simple cursor (arrow shape)
                # Main line (vertical)
                draw.line([(rel_x, rel_y), (rel_x, rel_y + 15)], fill=(0, 0, 0), width=2)
                draw.line([(rel_x, rel_y), (rel_x, rel_y + 15)], fill=(255, 255, 255), width=1)
                
                # Arrow head (diagonal lines)
                draw.line([(rel_x, rel_y), (rel_x + 5, rel_y + 5)], fill=(0, 0, 0), width=2)
                draw.line([(rel_x, rel_y), (rel_x + 5, rel_y + 5)], fill=(255, 255, 255), width=1)
                draw.line([(rel_x, rel_y), (rel_x - 5, rel_y + 5)], fill=(0, 0, 0), width=2)
                draw.line([(rel_x, rel_y), (rel_x - 5, rel_y + 5)], fill=(255, 255, 255), width=1)
                
                # Cursor hotspot circle
                draw.ellipse([rel_x - 2, rel_y - 2, rel_x + 2, rel_y + 2], 
                           fill=(255, 255, 255), outline=(0, 0, 0), width=1)
        except Exception as e:
            # Silently fail if cursor drawing fails
            pass
    
    def capture_screenshot(self, sct) -> Dict:
        """Capture screenshot of all monitors with mouse cursor"""
        timestamp = datetime.now().isoformat()
        screenshot_data = {
            "timestamp": timestamp,
            "monitors": [],
            "screen_locked": self.is_locked
        }
        
        try:
            # Get current cursor position (may fail if locked)
            try:
                cursor_x, cursor_y = mouse.Controller().position
            except:
                cursor_x, cursor_y = 0, 0
            
            # Capture all monitors
            for i, monitor in enumerate(sct.monitors):
                if i == 0:
                    # Skip the "All monitors" entry (index 0)
                    continue
                
                # Capture screenshot
                screenshot = sct.grab(monitor)
                
                # Convert to PIL Image
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                
                # Calculate cursor position relative to monitor
                cursor_rel_x = cursor_x - monitor["left"]
                cursor_rel_y = cursor_y - monitor["top"]
                
                # Scale down image to reduce file size
                if self.screenshot_scale < 1.0:
                    new_width = int(img.width * self.screenshot_scale)
                    new_height = int(img.height * self.screenshot_scale)
                    # Scale cursor position proportionally
                    cursor_rel_x = int(cursor_rel_x * self.screenshot_scale)
                    cursor_rel_y = int(cursor_rel_y * self.screenshot_scale)
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Draw cursor on this monitor if it's within bounds
                self.draw_cursor(img, cursor_rel_x, cursor_rel_y, 0, 0)
                
                # Save screenshot as JPEG with compression (much smaller than PNG)
                filename = f"{timestamp.replace(':', '-').replace('.', '-')}_monitor_{i}.jpg"
                screenshots_dir = self._get_screenshots_dir()
                filepath = screenshots_dir / filename
                # Ensure RGB mode for JPEG
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img.save(filepath, format="JPEG", quality=self.screenshot_quality, optimize=True)
                
                # Check if cursor is on this monitor
                cursor_on_monitor = (monitor["left"] <= cursor_x < monitor["left"] + screenshot.width and
                                    monitor["top"] <= cursor_y < monitor["top"] + screenshot.height)
                
                screenshot_data["monitors"].append({
                    "monitor_index": i,
                    "filename": filename,
                    "width": img.width,  # Actual saved image width (may be scaled)
                    "height": img.height,  # Actual saved image height (may be scaled)
                    "original_width": screenshot.width,
                    "original_height": screenshot.height,
                    "scale": self.screenshot_scale,
                    "quality": self.screenshot_quality,
                    "left": monitor["left"],
                    "top": monitor["top"],
                    "cursor_x": cursor_x if cursor_on_monitor else None,
                    "cursor_y": cursor_y if cursor_on_monitor else None
                })
            
            self.stats["screenshots_taken"] += 1
            return screenshot_data
            
        except Exception as e:
            # If screenshot fails, it might indicate screen is locked
            error_msg = str(e).lower()
            if "access" in error_msg or "denied" in error_msg or "locked" in error_msg:
                # Log potential lock event
                if not self.is_locked:
                    self.log_event({
                        "type": "screen_locked",
                        "timestamp": datetime.now().isoformat(),
                        "detected_by": "screenshot_failure"
                    })
                    self.is_locked = True
            print(f"Error capturing screenshot: {e}")
            return None
    
    def screenshot_loop(self):
        """Main loop for capturing screenshots at intervals"""
        # Create MSS instance in this thread (required for Windows)
        sct = mss.mss()
        
        while self.running:
            screenshot_data = self.capture_screenshot(sct)
            if screenshot_data:
                # Log screenshot event
                self.log_event({
                    "type": "screenshot",
                    "data": screenshot_data
                })
            
            time.sleep(self.screenshot_interval)
    
    def on_key_press(self, key):
        """Handle key press events (not logged, only key releases are logged)"""
        # Key press events are not logged to reduce noise
        # Only key release events are logged
        pass
    
    def on_key_release(self, key):
        """Handle key release events"""
        try:
            key_name = None
            if hasattr(key, 'char') and key.char:
                key_name = key.char
            elif hasattr(key, 'name'):
                key_name = key.name
            else:
                key_name = str(key)
            
            event = {
                "type": "key_release",
                "timestamp": datetime.now().isoformat(),
                "key": key_name,
                "key_code": str(key)
            }
            
            self.log_event(event)
            self.stats["key_events"] += 1
            
        except Exception as e:
            print(f"Error handling key release: {e}")
    
    def on_mouse_click(self, x, y, button, pressed):
        """Handle mouse click events"""
        try:
            event = {
                "type": "mouse_click" if pressed else "mouse_release",
                "timestamp": datetime.now().isoformat(),
                "x": x,
                "y": y,
                "button": str(button),
                "pressed": pressed
            }
            
            self.log_event(event)
            if pressed:
                self.stats["mouse_clicks"] += 1
                
        except Exception as e:
            print(f"Error handling mouse click: {e}")
    
    def check_lock_screen(self) -> bool:
        """Check if screen is locked (platform-specific)"""
        system = platform.system()
        
        try:
            if system == "Windows":
                return self._check_lock_windows()
            elif system == "Linux":
                return self._check_lock_linux()
            elif system == "Darwin":  # macOS
                return self._check_lock_macos()
            else:
                # Fallback: try to detect by screenshot failure or other means
                return False
        except Exception as e:
            # Silently fail and assume unlocked
            return False
    
    def _check_lock_windows(self) -> bool:
        """Check if Windows screen is locked"""
        try:
            # Method 1: Check if logonui.exe is running (Windows lock screen process)
            # This is the most reliable indicator
            try:
                for proc in psutil.process_iter(['name']):
                    try:
                        proc_name = proc.info.get('name', '').lower()
                        if proc_name == 'logonui.exe':
                            return True
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            except Exception:
                pass
            
            # Method 2: Check screensaver state (often indicates lock)
            try:
                user32 = ctypes.windll.user32
                SPI_GETSCREENSAVERRUNNING = 0x0072
                result = ctypes.c_bool()
                if user32.SystemParametersInfoW(SPI_GETSCREENSAVERRUNNING, 0, ctypes.byref(result), 0):
                    if result.value:
                        return True
            except Exception:
                pass
            
            return False
        except Exception:
            return False
    
    def _check_lock_linux(self) -> bool:
        """Check if Linux screen is locked"""
        try:
            # Try different methods based on desktop environment
            # For GNOME
            try:
                result = subprocess.run(
                    ["gsettings", "get", "org.gnome.desktop.screensaver", "lock-enabled"],
                    capture_output=True,
                    text=True,
                    timeout=1
                )
                if result.returncode == 0:
                    # Check if lock screen process is running
                    result = subprocess.run(
                        ["pgrep", "-f", "gnome-screensaver|xscreensaver|light-locker"],
                        capture_output=True,
                        timeout=1
                    )
                    return result.returncode == 0
            except:
                pass
            
            # For X11: check if screensaver is active
            try:
                result = subprocess.run(
                    ["xset", "q"],
                    capture_output=True,
                    timeout=1
                )
                # This is a basic check - more sophisticated detection needed
            except:
                pass
            
            return False
        except Exception:
            return False
    
    def _check_lock_macos(self) -> bool:
        """Check if macOS screen is locked"""
        try:
            # Use pmset or IOKit to check screen lock state
            result = subprocess.run(
                ["pmset", "-g", "assertions"],
                capture_output=True,
                text=True,
                timeout=1
            )
            if result.returncode == 0:
                # Check for display sleep or user idle assertions
                output = result.stdout.lower()
                if "preventuseridledisplaysleep" in output or "displaysleep" in output:
                    # This is a basic check
                    pass
            
            # Alternative: Check if screensaver is active
            result = subprocess.run(
                ["pgrep", "-x", "ScreenSaverEngine"],
                capture_output=True,
                timeout=1
            )
            # If screensaver is running, screen might be locked
            # But this is not definitive
            
            return False
        except Exception:
            return False
    
    def lock_screen_monitor_loop(self):
        """Monitor lock screen state changes"""
        while self.running:
            try:
                current_lock_state = self.check_lock_screen()
                
                # Detect state change
                if current_lock_state != self.is_locked:
                    if current_lock_state:
                        # Screen just locked
                        self.log_event({
                            "type": "screen_locked",
                            "timestamp": datetime.now().isoformat()
                        })
                        print("Screen locked detected")
                    else:
                        # Screen just unlocked
                        self.log_event({
                            "type": "screen_unlocked",
                            "timestamp": datetime.now().isoformat()
                        })
                        print("Screen unlocked detected")
                    
                    self.is_locked = current_lock_state
                    self.last_lock_check = datetime.now().isoformat()
                
                # Check every second
                time.sleep(1)
            except Exception as e:
                # Continue monitoring even if check fails
                time.sleep(1)
    
    def get_running_processes(self) -> List[Dict]:
        """Get list of running processes/services"""
        processes = []
        try:
            for proc in psutil.process_iter(['pid', 'name', 'exe', 'username', 'status', 'create_time']):
                try:
                    proc_info = proc.info
                    proc_info['timestamp'] = datetime.now().isoformat()
                    processes.append(proc_info)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        except Exception as e:
            print(f"Error getting processes: {e}")
        
        return processes
    
    def detect_process_changes(self, current_processes: List[Dict]) -> Dict[str, List[Dict]]:
        """Detect process starts and stops by comparing with previous snapshot"""
        changes = {
            "started": [],
            "stopped": []
        }
        
        # Create current PID set
        current_pids = {proc.get('pid') for proc in current_processes if proc.get('pid')}
        
        # Find stopped processes (in previous but not in current)
        for pid, proc_info in self.previous_processes.items():
            if pid not in current_pids:
                changes["stopped"].append({
                    "pid": pid,
                    "name": proc_info.get('name', 'unknown'),
                    "exe": proc_info.get('exe', 'unknown'),
                    "timestamp": datetime.now().isoformat(),
                    "stopped_at": datetime.now().isoformat()
                })
        
        # Find started processes (in current but not in previous)
        for proc in current_processes:
            pid = proc.get('pid')
            if pid and pid not in self.previous_processes:
                changes["started"].append({
                    "pid": pid,
                    "name": proc.get('name', 'unknown'),
                    "exe": proc.get('exe', 'unknown'),
                    "username": proc.get('username', 'unknown'),
                    "timestamp": datetime.now().isoformat(),
                    "started_at": datetime.now().isoformat()
                })
        
        return changes
    
    def process_monitor_loop(self):
        """Monitor running processes periodically and detect changes"""
        while self.running:
            processes = self.get_running_processes()
            if processes:
                # Detect process changes
                changes = self.detect_process_changes(processes)
                
                # Log process changes (starts/stops)
                if changes["started"]:
                    for proc_start in changes["started"]:
                        self.log_event({
                            "type": "process_started",
                            "timestamp": proc_start["started_at"],
                            "pid": proc_start["pid"],
                            "name": proc_start["name"],
                            "exe": proc_start.get("exe", ""),
                            "username": proc_start.get("username", "")
                        })
                
                if changes["stopped"]:
                    for proc_stop in changes["stopped"]:
                        self.log_event({
                            "type": "process_stopped",
                            "timestamp": proc_stop["stopped_at"],
                            "pid": proc_stop["pid"],
                            "name": proc_stop["name"],
                            "exe": proc_stop.get("exe", "")
                        })
                
                # Log full process snapshot
                self.log_processes(processes)
                
                # Update previous processes snapshot
                self.previous_processes = {
                    proc.get('pid'): proc 
                    for proc in processes 
                    if proc.get('pid')
                }
            
            # Check processes every 5 minutes (300 seconds)
            time.sleep(300)
    
    def log_event(self, event: Dict):
        """Log event to file (thread-safe)"""
        self.event_queue.put(event)
    
    def log_processes(self, processes: List[Dict]):
        """Log processes to file (thread-safe)"""
        self.process_queue.put(processes)
    
    def event_writer(self):
        """Background thread to write events to file"""
        while self.running or not self.event_queue.empty():
            try:
                event = self.event_queue.get(timeout=1)
                events_file = self._get_events_file()
                with open(events_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(event) + '\n')
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error writing event: {e}")
    
    def process_writer(self):
        """Background thread to write processes to file (one process per line for readability)"""
        while self.running or not self.process_queue.empty():
            try:
                processes = self.process_queue.get(timeout=1)
                processes_file = self._get_processes_file()
                with open(processes_file, 'a', encoding='utf-8') as f:
                    # Write each process on a separate line for better readability
                    for process in processes:
                        f.write(json.dumps(process, ensure_ascii=False) + '\n')
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error writing processes: {e}")
    
    def b2_upload_worker(self):
        """Background thread to upload completed folders to B2"""
        print("B2 upload worker started")
        while self.running or not self.completed_folders_queue.empty():
            try:
                folder_path = self.completed_folders_queue.get(timeout=5)
                print(f"B2 upload worker: Processing folder {folder_path.name}")
                
                if not folder_path.exists():
                    print(f"Warning: Folder {folder_path.name} no longer exists, skipping upload")
                    continue
                
                # Upload folder to B2 (compresses, uploads, and deletes automatically)
                print(f"Starting upload of {folder_path.name} to B2...")
                success = self._upload_folder_to_b2(folder_path)
                
                # Note: Folder and zip are automatically deleted after successful upload
                # No need for delete_after_upload check here
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in B2 upload worker: {e}")
    
    def start(self):
        """Start tracking"""
        if self.running:
            print("Tracker is already running")
            return
        
        print("Starting time tracker...")
        self.running = True
        self.stats["start_time"] = datetime.now().isoformat()
        
        # Start screenshot capture thread
        self.screenshot_thread = threading.Thread(target=self.screenshot_loop, daemon=True)
        self.screenshot_thread.start()
        
        # Start process monitoring thread
        process_thread = threading.Thread(target=self.process_monitor_loop, daemon=True)
        process_thread.start()
        
        # Start lock screen monitoring thread
        lock_monitor_thread = threading.Thread(target=self.lock_screen_monitor_loop, daemon=True)
        lock_monitor_thread.start()
        
        # Start event writer threads
        event_writer_thread = threading.Thread(target=self.event_writer, daemon=True)
        event_writer_thread.start()
        
        process_writer_thread = threading.Thread(target=self.process_writer, daemon=True)
        process_writer_thread.start()
        
        # Start B2 upload thread if enabled
        if self.upload_to_b2:
            b2_upload_thread = threading.Thread(target=self.b2_upload_worker, daemon=True)
            b2_upload_thread.start()
        
        # Start keyboard listener
        self.keyboard_listener = keyboard.Listener(
            on_press=self.on_key_press,
            on_release=self.on_key_release
        )
        self.keyboard_listener.start()
        
        # Start mouse listener
        self.mouse_listener = mouse.Listener(on_click=self.on_mouse_click)
        self.mouse_listener.start()
        
        print("Time tracker started!")
        print(f"Data will be saved to: {self.data_dir.absolute()}")
        print(f"Current session folder: {self.current_session_dir.name if self.current_session_dir else 'N/A'}")
        minutes = self.folder_rotation_interval / 60
        print(f"Folders will rotate every {minutes:.0f} minutes or when reaching {self.folder_max_size_mb} MB")
        print("Press Ctrl+C to stop")
    
    def stop(self):
        """Stop tracking"""
        if not self.running:
            return
        
        print("\nStopping time tracker...")
        self.running = False
        
        # Queue current folder for upload if enabled
        if self.upload_to_b2 and self.current_session_dir and self.current_session_dir.exists():
            print(f"Queueing current folder for upload: {self.current_session_dir.name}")
            self.completed_folders_queue.put(self.current_session_dir)
        
        # Stop listeners
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        if self.mouse_listener:
            self.mouse_listener.stop()
        
        # Wait for threads to finish
        if self.screenshot_thread:
            self.screenshot_thread.join(timeout=5)
        
        # Wait for uploads to complete (with timeout)
        if self.upload_to_b2 and not self.completed_folders_queue.empty():
            print("Waiting for B2 uploads to complete...")
            import time
            timeout = 60  # Wait up to 60 seconds
            start_time = time.time()
            while not self.completed_folders_queue.empty() and (time.time() - start_time) < timeout:
                time.sleep(1)
            if not self.completed_folders_queue.empty():
                print(f"Warning: {self.completed_folders_queue.qsize()} folders still queued for upload")
        
        # Print statistics
        print("\n=== Tracking Statistics ===")
        print(f"Start time: {self.stats['start_time']}")
        print(f"Screenshots taken: {self.stats['screenshots_taken']}")
        print(f"Key events: {self.stats['key_events']}")
        print(f"Mouse clicks: {self.stats['mouse_clicks']}")
        print(f"Data saved to: {self.data_dir.absolute()}")
        print("Tracker stopped.")
    
    def get_stats(self) -> Dict:
        """Get current tracking statistics"""
        return self.stats.copy()


def main():
    """Main entry point"""
    # Create tracker with all settings from Config class (loaded from .env)
    tracker = TimeTracker()
    
    try:
        tracker.start()
        
        # Keep main thread alive
        while tracker.running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        pass
    finally:
        tracker.stop()


if __name__ == "__main__":
    main()

