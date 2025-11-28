"""
Time Tracking Application
Captures screenshots, monitors keyboard/mouse events, and tracks running processes
"""

import time
import threading
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import queue

try:
    import mss
    from pynput import keyboard, mouse
    import psutil
    from PIL import Image
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Please install requirements: pip install -r requirements.txt")
    exit(1)


class TimeTracker:
    def __init__(self, screenshot_interval: float = 2.0, data_dir: str = "tracking_data"):
        """
        Initialize the time tracker
        
        Args:
            screenshot_interval: Interval in seconds between screenshots (default: 2.0)
            data_dir: Directory to store tracking data
        """
        self.screenshot_interval = screenshot_interval
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
    
    def capture_screenshot(self, sct) -> Dict:
        """Capture screenshot of all monitors"""
        timestamp = datetime.now().isoformat()
        screenshot_data = {
            "timestamp": timestamp,
            "monitors": []
        }
        
        try:
            # Capture all monitors
            for i, monitor in enumerate(sct.monitors):
                if i == 0:
                    # Skip the "All monitors" entry (index 0)
                    continue
                
                # Capture screenshot
                screenshot = sct.grab(monitor)
                
                # Convert to PIL Image
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                
                # Save screenshot
                filename = f"{timestamp.replace(':', '-').replace('.', '-')}_monitor_{i}.png"
                filepath = self.screenshots_dir / filename
                img.save(filepath)
                
                screenshot_data["monitors"].append({
                    "monitor_index": i,
                    "filename": filename,
                    "width": screenshot.width,
                    "height": screenshot.height,
                    "left": monitor["left"],
                    "top": monitor["top"]
                })
            
            self.stats["screenshots_taken"] += 1
            return screenshot_data
            
        except Exception as e:
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
        """Handle key press events"""
        try:
            key_name = None
            if hasattr(key, 'char') and key.char:
                key_name = key.char
            elif hasattr(key, 'name'):
                key_name = key.name
            else:
                key_name = str(key)
            
            event = {
                "type": "key_press",
                "timestamp": datetime.now().isoformat(),
                "key": key_name,
                "key_code": str(key)
            }
            
            self.log_event(event)
            self.stats["key_events"] += 1
            
        except Exception as e:
            print(f"Error handling key press: {e}")
    
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
    
    def process_monitor_loop(self):
        """Monitor running processes periodically"""
        while self.running:
            processes = self.get_running_processes()
            if processes:
                self.log_processes(processes)
            
            # Check processes every 5 seconds
            time.sleep(5)
    
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
        """Background thread to write processes to file"""
        while self.running or not self.process_queue.empty():
            try:
                processes = self.process_queue.get(timeout=1)
                with open(self.processes_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(processes) + '\n')
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
    tracker = TimeTracker(screenshot_interval=2.0)
    
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

