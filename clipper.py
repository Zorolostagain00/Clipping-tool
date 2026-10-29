#!/usr/bin/env python3
"""
Ultimate AI Viral Clipping System
==================================
Analyzes full videos and automatically finds ALL worthwhile moments.
No arbitrary clip limits. Completely local and free.

Usage:
    python clipper.py input/video.mp4
    python clipper.py input/video.mp4 --dry-run
    python clipper.py input/video.mp4 --model small --min-score 5
"""

import os
import sys
import json
import time
import math
import argparse
import subprocess
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple

# Fix Windows console UTF-8 encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Ensure WinGet/FFmpeg paths are in PATH if available
winget_links = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links"
if winget_links.exists() and str(winget_links) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{winget_links};{os.environ.get('PATH', '')}"


# ============================================================
#  CONFIGURATION
# ============================================================

class Config:
    # Clip duration settings (seconds)
    MIN_CLIP_DURATION = 45
    MAX_CLIP_DURATION = 120
    TARGET_CLIP_DURATION = 75

    # Analysis settings
    WINDOW_SIZE = 60        # seconds per analysis window
    WINDOW_STEP = 20        # seconds to advance each step
    CONTEXT_BUFFER = 5      # seconds of context to add before/after a clip
    BOUNDARY_TOLERANCE = 5  # seconds — how far to look for a natural sentence boundary

    # Whisper model to use
    WHISPER_MODEL = "base"

    # Paths
    OUTPUT_DIR = "output/clips"
    LOG_DIR = "output/logs"
    INPUT_DIR = "input"

    # Viral/engagement scoring: (regex pattern, weight)
    # Higher weight = more important signal
    HIGH_VALUE_PATTERNS = [
        # Comedy & reactions
        (r'\b(haha|lol|lmao|hilarious|funny|laugh|laughing|cringe|awkward)\b', 3),
        (r'\b(oh my god|omg|what the|no way|are you serious|seriously)\b', 4),
        (r'\b(did he just|did she just|did they just|I can\'t believe)\b', 4),
        (r'\b(wait what|wait no|hold on|oh no|oh yes)\b', 3),
        # Roasting & banter
        (r'\b(roast|savage|brutal|destroyed|demolished|wrecked|burned|owned)\b', 5),
        (r'\b(comeback|clap back|snap|drag|shade|throw shade)\b', 4),
        (r'\b(called out|cancel|cancelled|ratio)\b', 4),
        # Surprise & shock
        (r'\b(shocking|unbelievable|insane|crazy|wild|unexpected|plot twist)\b', 4),
        (r'\b(never thought|never expected|surprised me)\b', 3),
        (r'\b(turns out|and then|but then|suddenly|out of nowhere)\b', 3),
        # Controversy & hot takes
        (r'\b(controversial|unpopular opinion|hot take|change my mind)\b', 5),
        (r'\b(I disagree|actually no|wrong|let me be honest|real talk|ngl)\b', 3),
        (r'\b(fight me|prove me wrong|unpopular|problematic)\b', 3),
        # Strong emotional language
        (r'\b(amazing|incredible|absolutely|literally|genuinely|honestly)\b', 2),
        (r'\b(worst|best|ever|greatest|legendary|iconic|historic|goat)\b', 3),
        # Engagement-driving questions
        (r'\b(why would you|how could you|what were you thinking)\b', 3),
        (r'\b(can you believe|would you believe|who does that)\b', 3),
        # Stories & confessions
        (r'\b(story time|confession|I admit|secret|first time)\b', 4),
        (r'\b(back then|years ago|I used to|one time|this one time)\b', 2),
        # Punchlines & setups
        (r'\b(the thing is|here\'s the thing|and the best part)\b', 3),
        (r'\b(lowkey|highkey|no cap|frfr|deadass|bruh|bro|dude)\b', 2),
        # Disbelief / reaction
        (r'\b(bro what|bro no|bruh|sir|excuse me)\b', 2),
        (r'\b(the audacity|the nerve|I\'m done|I\'m dead|I can\'t)\b', 4),
    ]


# ============================================================
#  UTILITIES
# ============================================================

def format_time(seconds: float) -> str:
    """Convert seconds to HH:MM:SS.mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def seconds_to_hms(seconds: float) -> str:
    """Convert seconds to H:MM:SS for display."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def print_banner():
    print("\n" + "=" * 65)
    print("  [CLIP] ULTIMATE AI VIRAL CLIPPING SYSTEM")
    print("  Analyzes the ENTIRE video. No clip limits.")
    print("=" * 65 + "\n")


def print_progress(current: float, total: float, label: str = ""):
    """Print a progress bar to stdout."""
    if total <= 0:
        return
    pct = min(100.0, (current / total) * 100)
    bar_len = 38
    filled = int(bar_len * pct / 100)
    bar = "#" * filled + "-" * (bar_len - filled)
    print(f"\r  [{bar}] {pct:5.1f}%  {label:<25}", end="", flush=True)


def get_video_duration(video_path: str) -> float:
    """Use ffprobe to get video duration in seconds."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        print("\n  ERROR: ffprobe not found. Please install FFmpeg.")
        print("         Run: winget install Gyan.FFmpeg   (then restart terminal)")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("\n  ERROR: ffprobe timed out on this file.")
        sys.exit(1)

    if result.returncode != 0:
        print(f"\n  ERROR: ffprobe failed:\n{result.stderr}")
        sys.exit(1)

    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


# ============================================================
#  TRANSCRIPTION ENGINE
# ============================================================

class TranscriptionEngine:
    def __init__(self, model_name: str = "base"):
        self.model_name = model_name
        self.model = None

    def load_model(self):
        print(f"  Loading Whisper '{self.model_name}' model...")
        try:
            import whisper
            self.model = whisper.load_model(self.model_name)
            print(f"  Whisper '{self.model_name}' model ready.\n")
        except ImportError:
            print("  ERROR: openai-whisper not installed.")
            print("         Run: pip install openai-whisper")
            sys.exit(1)
        except Exception as e:
            print(f"  ERROR: Failed to load Whisper model: {e}")
            sys.exit(1)

    def transcribe_video(self, video_path: str, cache_dir: str = "output/logs",
                         force: bool = False) -> dict:
        """Transcribe a video, returning whisper result dict. Caches to disk."""
        video_name = Path(video_path).stem
        cache_file = Path(cache_dir) / f"{video_name}_transcript.json"

        if cache_file.exists() and not force:
            print(f"  Found cached transcript: {cache_file.name}")
            print(f"  (Use --retranscribe to force re-transcription)\n")
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)

        if self.model is None:
            self.load_model()

        print(f"  Transcribing speech (model: {self.model_name})...")
        print(f"  This runs locally - no internet required.")
        print(f"  Transcription is cached; subsequent runs are instant.\n")

        import whisper

        result = self.model.transcribe(
            video_path,
            verbose=False,
            word_timestamps=True,
            task="transcribe",
            fp16=False,        # FP32 for CPU compatibility
            temperature=0.0,   # Deterministic output
        )

        # Persist cache
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)

        seg_count = len(result.get("segments", []))
        print(f"\n  Transcription complete. {seg_count} segments. Cached to {cache_file.name}\n")
        return result


# ============================================================
#  CLIP ANALYZER
# ============================================================

class ClipAnalyzer:
    def __init__(self, config: Config):
        self.config = config

    def score_text(self, text: str) -> float:
        """Score a block of text for viral/entertainment potential."""
        if not text:
            return 0.0

        score = 0.0
        lower = text.lower()

        for pattern, weight in self.config.HIGH_VALUE_PATTERNS:
            hits = len(re.findall(pattern, lower, re.IGNORECASE))
            score += hits * weight

        # Structural bonuses
        score += text.count("?") * 2.0
        score += text.count("!") * 1.5
        score += text.count("...") * 0.5

        # Word-count scaling
        words = len(text.split())
        if words >= 100:
            score += 3.0
        elif words >= 50:
            score += 1.5
        elif words < 15:
            score *= 0.4

        return round(score, 2)

    def find_natural_start(self, segments: List[dict], target: float,
                            video_duration: float) -> float:
        """Snap clip start to the beginning of the nearest segment."""
        best = target
        best_dist = float("inf")

        for seg in segments:
            seg_start = seg.get("start", 0.0)
            dist = abs(seg_start - target)
            if dist < best_dist and dist <= self.config.BOUNDARY_TOLERANCE:
                best_dist = dist
                best = seg_start

        return max(0.0, best)

    def find_natural_end(self, segments: List[dict], target: float,
                          video_duration: float) -> float:
        """Snap clip end to after a sentence-ending segment near target."""
        best = target
        best_dist = float("inf")

        for seg in segments:
            seg_end = seg.get("end", 0.0)
            seg_text = seg.get("text", "").strip()
            dist = abs(seg_end - target)

            if dist <= self.config.BOUNDARY_TOLERANCE:
                is_sentence_end = seg_text.endswith((".", "!", "?", '"', "'"))
                effective_dist = dist * (0.5 if is_sentence_end else 1.0)
                if effective_dist < best_dist:
                    best_dist = effective_dist
                    best = seg_end + 0.3

        return min(video_duration, best)

    def build_window_scores(self, segments: List[dict],
                             video_duration: float) -> List[dict]:
        """Sweep the full video with overlapping windows and score each."""
        windows = []
        t = 0.0

        while t < video_duration:
            win_end = min(t + self.config.WINDOW_SIZE, video_duration)

            win_segs = [
                s for s in segments
                if s.get("end", 0) > t and s.get("start", 0) < win_end
            ]
            win_text = " ".join(s.get("text", "") for s in win_segs)
            score = self.score_text(win_text)

            windows.append({
                "start": t,
                "end": win_end,
                "score": score,
                "text": win_text,
            })

            print_progress(t, video_duration,
                           f"{seconds_to_hms(t)} / {seconds_to_hms(video_duration)}")
            t += self.config.WINDOW_STEP

        print()
        return windows

    def windows_to_candidates(self, windows: List[dict],
                               segments: List[dict],
                               video_duration: float) -> List[dict]:
        """Turn high-scoring windows into time-bounded clip candidates."""
        if not windows:
            return []

        scores = [w["score"] for w in windows]
        avg_score = sum(scores) / len(scores) if scores else 0
        threshold = max(avg_score * 0.65, 0.5)

        print(f"\n  Score stats: avg={avg_score:.2f}, threshold={threshold:.2f}")

        high_idxs = [i for i, w in enumerate(windows) if w["score"] >= threshold]

        if not high_idxs:
            n_top = max(1, len(windows) // 5)
            high_idxs = sorted(
                range(len(windows)),
                key=lambda x: windows[x]["score"],
                reverse=True
            )[:n_top]
            high_idxs.sort()

        print(f"  High-value windows: {len(high_idxs)} / {len(windows)}")

        # Group consecutive high-value windows (within 3 steps = 60s gap)
        groups: List[List[int]] = []
        current_group: List[int] = [high_idxs[0]]

        for idx in high_idxs[1:]:
            if idx - current_group[-1] <= 3:
                current_group.append(idx)
            else:
                groups.append(current_group)
                current_group = [idx]
        groups.append(current_group)

        print(f"  Clip regions found: {len(groups)}\n")

        candidates: List[dict] = []
        cfg = self.config

        for group in groups:
            group_start = windows[group[0]]["start"]
            group_end = windows[group[-1]]["end"]
            group_dur = group_end - group_start
            group_score = max(windows[i]["score"] for i in group)
            group_text = " ".join(windows[i]["text"] for i in group)

            if group_dur <= cfg.MAX_CLIP_DURATION:
                # Single clip
                cs = max(0.0, group_start - cfg.CONTEXT_BUFFER)
                ce = min(video_duration, group_end + cfg.CONTEXT_BUFFER)
                cs = self.find_natural_start(segments, cs, video_duration)
                ce = self.find_natural_end(segments, ce, video_duration)

                # Pad if too short
                if (ce - cs) < cfg.MIN_CLIP_DURATION:
                    pad = (cfg.MIN_CLIP_DURATION - (ce - cs)) / 2
                    cs = max(0.0, cs - pad)
                    ce = min(video_duration, ce + pad)

                if (ce - cs) >= cfg.MIN_CLIP_DURATION:
                    candidates.append({
                        "start": cs,
                        "end": ce,
                        "score": group_score,
                        "text_preview": group_text,
                    })
            else:
                # Group too long -- split into multiple clips
                n_sub = math.ceil(group_dur / cfg.TARGET_CLIP_DURATION)
                sub_dur = group_dur / n_sub

                for sub_i in range(n_sub):
                    sub_s = group_start + sub_i * sub_dur
                    sub_e = sub_s + sub_dur

                    sub_s = max(0.0, sub_s - 3.0)
                    sub_e = min(video_duration, sub_e + 3.0)
                    sub_s = self.find_natural_start(segments, sub_s, video_duration)
                    sub_e = self.find_natural_end(segments, sub_e, video_duration)

                    if (sub_e - sub_s) >= cfg.MIN_CLIP_DURATION:
                        sub_segs = [
                            s for s in segments
                            if s.get("start", 0) < sub_e and s.get("end", 0) > sub_s
                        ]
                        sub_text = " ".join(s.get("text", "") for s in sub_segs)
                        sub_score = self.score_text(sub_text)

                        candidates.append({
                            "start": sub_s,
                            "end": sub_e,
                            "score": sub_score,
                            "text_preview": sub_text,
                        })

        return candidates

    def deduplicate(self, candidates: List[dict]) -> List[dict]:
        """Remove candidates overlapping >50% with a higher-scored one."""
        ranked = sorted(candidates, key=lambda c: c["score"], reverse=True)
        kept: List[dict] = []

        for cand in ranked:
            overlaps = False
            for kept_c in kept:
                ov_start = max(cand["start"], kept_c["start"])
                ov_end = min(cand["end"], kept_c["end"])
                ov_dur = max(0.0, ov_end - ov_start)
                cand_dur = cand["end"] - cand["start"]
                kept_dur = kept_c["end"] - kept_c["start"]

                if (ov_dur > cand_dur * 0.50 or ov_dur > kept_dur * 0.50):
                    overlaps = True
                    break

            if not overlaps:
                kept.append(cand)

        kept.sort(key=lambda c: c["start"])
        for i, clip in enumerate(kept):
            clip["clip_number"] = i + 1
            clip["duration"] = clip["end"] - clip["start"]

        return kept

    def find_all_clips(self, transcript: dict, video_duration: float) -> List[dict]:
        segments = transcript.get("segments", [])
        if not segments:
            print("  WARNING: No speech segments found in transcript.")
            return []

        print(f"  Scanning {video_duration/60:.1f} min video ({len(segments)} segments)...\n")

        windows = self.build_window_scores(segments, video_duration)
        candidates = self.windows_to_candidates(windows, segments, video_duration)

        print(f"  Deduplicating {len(candidates)} candidates...")
        clips = self.deduplicate(candidates)
        print(f"  {len(clips)} unique clips found.\n")

        return clips


# ============================================================
#  VIDEO EXPORTER
# ============================================================

class VideoExporter:
    def __init__(self, output_dir: str = "output/clips"):
        self.output_dir = output_dir
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    def export_clip(self, source: str, clip: dict, output_name: str) -> Optional[str]:
        """Cut a single clip from source video using ffmpeg."""
        out_path = os.path.join(self.output_dir, output_name)
        start = clip["start"]
        duration = clip["end"] - clip["start"]

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", source,
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            "-avoid_negative_ts", "make_zero",
            out_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            n = clip.get("clip_number", "?")
            print(f"\n  ERROR: ffmpeg failed for clip #{n}:")
            print(f"         {result.stderr[-400:]}")
            return None

        return out_path

    def export_all(self, source: str, clips: List[dict],
                   video_stem: str = "clip") -> List[dict]:
        """Export every clip and annotate with file info."""
        total = len(clips)
        exported = []
        safe_stem = re.sub(r"[^\w\-]", "_", video_stem)

        print(f"\n  Exporting {total} clip(s)...\n")

        for clip in clips:
            n = clip["clip_number"]
            ts = f"{int(clip['start'] // 60)}m{int(clip['start'] % 60)}s"
            out_name = f"{safe_stem}_clip_{n:03d}_{ts}.mp4"

            print(f"  [{n:>3}/{total}]  #{n:03d}  "
                  f"{format_time(clip['start'])} -> {format_time(clip['end'])}  "
                  f"({clip['duration']:.0f}s)  score:{clip['score']:.1f}")

            out_path = self.export_clip(source, clip, out_name)

            if out_path:
                size_mb = os.path.getsize(out_path) / (1024 * 1024)
                print(f"         OK: {out_name}  ({size_mb:.1f} MB)")
                clip["output_name"] = out_name
                clip["output_path"] = out_path
                clip["file_size_mb"] = round(size_mb, 2)
                exported.append(clip)
            else:
                print(f"         FAILED: clip #{n}")

        return exported


# ============================================================
#  REPORT GENERATOR
# ============================================================

class ReportGenerator:
    def save(self, clips: List[dict], video_path: str,
             video_duration: float, out_file: str) -> str:
        video_name = Path(video_path).name
        ts_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_clip_sec = sum(c.get("duration", 0) for c in clips)
        coverage = (total_clip_sec / video_duration * 100) if video_duration > 0 else 0

        lines = [
            "# AI Viral Clipping Report",
            "",
            f"**Source Video:** `{video_name}`",
            f"**Duration:** {video_duration/60:.1f} min  ({format_time(video_duration)})",
            f"**Analysed:** {ts_now}",
            f"**Clips Found:** {len(clips)}",
            f"**Total Clip Content:** {total_clip_sec/60:.1f} min",
            f"**Coverage:** {coverage:.1f}% of source",
            "",
            "---",
            "",
            "## Ranking (Best First)",
            "",
            "| Rank | Clip | Start | End | Dur | Score | Preview |",
            "|------|------|-------|-----|-----|-------|---------|",
        ]

        for rank, clip in enumerate(
            sorted(clips, key=lambda c: c["score"], reverse=True), 1
        ):
            preview = clip.get("text_preview", "")[:80].replace("|", "-").replace("\n", " ")
            lines.append(
                f"| {rank} | #{clip['clip_number']:03d} | "
                f"{format_time(clip['start'])} | {format_time(clip['end'])} | "
                f"{clip.get('duration', 0):.0f}s | {clip['score']} | {preview}... |"
            )

        lines += ["", "---", "", "## All Clips (Chronological)", ""]

        for clip in clips:
            n = clip["clip_number"]
            out_name = clip.get("output_name", "Not exported")
            preview = clip.get("text_preview", "N/A")

            lines += [
                f"### Clip #{n:03d} -- Score: {clip['score']}",
                "",
                f"- **Start:** `{format_time(clip['start'])}`",
                f"- **End:**   `{format_time(clip['end'])}`",
                f"- **Duration:** {clip.get('duration', 0):.1f}s",
                f"- **Output File:** `{out_name}`",
                "",
                "**Transcript Preview:**",
                f"> {preview[:500]}",
                "",
                "---",
                "",
            ]

        report = "\n".join(lines)
        Path(out_file).parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(report)

        print(f"  Report saved: {out_file}")
        return report


# ============================================================
#  MAIN PIPELINE
# ============================================================

class ViralClippingPipeline:
    def __init__(self, config: Config = None):
        self.config = config or Config()
        self.transcriber = TranscriptionEngine(self.config.WHISPER_MODEL)
        self.analyzer = ClipAnalyzer(self.config)
        self.exporter = VideoExporter(self.config.OUTPUT_DIR)
        self.reporter = ReportGenerator()

    def run(self, video_path: str, dry_run: bool = False,
            min_score: Optional[float] = None,
            force_retranscribe: bool = False) -> List[dict]:
        print_banner()

        if not Path(video_path).exists():
            print(f"  ERROR: Video not found: {video_path}")
            sys.exit(1)

        video_stem = Path(video_path).stem

        # Step 1: Video info
        print("  Step 1: Reading video info...")
        video_duration = get_video_duration(video_path)
        print(f"  Duration: {video_duration/60:.1f} min  ({format_time(video_duration)})\n")

        # Step 2: Transcription
        print("  Step 2: Transcribing speech...")
        transcript = self.transcriber.transcribe_video(
            video_path, self.config.LOG_DIR, force=force_retranscribe
        )
        seg_count = len(transcript.get("segments", []))
        print(f"  Transcript ready. {seg_count} segments.\n")

        # Step 3: Find clips
        print("  Step 3: Finding ALL worthwhile moments...")
        clips = self.analyzer.find_all_clips(transcript, video_duration)

        # Step 4: Score filter
        if min_score is not None:
            before = len(clips)
            clips = [c for c in clips if c["score"] >= min_score]
            print(f"  Score filter (>= {min_score}): {before} -> {len(clips)} clips\n")

        if not clips:
            print("  WARNING: No clips found matching the criteria.\n")
            print("  Suggestions:")
            print("    - Use a better model: --model small")
            print("    - Lower score threshold: --min-score 1")
            print("    - Check that speech is audible in the video")
            return []

        # Summary before export
        total_dur = sum(c.get("duration", 0) for c in clips)
        coverage = (total_dur / video_duration * 100) if video_duration > 0 else 0

        print(f"  DISCOVERY SUMMARY")
        print(f"  {'─'*50}")
        print(f"  Clips found:     {len(clips)}")
        print(f"  Total content:   {total_dur/60:.1f} min")
        print(f"  Coverage:        {coverage:.1f}% of source video")
        print(f"  {'─'*50}\n")

        for c in clips:
            print(f"  #{c['clip_number']:03d}  "
                  f"{format_time(c['start'])} -> {format_time(c['end'])}  "
                  f"({c['duration']:.0f}s)  "
                  f"score:{c['score']:.1f}  "
                  f"{c.get('text_preview','')[:55]}...")
        print()

        # Step 5: Export
        if dry_run:
            print("  DRY RUN -- Clips analysed but NOT exported.")
            print("  Remove --dry-run to export clips.\n")
        else:
            print("  Step 5: Exporting clips with FFmpeg...")
            clips = self.exporter.export_all(video_path, clips, video_stem)

        # Step 6: Report
        print("\n  Step 6: Generating report...")
        report_path = str(Path(self.config.LOG_DIR) / f"{video_stem}_report.md")
        self.reporter.save(clips, video_path, video_duration, report_path)

        # Final summary
        print(f"\n  ALL DONE!")
        print(f"  {'='*50}")
        if not dry_run:
            print(f"  Exported:  {len(clips)} clip(s)")
            print(f"  Clips dir: {self.config.OUTPUT_DIR}")
        print(f"  Report:    {report_path}")
        print(f"  {'='*50}\n")

        return clips


# ============================================================
#  CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Ultimate AI Viral Clipping System — finds EVERY good moment.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python clipper.py input/podcast.mp4
  python clipper.py input/podcast.mp4 --dry-run
  python clipper.py input/podcast.mp4 --model small
  python clipper.py input/podcast.mp4 --min-score 5
  python clipper.py input/podcast.mp4 --min-duration 30 --max-duration 90
  python clipper.py input/podcast.mp4 --retranscribe
        """,
    )

    parser.add_argument("video", help="Path to source video file")
    parser.add_argument(
        "--model", "-m",
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model. Larger = more accurate but slower (default: base).",
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="Analyse only -- list clips without exporting.",
    )
    parser.add_argument(
        "--min-score", "-s",
        type=float,
        default=None,
        help="Minimum engagement score to include a clip (default: auto).",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output directory for clip files (default: output/clips/).",
    )
    parser.add_argument(
        "--retranscribe", "-r",
        action="store_true",
        help="Force re-transcription even when a cache exists.",
    )
    parser.add_argument(
        "--min-duration",
        type=int,
        default=45,
        help="Minimum clip duration in seconds (default: 45).",
    )
    parser.add_argument(
        "--max-duration",
        type=int,
        default=120,
        help="Maximum clip duration in seconds (default: 120).",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=60,
        help="Analysis window size in seconds (default: 60).",
    )

    args = parser.parse_args()

    cfg = Config()
    cfg.WHISPER_MODEL = args.model
    cfg.MIN_CLIP_DURATION = args.min_duration
    cfg.MAX_CLIP_DURATION = args.max_duration
    cfg.TARGET_CLIP_DURATION = (args.min_duration + args.max_duration) // 2
    cfg.WINDOW_SIZE = args.window
    if args.output:
        cfg.OUTPUT_DIR = args.output

    pipeline = ViralClippingPipeline(cfg)
    clips = pipeline.run(
        video_path=args.video,
        dry_run=args.dry_run,
        min_score=args.min_score,
        force_retranscribe=args.retranscribe,
    )

    return 0 if clips else 1


if __name__ == "__main__":
    sys.exit(main())
