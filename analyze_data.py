"""
Utility script to analyze collected tracking data
"""

import json
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, List


def load_events(events_file: Path) -> List[Dict]:
    """Load events from JSONL file"""
    events = []
    if events_file.exists():
        with open(events_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
    return events


def load_processes(processes_file: Path) -> List[List[Dict]]:
    """Load process snapshots from JSONL file (one process per line, grouped by timestamp)"""
    snapshots = []
    if processes_file.exists():
        with open(processes_file, 'r', encoding='utf-8') as f:
            current_snapshot = []
            current_timestamp = None
            
            for line in f:
                if line.strip():
                    try:
                        process = json.loads(line)
                        process_timestamp = process.get('timestamp', '')
                        
                        # Group processes by timestamp (same timestamp = same snapshot)
                        if process_timestamp != current_timestamp:
                            # Save previous snapshot if it exists
                            if current_snapshot:
                                snapshots.append(current_snapshot)
                            # Start new snapshot
                            current_snapshot = [process]
                            current_timestamp = process_timestamp
                        else:
                            # Add to current snapshot
                            current_snapshot.append(process)
                    except json.JSONDecodeError:
                        # Handle old format (array of processes on one line)
                        try:
                            processes = json.loads(line)
                            if isinstance(processes, list):
                                snapshots.append(processes)
                        except:
                            continue
            
            # Don't forget the last snapshot
            if current_snapshot:
                snapshots.append(current_snapshot)
    
    return snapshots


def analyze_events(events: List[Dict]) -> Dict:
    """Analyze keyboard and mouse events"""
    analysis = {
        "total_events": len(events),
        "key_presses": 0,
        "key_releases": 0,
        "mouse_clicks": 0,
        "screen_locks": 0,
        "screen_unlocks": 0,
        "process_starts": 0,
        "process_stops": 0,
        "lock_events": [],
        "process_changes": [],
        "most_pressed_keys": Counter(),  # Actually tracks key releases now
        "activity_by_hour": defaultdict(int),
    }
    
    for event in events:
        event_type = event.get("type", "")
        
        if event_type == "key_press":
            # Key presses are no longer logged, but keep for backward compatibility
            analysis["key_presses"] += 1
            
        elif event_type == "key_release":
            analysis["key_releases"] += 1
            key = event.get("key", "unknown")
            analysis["most_pressed_keys"][key] += 1
            
        elif event_type == "mouse_click":
            analysis["mouse_clicks"] += 1
        
        elif event_type == "screen_locked":
            analysis["screen_locks"] += 1
            analysis["lock_events"].append({
                "type": "locked",
                "timestamp": event.get("timestamp", "")
            })
            
        elif event_type == "screen_unlocked":
            analysis["screen_unlocks"] += 1
            analysis["lock_events"].append({
                "type": "unlocked",
                "timestamp": event.get("timestamp", "")
            })
        
        elif event_type == "process_started":
            analysis["process_starts"] += 1
            analysis["process_changes"].append({
                "type": "started",
                "timestamp": event.get("timestamp", ""),
                "name": event.get("name", "unknown"),
                "pid": event.get("pid", 0)
            })
        
        elif event_type == "process_stopped":
            analysis["process_stops"] += 1
            analysis["process_changes"].append({
                "type": "stopped",
                "timestamp": event.get("timestamp", ""),
                "name": event.get("name", "unknown"),
                "pid": event.get("pid", 0)
            })
        
        # Analyze by hour
        timestamp = event.get("timestamp", "")
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                hour = dt.hour
                analysis["activity_by_hour"][hour] += 1
            except:
                pass
    
    return analysis


def analyze_processes(snapshots: List[List[Dict]]) -> Dict:
    """Analyze running processes"""
    all_processes = set()
    process_frequency = Counter()
    unique_processes = set()
    
    for snapshot in snapshots:
        for proc in snapshot:
            proc_name = proc.get("name", "unknown")
            unique_processes.add(proc_name)
            process_frequency[proc_name] += 1
    
    return {
        "total_snapshots": len(snapshots),
        "unique_processes": len(unique_processes),
        "most_common_processes": process_frequency.most_common(20),
    }


def print_report(data_dir: Path):
    """Print analysis report"""
    events_file = data_dir / "events.jsonl"
    processes_file = data_dir / "processes.jsonl"
    screenshots_dir = data_dir / "screenshots"
    
    print("=" * 60)
    print("TIME TRACKING ANALYSIS REPORT")
    print("=" * 60)
    print()
    
    # Load and analyze events
    events = load_events(events_file)
    if events:
        event_analysis = analyze_events(events)
        print("KEYBOARD & MOUSE ACTIVITY")
        print("-" * 60)
        print(f"Total events: {event_analysis['total_events']}")
        print(f"Key presses: {event_analysis['key_presses']}")
        print(f"Key releases: {event_analysis['key_releases']}")
        print(f"Mouse clicks: {event_analysis['mouse_clicks']}")
        print(f"Screen locks: {event_analysis['screen_locks']}")
        print(f"Screen unlocks: {event_analysis['screen_unlocks']}")
        print(f"Process starts: {event_analysis['process_starts']}")
        print(f"Process stops: {event_analysis['process_stops']}")
        print()
        
        if event_analysis['lock_events']:
            print("Lock/Unlock events:")
            for lock_event in event_analysis['lock_events'][:10]:  # Show first 10
                print(f"  {lock_event['type']}: {lock_event['timestamp']}")
            if len(event_analysis['lock_events']) > 10:
                print(f"  ... and {len(event_analysis['lock_events']) - 10} more")
            print()
        
        if event_analysis['process_changes']:
            print("Recent process changes (last 10):")
            for proc_change in event_analysis['process_changes'][-10:]:  # Show last 10
                print(f"  {proc_change['type']}: {proc_change['name']} (PID: {proc_change['pid']}) at {proc_change['timestamp']}")
            if len(event_analysis['process_changes']) > 10:
                print(f"  ... and {len(event_analysis['process_changes']) - 10} more")
            print()
        
        if event_analysis['most_pressed_keys']:
            print("Most pressed keys (top 10):")
            for key, count in event_analysis['most_pressed_keys'].most_common(10):
                print(f"  {key}: {count}")
            print()
        
        if event_analysis['activity_by_hour']:
            print("Activity by hour:")
            for hour in sorted(event_analysis['activity_by_hour'].keys()):
                count = event_analysis['activity_by_hour'][hour]
                print(f"  {hour:02d}:00 - {count} events")
            print()
    else:
        print("No events found")
        print()
    
    # Analyze processes
    snapshots = load_processes(processes_file)
    if snapshots:
        process_analysis = analyze_processes(snapshots)
        print("PROCESS MONITORING")
        print("-" * 60)
        print(f"Total snapshots: {process_analysis['total_snapshots']}")
        print(f"Unique processes: {process_analysis['unique_processes']}")
        print()
        
        if process_analysis['most_common_processes']:
            print("Most common processes (top 10):")
            for proc_name, count in process_analysis['most_common_processes'][:10]:
                print(f"  {proc_name}: appeared in {count} snapshots")
            print()
    else:
        print("No process data found")
        print()
    
    # Screenshot count
    if screenshots_dir.exists():
        screenshot_count = len(list(screenshots_dir.glob("*.png")))
        print("SCREENSHOTS")
        print("-" * 60)
        print(f"Total screenshots: {screenshot_count}")
        print(f"Location: {screenshots_dir.absolute()}")
        print()
    
    print("=" * 60)


def main():
    """Main entry point"""
    data_dir = Path("t_data")
    
    if not data_dir.exists():
        print(f"Error: Tracking data directory not found: {data_dir}")
        print("Run t.py first to collect data.")
        return
    
    print_report(data_dir)


if __name__ == "__main__":
    main()

