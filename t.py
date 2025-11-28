"""
Time Tracking Application
Captures screenshots, monitors keyboard/mouse events, and tracks running processes
"""

import time
import threading
import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import queue

try:
    import mss
    from pynput import keyboard, mouse
    import psutil
    from PIL import Image, ImageDraw
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Please install requirements: pip install -r requirements.txt")
    exit(1)

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
    def __init__(self, screenshot_interval: float = 2.0, data_dir: str = "t_data",
                 screenshot_quality: int = 50, screenshot_scale: float = 1):
        """
        Initialize the time tracker
        
        Args:
            screenshot_interval: Interval in seconds between screenshots (default: 2.0)
            data_dir: Directory to store tracking data
            screenshot_quality: JPEG quality 1-100, lower = smaller files (default: 50)
            screenshot_scale: Scale factor 0.1-1.0, lower = smaller files (default: 1 = 100% size)
        """
        self.screenshot_interval = screenshot_interval
        self.screenshot_quality = max(1, min(100, screenshot_quality))
        self.screenshot_scale = max(0.1, min(1.0, screenshot_scale))
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        
        # Screenshot storage
        self.screenshots_dir = self.data_dir / "screenshots"
        self.screenshots_dir.mkdir(exist_ok=True)
        
        # Event storage
        self.events_file = self.data_dir / "events.jsonl"
        self.processes_file = self.data_dir / "processes.jsonl"
        
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
                filepath = self.screenshots_dir / filename
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
                with open(self.events_file, 'a', encoding='utf-8') as f:
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
                with open(self.processes_file, 'a', encoding='utf-8') as f:
                    # Write each process on a separate line for better readability
                    for process in processes:
                        f.write(json.dumps(process, ensure_ascii=False) + '\n')
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error writing processes: {e}")
    
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
        print("Press Ctrl+C to stop")
    
    def stop(self):
        """Stop tracking"""
        if not self.running:
            return
        
        print("\nStopping time tracker...")
        self.running = False
        
        # Stop listeners
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        if self.mouse_listener:
            self.mouse_listener.stop()
        
        # Wait for threads to finish
        if self.screenshot_thread:
            self.screenshot_thread.join(timeout=5)
        
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
    # Configure screenshot quality and scale to reduce file size
    # Lower quality (30-60) = smaller files, acceptable quality
    # Lower scale (0.5-1) = smaller files, lower resolution
    tracker = TimeTracker(
        screenshot_interval=2.0,
        screenshot_quality=50,  # 50% quality (good balance of size/quality)
        screenshot_scale=1      # 70% size (reduces file size significantly)
    )
    
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

