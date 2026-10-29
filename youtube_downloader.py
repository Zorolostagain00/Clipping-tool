#!/usr/bin/env python3
"""
YouTube Video Acquirer
======================
Modular video acquisition component. Downloads YouTube videos using yt-dlp,
validates URLs, reports progress, handles errors, and caches downloads.

Designed to slot into the existing ViralClippingPipeline as a pre-processing step.

LEGAL NOTE:
  Only download videos you own or have explicit permission to process.
  This module respects yt-dlp's built-in restrictions; it does NOT bypass
  DRM, age-gates that require sign-in, or private/unlisted video access.

Usage (standalone):
    python youtube_downloader.py https://youtu.be/dQw4w9WgXcQ
    python youtube_downloader.py https://youtu.be/dQw4w9WgXcQ --info-only
    python youtube_downloader.py https://youtu.be/dQw4w9WgXcQ --output D:/MyClips/
"""

import os
import sys
import re
import json
import time
import shutil
import hashlib
import argparse
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Callable


# ============================================================
#  CONSTANTS
# ============================================================

CACHE_DIR = Path("input/yt_cache")
YTDLP_FORMATS = [
    # Prefer: best quality single-file (mp4) up to 1080p, with audio
    "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best",
]
MAX_DURATION_MINUTES = 180   # refuse videos longer than 3 hours
MAX_FILESIZE_MB = 4096       # refuse estimated files bigger than 4 GB


# ============================================================
#  URL VALIDATION
# ============================================================

# Standard patterns — no API key required, purely local regex
_YT_PATTERNS = [
    # Full watch URLs
    r"(?:https?://)?(?:www\.)?youtube\.com/watch\?(?:.*&)?v=([\w\-]{11})",
    # Short URLs
    r"(?:https?://)?youtu\.be/([\w\-]{11})",
    # Shorts
    r"(?:https?://)?(?:www\.)?youtube\.com/shorts/([\w\-]{11})",
    # Embed
    r"(?:https?://)?(?:www\.)?youtube\.com/embed/([\w\-]{11})",
    # Mobile
    r"(?:https?://)?m\.youtube\.com/watch\?(?:.*&)?v=([\w\-]{11})",
]

_YT_COMPILED = [re.compile(p, re.IGNORECASE) for p in _YT_PATTERNS]


def extract_video_id(url: str) -> Optional[str]:
    """Return the 11-char YouTube video ID from a URL, or None."""
    url = url.strip()
    for pattern in _YT_COMPILED:
        m = pattern.search(url)
        if m:
            return m.group(1)
    return None


def validate_youtube_url(url: str) -> Dict:
    """
    Validate a YouTube URL without any API key.
    Returns:
        {
            "valid": bool,
            "video_id": str | None,
            "normalized_url": str | None,
            "error": str | None,
        }
    """
    url = url.strip()

    if not url:
        return {"valid": False, "video_id": None, "normalized_url": None,
                "error": "URL cannot be empty."}

    video_id = extract_video_id(url)

    if video_id is None:
        return {
            "valid": False,
            "video_id": None,
            "normalized_url": None,
            "error": (
                "URL does not appear to be a valid YouTube link. "
                "Supported formats: youtube.com/watch?v=..., youtu.be/..., "
                "youtube.com/shorts/..."
            ),
        }

    normalized = f"https://www.youtube.com/watch?v={video_id}"
    return {
        "valid": True,
        "video_id": video_id,
        "normalized_url": normalized,
        "error": None,
    }


# ============================================================
#  METADATA FETCHER (no API key — uses yt-dlp --dump-json)
# ============================================================

class VideoMetadata:
    """Holds information about a YouTube video retrieved via yt-dlp."""

    def __init__(self, raw: dict):
        self.video_id: str = raw.get("id", "")
        self.title: str = raw.get("title", "Unknown Title")
        self.uploader: str = raw.get("uploader", raw.get("channel", "Unknown Channel"))
        self.duration_sec: float = float(raw.get("duration", 0))
        self.view_count: int = raw.get("view_count", 0)
        self.description: str = (raw.get("description", "") or "")[:500]
        self.thumbnail_url: str = raw.get("thumbnail", "")
        self.is_live: bool = raw.get("is_live", False)
        self.age_limit: int = raw.get("age_limit", 0)
        self.availability: str = raw.get("availability", "public")

    @property
    def duration_str(self) -> str:
        h = int(self.duration_sec // 3600)
        m = int((self.duration_sec % 3600) // 60)
        s = int(self.duration_sec % 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def display(self):
        print(f"\n  {'─'*55}")
        print(f"  Title:    {self.title}")
        print(f"  Channel:  {self.uploader}")
        print(f"  Duration: {self.duration_str}  ({self.duration_sec:.0f}s)")
        if self.view_count:
            print(f"  Views:    {self.view_count:,}")
        print(f"  {'─'*55}\n")


def fetch_metadata(video_id: str, timeout: int = 30) -> tuple:
    """
    Fetch video metadata using yt-dlp --dump-json (no API key needed).
    Returns (VideoMetadata | None, error_str | None).
    Does NOT download the video.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-download",
        "--no-playlist",
        "--socket-timeout", "15",
        url,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return None, "yt-dlp not found. Run: pip install yt-dlp"
    except subprocess.TimeoutExpired:
        return None, "Timed out while fetching video info."

    if result.returncode != 0:
        stderr = result.stderr.lower()
        if "private video" in stderr or "private" in stderr:
            return None, "This video is private and cannot be accessed."
        if "age" in stderr and "restrict" in stderr:
            return None, "This video has an age restriction and cannot be downloaded without sign-in."
        if "unavailable" in stderr or "not available" in stderr:
            return None, "This video is unavailable (may have been deleted or removed)."
        if "copyright" in stderr:
            return None, "This video is blocked due to a copyright claim."
        if "sign in" in stderr or "login" in stderr:
            return None, "This video requires sign-in to access."
        # Generic fallback
        snippet = result.stderr.strip()[-300:]
        return None, f"yt-dlp error: {snippet}"

    try:
        raw = json.loads(result.stdout.strip().split("\n")[0])
    except json.JSONDecodeError as e:
        return None, f"Could not parse yt-dlp output: {e}"

    meta = VideoMetadata(raw)

    # Sanity checks
    if meta.is_live:
        return None, "Live streams are not supported. Wait for the replay to be available."
    if meta.duration_sec <= 0:
        return None, "Could not determine video duration."
    if meta.duration_sec > MAX_DURATION_MINUTES * 60:
        return None, (
            f"Video is {meta.duration_str} long. "
            f"Maximum supported duration is {MAX_DURATION_MINUTES} minutes."
        )

    return meta, None


# ============================================================
#  DOWNLOADER
# ============================================================

class DownloadProgress:
    """Thread-safe download progress tracker."""

    def __init__(self):
        self.pct: float = 0.0
        self.speed: str = ""
        self.downloaded: str = ""
        self.total: str = ""
        self.eta: str = ""
        self.status: str = "starting"
        self._lock = threading.Lock()

    def update(self, line: str):
        """Parse a yt-dlp progress line and update state."""
        with self._lock:
            # [download]  45.3% of  234.56MiB at  2.50MiB/s ETA 00:45
            m = re.search(
                r"\[download\]\s+([\d.]+)%\s+of\s+([\d.]+\s*\S+)\s+at\s+([\d.]+\s*\S+)\s+ETA\s+(\S+)",
                line,
            )
            if m:
                self.pct = float(m.group(1))
                self.total = m.group(2)
                self.speed = m.group(3)
                self.eta = m.group(4)
                self.status = "downloading"
            elif "[Merger]" in line or "[ffmpeg]" in line:
                self.status = "merging"
                self.pct = 99.0
            elif "Destination:" in line:
                self.status = "writing"

    def display(self):
        """Print current progress to stdout."""
        with self._lock:
            bar_len = 35
            filled = int(bar_len * self.pct / 100)
            bar = "█" * filled + "░" * (bar_len - filled)
            speed_str = f"  {self.speed}/s" if self.speed else ""
            size_str = f"  {self.total}" if self.total else ""
            eta_str = f"  ETA {self.eta}" if self.eta else ""
            status = self.status.upper()
            print(
                f"\r  [{bar}] {self.pct:5.1f}%  {status}{speed_str}{size_str}{eta_str}",
                end="",
                flush=True,
            )


class VideoDownloader:
    """
    Downloads YouTube videos using yt-dlp.
    Handles caching, progress, cancellation, and cleanup.
    """

    def __init__(self, cache_dir: Path = CACHE_DIR, output_dir: Path = None):
        self.cache_dir = Path(cache_dir)
        self.output_dir = Path(output_dir) if output_dir else Path("input")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._cancel_requested = False
        self._process: Optional[subprocess.Popen] = None

    def cancel(self):
        """Request cancellation of an in-progress download."""
        self._cancel_requested = True
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
            except Exception:
                pass

    def _cache_key(self, video_id: str) -> str:
        return video_id

    def get_cached_path(self, video_id: str) -> Optional[Path]:
        """Return path to cached download if it exists and is valid."""
        cache_meta = self.cache_dir / f"{video_id}.json"
        if not cache_meta.exists():
            return None
        try:
            with open(cache_meta, "r") as f:
                info = json.load(f)
            cached_file = Path(info.get("local_path", ""))
            if cached_file.exists() and cached_file.stat().st_size > 1024:
                return cached_file
        except Exception:
            pass
        return None

    def _save_cache_meta(self, video_id: str, local_path: Path, meta: VideoMetadata):
        cache_meta = self.cache_dir / f"{video_id}.json"
        with open(cache_meta, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "video_id": video_id,
                    "local_path": str(local_path),
                    "title": meta.title,
                    "duration": meta.duration_sec,
                    "downloaded_at": datetime.now().isoformat(),
                },
                f,
                indent=2,
            )

    def _safe_filename(self, title: str, video_id: str) -> str:
        """Build a safe, deterministic filename from title + video_id."""
        safe = re.sub(r'[\\/:*?"<>|]', "_", title)
        safe = re.sub(r"\s+", "_", safe.strip())
        safe = safe[:60]  # cap length
        return f"{safe}_{video_id}"

    def download(
        self,
        video_id: str,
        meta: VideoMetadata,
        progress_callback: Callable[[DownloadProgress], None] = None,
        on_complete: Callable[[Path], None] = None,
        on_error: Callable[[str], None] = None,
    ) -> Optional[Path]:
        """
        Download a YouTube video to output_dir.
        Returns local Path on success, None on failure.
        Thread-safe; safe to call from a background thread.
        """
        self._cancel_requested = False

        # --- Check cache first ---
        cached = self.get_cached_path(video_id)
        if cached:
            print(f"\n  Using cached download: {cached.name}")
            if on_complete:
                on_complete(cached)
            return cached

        url = f"https://www.youtube.com/watch?v={video_id}"
        safe_name = self._safe_filename(meta.title, video_id)
        # yt-dlp will append the actual extension; use a template
        output_template = str(self.output_dir / f"{safe_name}.%(ext)s")

        cmd = [
            "yt-dlp",
            # Format selection: best mp4 ≤1080p with audio
            "-f", "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best",
            "--merge-output-format", "mp4",
            "--no-playlist",
            "-k",                   # keep intermediate files to prevent Windows WinError 32 delete locks
            "--socket-timeout", "30",
            "--retries", "3",
            "--fragment-retries", "5",
            "--no-part",            # avoid partial .part files cluttering output
            "-o", output_template,
            "--newline",            # one progress line per newline (parseable)
            url,
        ]

        progress = DownloadProgress()

        print(f"\n  Downloading: {meta.title}")
        print(f"  Duration: {meta.duration_str}  |  Output: {self.output_dir}\n")

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            lines = []
            for line in self._process.stdout:
                line = line.rstrip()
                lines.append(line)
                progress.update(line)
                if progress_callback:
                    progress_callback(progress)
                else:
                    progress.display()

                if self._cancel_requested:
                    self._process.terminate()
                    print("\n\n  Download cancelled by user.")
                    self._cleanup_partial(safe_name)
                    if on_error:
                        on_error("Download cancelled.")
                    return None

            self._process.wait()
            return_code = self._process.returncode

        except FileNotFoundError:
            err = "yt-dlp is not installed. Run: pip install yt-dlp"
            print(f"\n  ERROR: {err}")
            if on_error:
                on_error(err)
            return None
        except Exception as e:
            err = f"Unexpected error during download: {e}"
            print(f"\n  ERROR: {err}")
            if on_error:
                on_error(err)
            return None
        finally:
            self._process = None

        print()  # newline after progress bar

        # Check if the downloaded / merged file already exists and is healthy
        local_path = self._find_downloaded_file(safe_name)

        if return_code != 0:
            all_output = "\n".join(lines)
            # If the only failure was Windows file locking during temp file deletion, and the merged file exists:
            if local_path and local_path.exists() and local_path.stat().st_size > 1024 * 1024:
                print(f"  Note: Video merged successfully ({local_path.name}), ignoring post-cleanup error.")
            else:
                err = self._parse_error(all_output)
                print(f"\n  ERROR: {err}")
                if on_error:
                    on_error(err)
                return None

        # Clean up any residual fragment / intermediate stream files safely
        for extra in self.output_dir.glob(f"{safe_name}.f*"):
            try:
                extra.unlink()
            except Exception:
                pass

        if not local_path:
            err = "Download appeared to succeed but output file not found."
            print(f"\n  ERROR: {err}")
            if on_error:
                on_error(err)
            return None

        if local_path.stat().st_size < 1024:
            err = f"Downloaded file is suspiciously small: {local_path}"
            print(f"\n  ERROR: {err}")
            if on_error:
                on_error(err)
            return None

        size_mb = local_path.stat().st_size / (1024 * 1024)
        print(f"  Download complete: {local_path.name}  ({size_mb:.1f} MB)")

        # Save cache metadata
        self._save_cache_meta(video_id, local_path, meta)

        if on_complete:
            on_complete(local_path)

        return local_path

    def _find_downloaded_file(self, safe_name: str) -> Optional[Path]:
        """Search output_dir for a file matching the expected name stem."""
        for ext in ["mp4", "mkv", "webm", "avi", "mov"]:
            p = self.output_dir / f"{safe_name}.{ext}"
            if p.exists():
                return p
        # Fallback: any recently modified video file with the name stem
        candidates = list(self.output_dir.glob(f"{safe_name}*"))
        candidates = [c for c in candidates if c.suffix.lower() in
                      {".mp4", ".mkv", ".webm", ".avi", ".mov"}]
        if candidates:
            return max(candidates, key=lambda c: c.stat().st_mtime)
        return None

    def _cleanup_partial(self, safe_name: str):
        """Remove any partial download files."""
        for f in self.output_dir.glob(f"{safe_name}*"):
            try:
                f.unlink()
            except Exception:
                pass

    @staticmethod
    def _parse_error(output: str) -> str:
        """Extract a human-readable error from yt-dlp output."""
        lower = output.lower()
        if "private video" in lower:
            return "This video is private."
        if "age" in lower and "restrict" in lower:
            return "Age-restricted video — cannot download without authentication."
        if "unavailable" in lower or "removed" in lower:
            return "Video unavailable (deleted or removed)."
        if "copyright" in lower:
            return "Blocked by copyright claim."
        if "network" in lower or "connection" in lower:
            return "Network error. Check your internet connection."
        if "rate" in lower and "limit" in lower:
            return "Rate limited by YouTube. Wait a few minutes and try again."
        if "format" in lower and "not available" in lower:
            return "Requested video format is not available."
        # Last resort: last non-empty line
        lines = [l.strip() for l in output.strip().splitlines() if l.strip()]
        return lines[-1][:300] if lines else "Unknown download error."


# ============================================================
#  HIGH-LEVEL API
# ============================================================

def acquire_youtube_video(
    url: str,
    output_dir: str = "input",
    cache_dir: str = "input/yt_cache",
    progress_callback: Callable = None,
) -> tuple:
    """
    High-level entry point: validate URL → fetch metadata → download.
    Returns (local_path: Path | None, error: str | None, meta: VideoMetadata | None).
    """
    # 1. Validate URL
    val = validate_youtube_url(url)
    if not val["valid"]:
        return None, val["error"], None

    video_id = val["video_id"]
    print(f"\n  Video ID: {video_id}")
    print(f"  Normalized URL: {val['normalized_url']}\n")

    # 2. Fetch metadata
    print("  Fetching video info (no API key required)...")
    meta, err = fetch_metadata(video_id)
    if err:
        return None, err, None

    meta.display()

    # 3. Download
    downloader = VideoDownloader(
        cache_dir=Path(cache_dir),
        output_dir=Path(output_dir),
    )

    local_path = downloader.download(
        video_id=video_id,
        meta=meta,
        progress_callback=progress_callback,
    )

    if local_path is None:
        return None, "Download failed. See output above for details.", meta

    return local_path, None, meta


# ============================================================
#  STANDALONE CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="YouTube video downloader for the AI Viral Clipping System.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python youtube_downloader.py https://youtu.be/dQw4w9WgXcQ
  python youtube_downloader.py https://www.youtube.com/watch?v=dQw4w9WgXcQ --info-only
  python youtube_downloader.py https://youtu.be/dQw4w9WgXcQ --output D:\\MyClips\\

LEGAL:
  Only download content you own or have permission to process.
  This tool respects yt-dlp restrictions and does NOT bypass DRM or private access.
        """,
    )
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("--info-only", "-i", action="store_true",
                        help="Fetch metadata only, do not download.")
    parser.add_argument("--output", "-o", default="input",
                        help="Directory to save the downloaded video (default: input/)")
    parser.add_argument("--cache", default="input/yt_cache",
                        help="Cache directory for metadata and downloads (default: input/yt_cache/)")

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  YouTube Video Acquirer")
    print("=" * 60)

    # Validate
    val = validate_youtube_url(args.url)
    if not val["valid"]:
        print(f"\n  ERROR: {val['error']}\n")
        sys.exit(1)

    video_id = val["video_id"]
    print(f"\n  URL valid. Video ID: {video_id}")

    # Fetch metadata
    print("  Fetching video info...")
    meta, err = fetch_metadata(video_id)
    if err:
        print(f"\n  ERROR: {err}\n")
        sys.exit(1)

    meta.display()

    if args.info_only:
        print("  --info-only: skipping download.\n")
        sys.exit(0)

    # Download
    downloader = VideoDownloader(
        cache_dir=Path(args.cache),
        output_dir=Path(args.output),
    )

    local_path = downloader.download(video_id, meta)

    if local_path:
        print(f"\n  Output file: {local_path}")
        print(f"\n  Next step:")
        print(f"    python clipper.py \"{local_path}\"\n")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
