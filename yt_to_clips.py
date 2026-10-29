#!/usr/bin/env python3
"""
YouTube-to-Clips: One-Command Pipeline
=======================================
Paste a YouTube URL → download → transcribe → find funny moments → export 10 clips.

This is the main entry point for the YouTube URL workflow.
It calls youtube_downloader.py then feeds the result straight into clipper.py.

Usage:
    python yt_to_clips.py https://youtu.be/dQw4w9WgXcQ
    python yt_to_clips.py https://youtu.be/dQw4w9WgXcQ --dry-run
    python yt_to_clips.py https://youtu.be/dQw4w9WgXcQ --model small
    python yt_to_clips.py https://youtu.be/dQw4w9WgXcQ --max-clips 10

LEGAL NOTE:
    Only use this tool on videos you own or have explicit permission to process.
    Respects YouTube's content restrictions. Does not bypass DRM or private access.
"""

import os
import sys
import json
import time
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# Fix Windows console UTF-8 encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Ensure WinGet/FFmpeg paths are in PATH if available
winget_links = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links"
if winget_links.exists() and str(winget_links) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{winget_links};{os.environ.get('PATH', '')}"


# Ensure we can import sibling modules
sys.path.insert(0, str(Path(__file__).parent))

from youtube_downloader import (
    validate_youtube_url,
    fetch_metadata,
    VideoDownloader,
    DownloadProgress,
    VideoMetadata,
)
from clipper import (
    Config,
    TranscriptionEngine,
    ClipAnalyzer,
    VideoExporter,
    ReportGenerator,
    get_video_duration,
    format_time,
    print_banner,
)


# ============================================================
#  PIPELINE
# ============================================================

class YouTubeClippingPipeline:
    """
    End-to-end pipeline:
      URL → validate → metadata → download → transcribe → clip → export → report
    """

    def __init__(self, config: Config = None):
        self.config = config or Config()
        self.transcriber = TranscriptionEngine(self.config.WHISPER_MODEL)
        self.analyzer = ClipAnalyzer(self.config)
        self.exporter = VideoExporter(self.config.OUTPUT_DIR)
        self.reporter = ReportGenerator()

    # ----------------------------------------------------------
    #  STAGE 1: Validate & Fetch Metadata
    # ----------------------------------------------------------

    def stage_validate(self, url: str) -> tuple:
        """Returns (video_id, normalized_url) or prints error and exits."""
        print("  Stage 1/6: Validating URL...", flush=True)
        val = validate_youtube_url(url)

        if not val["valid"]:
            print(f"\n  ERROR: {val['error']}")
            print("\n  Supported URL formats:")
            print("    https://www.youtube.com/watch?v=XXXXXXXXXXX")
            print("    https://youtu.be/XXXXXXXXXXX")
            print("    https://www.youtube.com/shorts/XXXXXXXXXXX")
            sys.exit(1)

        print(f"  OK — Video ID: {val['video_id']}")
        return val["video_id"], val["normalized_url"]

    def stage_metadata(self, video_id: str) -> VideoMetadata:
        """Returns VideoMetadata or prints error and exits."""
        print("\n  Stage 2/6: Fetching video info (no API key)...", flush=True)
        meta, err = fetch_metadata(video_id)
        if err:
            print(f"\n  ERROR: {err}")
            self._print_common_errors(err)
            sys.exit(1)

        meta.display()
        return meta

    # ----------------------------------------------------------
    #  STAGE 2: Download
    # ----------------------------------------------------------

    def stage_download(self, video_id: str, meta: VideoMetadata) -> Path:
        """Download the video. Returns local Path or exits."""
        print("  Stage 3/6: Downloading video...", flush=True)
        print("  (Only downloading content you own or have permission to process)")
        print()

        downloader = VideoDownloader(
            cache_dir=Path("input/yt_cache"),
            output_dir=Path("input"),
        )

        local_path = downloader.download(video_id, meta)

        if local_path is None:
            print("\n  Download failed. Cannot continue.")
            sys.exit(1)

        size_mb = local_path.stat().st_size / (1024 * 1024)
        print(f"\n  File ready: {local_path.name}  ({size_mb:.1f} MB)")
        return local_path

    # ----------------------------------------------------------
    #  STAGE 3: Validate downloaded file
    # ----------------------------------------------------------

    def stage_validate_file(self, local_path: Path) -> float:
        """Use ffprobe to validate the file and get duration."""
        print("\n  Stage 4/6: Validating downloaded file with FFprobe...", flush=True)
        duration = get_video_duration(str(local_path))
        print(f"  OK — Duration confirmed: {duration/60:.1f} min  ({format_time(duration)})")
        return duration

    # ----------------------------------------------------------
    #  STAGE 4: Transcribe
    # ----------------------------------------------------------

    def stage_transcribe(self, local_path: Path) -> dict:
        """Transcribe speech. Returns transcript dict."""
        print("\n  Stage 5/6: Transcribing speech locally...", flush=True)
        print(f"  Model: {self.config.WHISPER_MODEL}  |  GPU: auto-detected")
        transcript = self.transcriber.transcribe_video(
            str(local_path),
            cache_dir=self.config.LOG_DIR,
            force=self.config.FORCE_RETRANSCRIBE,
        )
        seg_count = len(transcript.get("segments", []))
        print(f"  Transcription complete. {seg_count} segments.")
        return transcript

    # ----------------------------------------------------------
    #  STAGE 5: Find clips
    # ----------------------------------------------------------

    def stage_find_clips(self, transcript: dict, duration: float,
                          max_clips: int) -> list:
        """Analyse transcript and return top-N ranked clips."""
        print("\n  Stage 6/6: Detecting funny & engaging moments...", flush=True)
        all_clips = self.analyzer.find_all_clips(transcript, duration)

        if not all_clips:
            print("  No clips found. The video may have little speech.")
            print("  Try: --model small  or  --min-score 1")
            return []

        # Limit to max_clips, sorted by score descending, then re-sorted chrono
        top_clips = sorted(all_clips, key=lambda c: c["score"], reverse=True)[:max_clips]
        top_clips.sort(key=lambda c: c["start"])

        # Re-number
        for i, c in enumerate(top_clips):
            c["clip_number"] = i + 1

        return top_clips

    # ----------------------------------------------------------
    #  STAGE 6: Export
    # ----------------------------------------------------------

    def stage_export(self, local_path: Path, clips: list,
                     video_stem: str, dry_run: bool) -> list:
        """Export clips to MP4. Returns list of successfully exported clips."""
        if dry_run:
            print("\n  DRY RUN — Skipping export. Remove --dry-run to generate MP4s.")
            return clips

        print(f"\n  Exporting {len(clips)} clip(s) with FFmpeg...\n")
        return self.exporter.export_all(str(local_path), clips, video_stem)

    # ----------------------------------------------------------
    #  STAGE 7: Report
    # ----------------------------------------------------------

    def stage_report(self, clips: list, local_path: Path,
                     duration: float, meta: VideoMetadata) -> str:
        """Generate a markdown report. Returns path to report."""
        video_stem = local_path.stem
        report_path = str(
            Path(self.config.LOG_DIR) / f"{video_stem}_report.md"
        )
        self.reporter.save(clips, str(local_path), duration, report_path)
        return report_path

    # ----------------------------------------------------------
    #  RESULTS DASHBOARD
    # ----------------------------------------------------------

    def print_dashboard(self, clips: list, local_path: Path,
                         meta: VideoMetadata, report_path: str,
                         dry_run: bool, duration: float):
        """Print a final summary dashboard."""
        total_dur = sum(c.get("duration", 0) for c in clips)
        coverage = (total_dur / duration * 100) if duration > 0 else 0

        print("\n" + "=" * 65)
        print("  RESULTS DASHBOARD")
        print("=" * 65)
        print(f"\n  Source:   {meta.title}")
        print(f"  Channel:  {meta.uploader}")
        print(f"  Duration: {meta.duration_str}")
        print(f"\n  Clips generated:  {len(clips)}")
        print(f"  Total clip time:  {total_dur/60:.1f} min")
        print(f"  Video coverage:   {coverage:.1f}%")

        if clips:
            print(f"\n  Top clips by engagement score:")
            top = sorted(clips, key=lambda c: c["score"], reverse=True)[:5]
            for rank, c in enumerate(top, 1):
                out = c.get("output_name", "not exported")
                print(f"    {rank}. #{c['clip_number']:03d}  "
                      f"{format_time(c['start'])} -> {format_time(c['end'])}  "
                      f"({c['duration']:.0f}s)  score:{c['score']:.1f}")
                if not dry_run:
                    print(f"         -> {out}")

        print(f"\n  Report: {report_path}")
        if not dry_run:
            print(f"  Clips:  {self.config.OUTPUT_DIR}")
        print("\n" + "=" * 65 + "\n")

    # ----------------------------------------------------------
    #  MAIN RUN
    # ----------------------------------------------------------

    def run(self, url: str, dry_run: bool = False, max_clips: int = 10) -> list:
        print_banner()
        print(f"  Source: {url}")
        print(f"  Mode:   {'DRY RUN (no export)' if dry_run else 'FULL (download + clip + export)'}")
        print(f"  Model:  {self.config.WHISPER_MODEL}")
        print(f"  Max clips: {max_clips}")
        print()

        # Stage 1: Validate URL
        video_id, norm_url = self.stage_validate(url)

        # Stage 2: Fetch metadata
        meta = self.stage_metadata(video_id)

        # Stage 3: Download
        local_path = self.stage_download(video_id, meta)

        # Stage 4: Validate downloaded file
        duration = self.stage_validate_file(local_path)

        # Stage 5: Transcribe
        transcript = self.stage_transcribe(local_path)

        # Stage 6: Find clips
        clips = self.stage_find_clips(transcript, duration, max_clips)

        if not clips:
            print("\n  No clips to export.\n")
            return []

        # Stage 7: Export
        video_stem = local_path.stem
        exported = self.stage_export(local_path, clips, video_stem, dry_run)

        # Stage 8: Verify exported files exist and are playable
        if not dry_run:
            self._verify_exports(exported)

        # Stage 9: Report
        report_path = self.stage_report(exported, local_path, duration, meta)

        # Stage 10: Dashboard
        self.print_dashboard(exported, local_path, meta, report_path, dry_run, duration)

        return exported

    # ----------------------------------------------------------
    #  HELPERS
    # ----------------------------------------------------------

    def _verify_exports(self, clips: list):
        """Verify each exported file exists and is non-empty."""
        print("\n  Verifying exported clips...")
        ok = 0
        fail = 0
        for clip in clips:
            out_path = clip.get("output_path")
            if out_path and Path(out_path).exists() and Path(out_path).stat().st_size > 1024:
                ok += 1
            else:
                fail += 1
                print(f"  WARNING: Clip #{clip.get('clip_number')} not found or empty: {out_path}")

        if fail == 0:
            print(f"  All {ok} clip(s) verified OK.")
        else:
            print(f"  {ok} clips OK, {fail} clips FAILED.")

    @staticmethod
    def _print_common_errors(err: str):
        if "private" in err.lower():
            print("\n  Private videos cannot be downloaded.")
            print("  The video owner has restricted access.")
        elif "age" in err.lower():
            print("\n  Age-restricted videos require sign-in to download.")
            print("  yt-dlp supports cookies if you add --cookies-from-browser")
        elif "unavailable" in err.lower():
            print("\n  The video may have been deleted or removed.")
        elif "yt-dlp" in err.lower() and "not found" in err.lower():
            print("\n  Install yt-dlp: pip install yt-dlp")


# ============================================================
#  CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "YouTube URL → AI Clips pipeline.\n"
            "Validates URL, downloads video, transcribes speech, "
            "finds funny moments, exports up to 10 MP4 clips.\n\n"
            "LEGAL: Only use on content you own or have permission to process."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python yt_to_clips.py https://youtu.be/dQw4w9WgXcQ
  python yt_to_clips.py https://youtu.be/dQw4w9WgXcQ --dry-run
  python yt_to_clips.py https://youtu.be/dQw4w9WgXcQ --model small --max-clips 10
  python yt_to_clips.py https://youtu.be/dQw4w9WgXcQ --output D:\\MyClips\\
        """,
    )

    parser.add_argument("url", help="YouTube video URL (watch, youtu.be, or Shorts)")
    parser.add_argument(
        "--model", "-m",
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model for transcription (default: base).",
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="Download and analyse but do NOT export MP4 clips.",
    )
    parser.add_argument(
        "--max-clips", "-n",
        type=int,
        default=10,
        help="Maximum number of clips to export (default: 10).",
    )
    parser.add_argument(
        "--output", "-o",
        default="output/clips",
        help="Output directory for clip files (default: output/clips/).",
    )
    parser.add_argument(
        "--min-duration",
        type=int,
        default=60,
        help="Minimum clip duration in seconds (default: 60).",
    )
    parser.add_argument(
        "--max-duration",
        type=int,
        default=120,
        help="Maximum clip duration in seconds (default: 120).",
    )
    parser.add_argument(
        "--retranscribe", "-r",
        action="store_true",
        help="Force re-transcription even if a cached transcript exists.",
    )
    parser.add_argument(
        "--min-score", "-s",
        type=float,
        default=None,
        help="Minimum engagement score for a clip to be included (default: auto).",
    )

    args = parser.parse_args()

    cfg = Config()
    cfg.WHISPER_MODEL = args.model
    cfg.MIN_CLIP_DURATION = args.min_duration
    cfg.MAX_CLIP_DURATION = args.max_duration
    cfg.TARGET_CLIP_DURATION = (args.min_duration + args.max_duration) // 2
    cfg.OUTPUT_DIR = args.output
    cfg.FORCE_RETRANSCRIBE = args.retranscribe

    # Create output dirs
    Path(cfg.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    Path(cfg.LOG_DIR).mkdir(parents=True, exist_ok=True)
    Path("input/yt_cache").mkdir(parents=True, exist_ok=True)

    pipeline = YouTubeClippingPipeline(cfg)
    clips = pipeline.run(
        url=args.url,
        dry_run=args.dry_run,
        max_clips=args.max_clips,
    )

    return 0 if clips else 1


if __name__ == "__main__":
    sys.exit(main())
