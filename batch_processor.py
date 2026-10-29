#!/usr/bin/env python3
"""
Batch Processor — Run the clipping system on multiple videos automatically.

Usage:
    python batch_processor.py                     # Process all videos in input/
    python batch_processor.py --model small       # Use better model for all
    python batch_processor.py --dry-run           # Preview mode for all videos
    python batch_processor.py video1.mp4 video2.mp4  # Specific files
"""

import os
import sys
import glob
import argparse
import subprocess
import time
from pathlib import Path
from datetime import datetime


SUPPORTED_EXTENSIONS = ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v', '.flv']


def format_duration(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    elif m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def find_videos(input_dir: str = "input") -> list:
    """Find all supported video files in the input directory."""
    videos = []
    input_path = Path(input_dir)
    
    if not input_path.exists():
        return []
    
    for ext in SUPPORTED_EXTENSIONS:
        videos.extend(input_path.glob(f"*{ext}"))
        videos.extend(input_path.glob(f"*{ext.upper()}"))
    
    return sorted(set(videos))


def process_video(video_path: str, model: str = "base", dry_run: bool = False,
                  min_score: float = None, output_dir: str = None) -> dict:
    """Run clipper.py on a single video and return results."""
    start_time = time.time()
    
    cmd = [sys.executable, 'clipper.py', str(video_path), '--model', model]
    
    if dry_run:
        cmd.append('--dry-run')
    if min_score is not None:
        cmd.extend(['--min-score', str(min_score)])
    if output_dir:
        cmd.extend(['--output', output_dir])
    
    print(f"\n  🎬 Processing: {Path(video_path).name}")
    print(f"  Command: {' '.join(cmd)}\n")
    
    result = subprocess.run(cmd, capture_output=False, text=True)
    
    elapsed = time.time() - start_time
    
    return {
        'video': str(video_path),
        'name': Path(video_path).name,
        'success': result.returncode == 0,
        'elapsed': elapsed,
        'returncode': result.returncode
    }


def main():
    parser = argparse.ArgumentParser(
        description='Batch process multiple videos with the AI Clipping System.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python batch_processor.py
  python batch_processor.py --model small
  python batch_processor.py --dry-run
  python batch_processor.py input/video1.mp4 input/video2.mp4
        """
    )
    parser.add_argument('videos', nargs='*', help='Specific video files to process (default: all in input/)')
    parser.add_argument('--model', '-m', default='base',
                        choices=['tiny', 'base', 'small', 'medium', 'large'],
                        help='Whisper model (default: base)')
    parser.add_argument('--dry-run', '-d', action='store_true',
                        help='Preview mode — no clip export')
    parser.add_argument('--min-score', '-s', type=float, default=None,
                        help='Minimum engagement score')
    parser.add_argument('--output', '-o', default=None,
                        help='Output directory for all clips')
    parser.add_argument('--input-dir', default='input',
                        help='Directory to scan for videos (default: input/)')
    
    args = parser.parse_args()
    
    print("\n" + "="*65)
    print("  🎬  BATCH VIDEO PROCESSOR")
    print(f"  Model: {args.model} | Dry Run: {args.dry_run}")
    print("="*65)
    
    # Determine video list
    if args.videos:
        videos = [Path(v) for v in args.videos if Path(v).exists()]
        missing = [v for v in args.videos if not Path(v).exists()]
        if missing:
            print(f"\n  ⚠️  Not found: {', '.join(missing)}")
    else:
        videos = find_videos(args.input_dir)
    
    if not videos:
        print(f"\n  ❌ No videos found in '{args.input_dir}' folder.")
        print(f"  Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}")
        print(f"  Put your videos in the input\\ folder and try again.\n")
        sys.exit(1)
    
    print(f"\n  📋 Found {len(videos)} video(s) to process:\n")
    for i, v in enumerate(videos, 1):
        size_mb = v.stat().st_size / (1024*1024)
        print(f"    {i}. {v.name} ({size_mb:.1f} MB)")
    
    print()
    
    # Confirm
    if not args.dry_run and len(videos) > 1:
        confirm = input(f"  Process all {len(videos)} videos? [Y/n]: ").strip().lower()
        if confirm == 'n':
            print("  Cancelled.")
            sys.exit(0)
    
    # Process each video
    batch_start = time.time()
    results = []
    
    for i, video in enumerate(videos, 1):
        print(f"\n  {'='*55}")
        print(f"  VIDEO {i}/{len(videos)}: {video.name}")
        print(f"  {'='*55}")
        
        # Create per-video output directory if processing multiple
        out_dir = args.output
        if out_dir is None and len(videos) > 1:
            out_dir = f"output/clips/{video.stem}"
        
        result = process_video(
            str(video),
            model=args.model,
            dry_run=args.dry_run,
            min_score=args.min_score,
            output_dir=out_dir
        )
        results.append(result)
    
    # Final batch summary
    total_time = time.time() - batch_start
    successful = sum(1 for r in results if r['success'])
    
    print(f"\n\n  {'='*55}")
    print(f"  🏁 BATCH COMPLETE")
    print(f"  {'='*55}")
    print(f"  ✅ Successful: {successful}/{len(results)}")
    print(f"  ⏱️  Total time: {format_duration(total_time)}")
    print()
    
    for r in results:
        status = "✅" if r['success'] else "❌"
        print(f"  {status} {r['name']} — {format_duration(r['elapsed'])}")
    
    print()
    
    if not args.dry_run:
        print(f"  📁 Check output\\clips\\ for your clips!")
    
    print()


if __name__ == '__main__':
    main()
