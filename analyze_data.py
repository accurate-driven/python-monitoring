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
    """Load process snapshots from JSONL file"""
    snapshots = []
    if processes_file.exists():
        with open(processes_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    snapshots.append(json.loads(line))
    return snapshots


def analyze_events(events: List[Dict]) -> Dict:
    """Analyze keyboard and mouse events"""
    analysis = {
        "total_events": len(events),
        "key_presses": 0,
        "key_releases": 0,
        "mouse_clicks": 0,
        "most_pressed_keys": Counter(),
        "activity_by_hour": defaultdict(int),
    }
    
    for event in events:
        event_type = event.get("type", "")
        
        if event_type == "key_press":
            analysis["key_presses"] += 1
            key = event.get("key", "unknown")
            analysis["most_pressed_keys"][key] += 1
            
        elif event_type == "key_release":
            analysis["key_releases"] += 1
            
        elif event_type == "mouse_click":
            analysis["mouse_clicks"] += 1
        
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
    data_dir = Path("tracking_data")
    
    if not data_dir.exists():
        print(f"Error: Tracking data directory not found: {data_dir}")
        print("Run tracker.py first to collect data.")
        return
    
    print_report(data_dir)


if __name__ == "__main__":
    main()

