#!/usr/bin/env python3
"""
Subtitle Burner — Adds burned-in captions to clips for social media.
Reads the cached transcript from clipper.py and burns subtitles into exported clips.

Usage:
    python subtitle_burner.py output/clips/clip_001.mp4
    python subtitle_burner.py output/clips/ --all   (process all clips in folder)
"""

import os
import sys
import json
import subprocess
import argparse
import re
from pathlib import Path


def find_transcript(video_stem: str, logs_dir: str = "output/logs") -> dict:
    """Find the cached transcript JSON for a source video."""
    # Try to find any transcript JSON in logs
    logs_path = Path(logs_dir)
    for json_file in logs_path.glob("*_transcript.json"):
        with open(json_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def build_ass_subtitle(transcript: dict, clip_start: float, clip_end: float) -> str:
    """Build an ASS subtitle file for a clip's time range."""
    segments = transcript.get('segments', [])
    
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
Timer: 100.0000

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,22,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,0,2,10,10,30,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    lines = [header]
    
    for seg in segments:
        seg_start = seg.get('start', 0)
        seg_end = seg.get('end', 0)
        
        # Only include segments within clip range
        if seg_end < clip_start or seg_start > clip_end:
            continue
        
        # Adjust timestamps relative to clip start
        rel_start = max(0, seg_start - clip_start)
        rel_end = min(clip_end - clip_start, seg_end - clip_start)
        
        text = seg.get('text', '').strip()
        if not text:
            continue
        
        # Format ASS timestamp: H:MM:SS.CC
        def to_ass_time(t):
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            s = t % 60
            return f"{h}:{m:02d}:{s:05.2f}"
        
        start_str = to_ass_time(rel_start)
        end_str = to_ass_time(rel_end)
        
        # Clean text and wrap long lines
        text = text.replace('\n', ' ')
        text = re.sub(r'\s+', ' ', text)
        
        # Word-wrap at ~40 chars
        if len(text) > 40:
            words = text.split()
            lines_wrap = []
            current = []
            for word in words:
                if len(' '.join(current + [word])) <= 40:
                    current.append(word)
                else:
                    if current:
                        lines_wrap.append(' '.join(current))
                    current = [word]
            if current:
                lines_wrap.append(' '.join(current))
            text = r'\N'.join(lines_wrap)
        
        lines.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{text}")
    
    return '\n'.join(lines)


def burn_subtitles(clip_path: str, transcript: dict, clip_start: float, clip_end: float,
                   output_path: str = None) -> str:
    """Burn subtitles into a clip using ffmpeg."""
    clip_path = Path(clip_path)
    
    if output_path is None:
        output_path = str(clip_path.parent / f"{clip_path.stem}_subtitled{clip_path.suffix}")
    
    # Create temporary ASS subtitle file
    ass_path = str(clip_path.parent / f"{clip_path.stem}_temp.ass")
    ass_content = build_ass_subtitle(transcript, clip_start, clip_end)
    
    with open(ass_path, 'w', encoding='utf-8') as f:
        f.write(ass_content)
    
    # Burn subtitles with ffmpeg
    cmd = [
        'ffmpeg', '-y',
        '-i', str(clip_path),
        '-vf', f"ass='{ass_path}'",
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '23',
        '-c:a', 'copy',
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Clean up temp ASS file
    try:
        os.remove(ass_path)
    except:
        pass
    
    if result.returncode == 0:
        print(f"  ✅ Subtitled: {output_path}")
        return output_path
    else:
        print(f"  ❌ Error: {result.stderr[-300:]}")
        return None


def parse_timestamp_from_filename(filename: str) -> float:
    """Extract start timestamp from clip filename like 'clip_001_2m30s.mp4'."""
    match = re.search(r'(\d+)m(\d+)s', filename)
    if match:
        minutes = int(match.group(1))
        seconds = int(match.group(2))
        return minutes * 60 + seconds
    return 0.0


def main():
    parser = argparse.ArgumentParser(
        description='Burn subtitles into video clips for social media.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python subtitle_burner.py output/clips/clip_001.mp4
  python subtitle_burner.py output/clips/ --all
        """
    )
    parser.add_argument('input', help='Clip file or directory of clips')
    parser.add_argument('--all', '-a', action='store_true', help='Process all clips in directory')
    parser.add_argument('--transcript', '-t', default=None, help='Path to transcript JSON file')
    parser.add_argument('--output-dir', '-o', default=None, help='Output directory')
    
    args = parser.parse_args()
    
    print("\n" + "="*55)
    print("  📝 SUBTITLE BURNER")
    print("  Auto-captions for viral clips")
    print("="*55 + "\n")
    
    # Load transcript
    transcript = None
    if args.transcript:
        with open(args.transcript, 'r', encoding='utf-8') as f:
            transcript = json.load(f)
    else:
        transcript = find_transcript("", "output/logs")
    
    if not transcript:
        print("  ❌ No transcript found. Run clipper.py first to generate a transcript.")
        sys.exit(1)
    
    print(f"  ✅ Transcript loaded. Segments: {len(transcript.get('segments', []))}\n")
    
    input_path = Path(args.input)
    
    if args.all or input_path.is_dir():
        # Process all clips in directory
        clips = list(input_path.glob("*.mp4"))
        clips = [c for c in clips if '_subtitled' not in c.name]
        print(f"  📂 Found {len(clips)} clips to process\n")
        
        for clip in clips:
            clip_start = parse_timestamp_from_filename(clip.name)
            clip_end = clip_start + 120  # estimate
            
            out_dir = Path(args.output_dir) if args.output_dir else clip.parent
            out_path = str(out_dir / f"{clip.stem}_subtitled{clip.suffix}")
            
            print(f"  Processing: {clip.name} (starts at {clip_start:.0f}s)")
            burn_subtitles(str(clip), transcript, clip_start, clip_end, out_path)
    else:
        # Process single clip
        clip_start = parse_timestamp_from_filename(input_path.name)
        clip_end = clip_start + 120
        
        out_path = args.output_dir
        burn_subtitles(str(input_path), transcript, clip_start, clip_end, out_path)
    
    print("\n  🏁 Done! Check for *_subtitled.mp4 files.\n")


if __name__ == '__main__':
    main()
