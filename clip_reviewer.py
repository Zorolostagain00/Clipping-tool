#!/usr/bin/env python3
"""
Clip Reviewer — Interactive terminal UI to review, rate, and manage clips.
After clipper.py generates clips, use this to:
- View clip details and transcript previews
- Rate clips (keep/discard/maybe)
- Re-export specific clips with different settings
- Export only your "keep" list

Usage:
    python clip_reviewer.py
    python clip_reviewer.py output/logs/video_report.md
"""

import os
import sys
import json
import re
import argparse
import subprocess
from pathlib import Path
from datetime import datetime


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def format_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:05.2f}"


def load_clips_from_report(report_path: str) -> list:
    """Parse clip data from a markdown report."""
    clips = []
    
    with open(report_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find clip sections
    clip_sections = re.findall(
        r'### Clip #(\d+) — Score: ([\d.]+)\n\n'
        r'- \*\*Start:\*\* `([^`]+)`\n'
        r'- \*\*End:\*\* `([^`]+)`\n'
        r'- \*\*Duration:\*\* ([\d.]+) seconds\n'
        r'- \*\*Output File:\*\* `([^`]+)`\n\n'
        r'\*\*Transcript Preview:\*\*\n'
        r'> ([^\n]+)',
        content
    )
    
    for match in clip_sections:
        clip_num, score, start_str, end_str, duration, output_file, preview = match
        clips.append({
            'clip_number': int(clip_num),
            'score': float(score),
            'start_str': start_str,
            'end_str': end_str,
            'duration': float(duration),
            'output_file': output_file,
            'preview': preview,
            'rating': 'unreviewed'
        })
    
    return clips


def load_clips_from_json(json_path: str) -> list:
    """Load clips from a JSON file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        clips = json.load(f)
    for clip in clips:
        if 'rating' not in clip:
            clip['rating'] = 'unreviewed'
    return clips


def save_ratings(clips: list, output_path: str):
    """Save clip ratings to JSON."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(clips, f, indent=2, default=str)
    print(f"\n  💾 Ratings saved to: {output_path}")


def display_clip(clip: dict, current: int, total: int):
    """Display a single clip's details."""
    clear_screen()
    
    rating_emoji = {
        'keep': '✅ KEEP',
        'discard': '❌ DISCARD', 
        'maybe': '⚠️  MAYBE',
        'unreviewed': '❓ UNREVIEWED'
    }
    
    print("=" * 65)
    print(f"  📹 CLIP #{clip['clip_number']:03d}   [{current}/{total}]   {rating_emoji.get(clip.get('rating', 'unreviewed'), '?')}")
    print("=" * 65)
    print()
    print(f"  ⭐ Engagement Score: {clip.get('score', 0):.1f}")
    print(f"  ⏱️  Start:    {clip.get('start_str', format_time(clip.get('start', 0)))}")
    print(f"  ⏱️  End:      {clip.get('end_str', format_time(clip.get('end', 0)))}")
    print(f"  📏 Duration: {clip.get('duration', 0):.1f} seconds")
    print(f"  📁 File:     {clip.get('output_file', clip.get('output_name', 'Not exported'))}")
    print()
    print("  📝 Transcript Preview:")
    print("  " + "─" * 50)
    
    preview = clip.get('preview', clip.get('text_preview', 'N/A'))
    # Word-wrap preview
    words = preview.split()
    line = "  "
    for word in words:
        if len(line) + len(word) + 1 > 63:
            print(line)
            line = "  " + word + " "
        else:
            line += word + " "
    if line.strip():
        print(line)
    
    print("  " + "─" * 50)
    print()
    print("  ACTIONS:")
    print("  [K] Keep    [D] Discard    [M] Maybe    [S] Skip")
    print("  [P] Play clip    [B] Back    [Q] Quit & Save")
    print()


def play_clip(clip: dict):
    """Open the clip file with the default media player."""
    output_file = clip.get('output_file', clip.get('output_name', ''))
    
    # Try to find the actual file
    candidates = [
        output_file,
        f"output/clips/{output_file}",
        f"output/clips/{Path(output_file).name}"
    ]
    
    for candidate in candidates:
        if Path(candidate).exists():
            print(f"\n  🎬 Opening: {candidate}")
            if os.name == 'nt':
                os.startfile(candidate)
            else:
                subprocess.Popen(['xdg-open', candidate])
            return
    
    print(f"\n  ❌ File not found: {output_file}")
    input("  Press Enter to continue...")


def interactive_review(clips: list, ratings_file: str):
    """Run the interactive clip review session."""
    current_idx = 0
    total = len(clips)
    
    while current_idx < total:
        clip = clips[current_idx]
        display_clip(clip, current_idx + 1, total)
        
        action = input("  Your choice: ").strip().lower()
        
        if action == 'k':
            clip['rating'] = 'keep'
            current_idx += 1
        elif action == 'd':
            clip['rating'] = 'discard'
            current_idx += 1
        elif action == 'm':
            clip['rating'] = 'maybe'
            current_idx += 1
        elif action == 's':
            current_idx += 1
        elif action == 'p':
            play_clip(clip)
        elif action == 'b':
            current_idx = max(0, current_idx - 1)
        elif action == 'q':
            save_ratings(clips, ratings_file)
            break
        else:
            print("  Invalid choice. Use K/D/M/S/P/B/Q")
            import time; time.sleep(1)
    
    # Summary
    clear_screen()
    print("\n" + "="*55)
    print("  📊 REVIEW SUMMARY")
    print("="*55)
    
    keep = [c for c in clips if c.get('rating') == 'keep']
    discard = [c for c in clips if c.get('rating') == 'discard']
    maybe = [c for c in clips if c.get('rating') == 'maybe']
    unreviewed = [c for c in clips if c.get('rating') == 'unreviewed']
    
    print(f"\n  ✅ Keep:       {len(keep)} clips")
    print(f"  ❌ Discard:    {len(discard)} clips")
    print(f"  ⚠️  Maybe:      {len(maybe)} clips")
    print(f"  ❓ Unreviewed: {len(unreviewed)} clips")
    
    if keep:
        print(f"\n  📋 Your KEEP list:")
        for c in keep:
            print(f"     #{c['clip_number']:03d} | ★{c.get('score',0):.1f} | {c.get('output_file', c.get('output_name', ''))}")
    
    save_ratings(clips, ratings_file)
    print()


def find_latest_report(logs_dir: str = "output/logs") -> str:
    """Find the most recent report file."""
    logs_path = Path(logs_dir)
    reports = sorted(logs_path.glob("*_report.md"), key=lambda x: x.stat().st_mtime, reverse=True)
    return str(reports[0]) if reports else None


def main():
    parser = argparse.ArgumentParser(
        description='Interactive clip reviewer — rate and manage your clips.',
    )
    parser.add_argument('input', nargs='?', default=None,
                        help='Report .md file or ratings .json file (auto-detects latest if omitted)')
    args = parser.parse_args()
    
    print("\n" + "="*55)
    print("  🎬 CLIP REVIEWER")
    print("  Review, rate, and manage your clips")
    print("="*55 + "\n")
    
    # Find input file
    input_path = args.input
    
    if input_path is None:
        # Try latest report
        input_path = find_latest_report()
        if input_path is None:
            print("  ❌ No report found. Run clipper.py first.")
            sys.exit(1)
        print(f"  📋 Auto-detected report: {input_path}\n")
    
    input_path = Path(input_path)
    
    # Load clips
    if input_path.suffix == '.json':
        clips = load_clips_from_json(str(input_path))
    elif input_path.suffix == '.md':
        clips = load_clips_from_report(str(input_path))
    else:
        print(f"  ❌ Unsupported file type: {input_path.suffix}")
        sys.exit(1)
    
    if not clips:
        print("  ❌ No clips found in file. Check the report format.")
        sys.exit(1)
    
    print(f"  ✅ Loaded {len(clips)} clips for review\n")
    
    # Sort by score (best first)
    clips.sort(key=lambda x: x.get('score', 0), reverse=True)
    
    # Ratings output file
    ratings_file = str(input_path.parent / f"{input_path.stem}_ratings.json")
    
    # Start review
    interactive_review(clips, ratings_file)


if __name__ == '__main__':
    main()
