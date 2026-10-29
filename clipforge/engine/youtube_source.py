"""
YouTube source ingester for ClipForge Studio.
Wraps yt-dlp to download video into the session's isolated source/ directory.
Handles Windows file locks, progress callbacks, and metadata extraction.
"""

import logging
import pathlib
import sys
from typing import Callable, Optional

# Ensure parent repo is in path so we can reuse youtube_downloader.py
from engine.config import REPO_ROOT
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from youtube_downloader import (
    validate_youtube_url,
    extract_video_id,
    fetch_metadata,
    YouTubeDownloader,
    VideoMetadata,
)

log = logging.getLogger(__name__)


class YouTubeIngestError(Exception):
    pass


def ingest_youtube_video(
    url: str,
    output_dir: pathlib.Path,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> tuple[pathlib.Path, VideoMetadata]:
    """
    Download a YouTube video to the given output directory (usually session.source_dir).

    Args:
        url: Full YouTube or youtu.be URL.
        output_dir: Target directory for the download.
        progress_callback: Optional callable(pct_0_to_1, message_str).

    Returns:
        (downloaded_mp4_path, VideoMetadata)
    """
    validation = validate_youtube_url(url)
    if not validation["valid"]:
        raise YouTubeIngestError(f"Invalid YouTube URL: {validation['error']}")

    video_id = validation["video_id"]

    if progress_callback:
        progress_callback(0.02, "Fetching video metadata...")

    meta, err = fetch_metadata(video_id)
    if err or not meta:
        raise YouTubeIngestError(f"Failed to fetch video metadata: {err}")

    log.info("Downloading YouTube video: %s (%s)", meta.title, meta.duration_str)

    downloader = YouTubeDownloader(output_dir=output_dir, cache_dir=output_dir / ".cache")

    def _on_progress(p):
        if progress_callback:
            # Map download 0..100% to fraction 0.05..0.95
            pct = 0.05 + (p.pct / 100.0) * 0.90
            msg = f"Downloading {p.pct:.1f}% ({p.speed}, ETA {p.eta})"
            progress_callback(pct, msg)

    downloaded = downloader.download(video_id, meta, progress_callback=_on_progress)
    if not downloaded or not downloaded.exists():
        raise YouTubeIngestError("Download failed or output file not created.")

    if progress_callback:
        progress_callback(1.0, f"Downloaded {downloaded.name}")

    return downloaded, meta
