"""
FFprobe wrapper — inspects media files and returns structured metadata.
Raises MediaInspectionError for invalid, missing, or corrupt files.
"""

import json
import logging
import pathlib
import subprocess
from dataclasses import dataclass, field
from typing import Optional

from engine.config import ffprobe_path

log = logging.getLogger(__name__)


class MediaInspectionError(Exception):
    pass


@dataclass
class StreamInfo:
    index: int
    codec_type: str       # video | audio | subtitle | data
    codec_name: str
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    duration: Optional[float] = None
    channels: Optional[int] = None
    sample_rate: Optional[int] = None
    bit_rate: Optional[int] = None
    rotation: int = 0
    pixel_format: Optional[str] = None
    extra: dict = field(default_factory=dict)


@dataclass
class MediaInfo:
    path: str
    duration: float           # seconds
    size_bytes: int
    format_name: str
    bit_rate: Optional[int]
    video: Optional[StreamInfo]
    audio: Optional[StreamInfo]
    all_streams: list[StreamInfo]
    raw: dict = field(default_factory=dict)

    @property
    def has_video(self) -> bool:
        return self.video is not None

    @property
    def has_audio(self) -> bool:
        return self.audio is not None

    @property
    def resolution(self) -> Optional[tuple[int, int]]:
        if self.video:
            return (self.video.width, self.video.height)
        return None

    @property
    def fps(self) -> Optional[float]:
        return self.video.fps if self.video else None


def _parse_fps(fps_str: str) -> Optional[float]:
    """Parse '30000/1001' or '25' style fps strings."""
    if not fps_str or fps_str == "0/0":
        return None
    try:
        if "/" in fps_str:
            num, den = fps_str.split("/")
            den = int(den)
            return round(int(num) / den, 3) if den else None
        return float(fps_str)
    except (ValueError, ZeroDivisionError):
        return None


def _parse_rotation(tags: dict) -> int:
    """Extract rotation from stream tags."""
    rot = tags.get("rotate", tags.get("rotation", "0"))
    try:
        return int(rot)
    except (ValueError, TypeError):
        return 0


def probe(path: str | pathlib.Path, timeout: int = 30) -> MediaInfo:
    """
    Run ffprobe on the given file and return a MediaInfo object.
    Raises MediaInspectionError if the file cannot be inspected.
    """
    path = pathlib.Path(path)
    if not path.exists():
        raise MediaInspectionError(f"File not found: {path}")
    if path.stat().st_size == 0:
        raise MediaInspectionError(f"File is empty: {path}")

    cmd = [
        ffprobe_path(),
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise MediaInspectionError(f"ffprobe timed out on: {path}")
    except FileNotFoundError:
        raise MediaInspectionError("ffprobe binary not found — is FFmpeg installed?")

    if result.returncode != 0:
        raise MediaInspectionError(
            f"ffprobe failed (exit {result.returncode}) on {path}: {result.stderr[:400]}"
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise MediaInspectionError(f"ffprobe output not valid JSON for {path}: {e}")

    fmt = data.get("format", {})
    try:
        duration = float(fmt.get("duration", 0))
    except (ValueError, TypeError):
        duration = 0.0

    try:
        size_bytes = int(fmt.get("size", path.stat().st_size))
    except (ValueError, TypeError):
        size_bytes = path.stat().st_size

    try:
        bit_rate = int(fmt.get("bit_rate", 0)) or None
    except (ValueError, TypeError):
        bit_rate = None

    streams: list[StreamInfo] = []
    for s in data.get("streams", []):
        codec_type = s.get("codec_type", "unknown")
        tags = s.get("tags", {})
        si = StreamInfo(
            index=s.get("index", 0),
            codec_type=codec_type,
            codec_name=s.get("codec_name", "unknown"),
            pixel_format=s.get("pix_fmt"),
            extra=s,
        )
        if codec_type == "video":
            si.width = s.get("width")
            si.height = s.get("height")
            si.fps = _parse_fps(s.get("r_frame_rate", ""))
            si.rotation = _parse_rotation(tags)
            try:
                si.duration = float(s.get("duration", duration))
            except (ValueError, TypeError):
                si.duration = duration
        elif codec_type == "audio":
            try:
                si.channels = int(s.get("channels", 1))
            except (ValueError, TypeError):
                si.channels = 1
            try:
                si.sample_rate = int(s.get("sample_rate", 44100))
            except (ValueError, TypeError):
                si.sample_rate = 44100
            try:
                si.duration = float(s.get("duration", duration))
            except (ValueError, TypeError):
                si.duration = duration
        streams.append(si)

    video_stream = next((s for s in streams if s.codec_type == "video"), None)
    audio_stream = next((s for s in streams if s.codec_type == "audio"), None)

    # Use stream duration as fallback if format duration is 0
    if duration == 0.0:
        for s in streams:
            if s.duration and s.duration > 0:
                duration = s.duration
                break

    if duration <= 0:
        raise MediaInspectionError(f"Could not determine duration of: {path}")

    return MediaInfo(
        path=str(path),
        duration=round(duration, 3),
        size_bytes=size_bytes,
        format_name=fmt.get("format_name", "unknown"),
        bit_rate=bit_rate,
        video=video_stream,
        audio=audio_stream,
        all_streams=streams,
        raw=data,
    )

