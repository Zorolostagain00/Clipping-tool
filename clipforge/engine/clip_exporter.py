"""
Clip exporter — renders candidate clips to output files using FFmpeg.

Two export modes:
  FastExport  — stream copy, near-instant, no quality loss (compatible formats only).
  PreciseExport — full decode/encode, slower, supports crops/filters/subtitles.

Every export is followed by output_validator to confirm success.
Renders go to session renders/ dir first, then moved to output/ on validation success.
"""

import logging
import pathlib
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from engine.config import ffmpeg_path, OUTPUT_DIR
from engine.output_validator import validate_export, ValidationResult

log = logging.getLogger(__name__)


class ExportError(Exception):
    pass


@dataclass
class ExportConfig:
    # Output
    output_dir: Optional[pathlib.Path] = None   # defaults to OUTPUT_DIR
    filename_prefix: str = "clip"
    video_codec: str = "libx264"                # for PreciseExport
    audio_codec: str = "aac"
    crf: int = 23                               # quality (lower = better)
    preset: str = "fast"
    # Aspect ratio cropping (optional)
    target_aspect: Optional[str] = None         # e.g. "9:16" | "1:1" | "16:9"
    # Audio
    audio_bitrate: str = "192k"


@dataclass
class ExportResult:
    ok: bool
    output_path: Optional[pathlib.Path]
    validation: Optional[ValidationResult]
    mode: str   # "fast" | "precise"
    duration_seconds: float
    error: Optional[str] = None


def _build_crop_filter(
    in_w: int, in_h: int, target_aspect: str
) -> Optional[str]:
    """Build an FFmpeg crop filter string for the given target aspect ratio."""
    try:
        parts = target_aspect.split(":")
        tw, th = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return None

    target_ratio = tw / th
    source_ratio = in_w / in_h

    if abs(target_ratio - source_ratio) < 0.01:
        return None  # Already correct aspect

    if target_ratio < source_ratio:
        # Crop width
        new_w = int(in_h * target_ratio)
        new_h = in_h
        x = (in_w - new_w) // 2
        return f"crop={new_w}:{new_h}:{x}:0"
    else:
        # Crop height
        new_w = in_w
        new_h = int(in_w / target_ratio)
        y = (in_h - new_h) // 2
        return f"crop={new_w}:{new_h}:0:{y}"


def fast_export(
    source_path: pathlib.Path,
    start: float,
    end: float,
    renders_dir: pathlib.Path,
    config: ExportConfig,
    candidate_id: str,
) -> ExportResult:
    """
    Export using FFmpeg stream copy — very fast, no re-encode.
    Best for clips where no filters are needed.
    """
    t_start = time.perf_counter()
    duration = end - start
    out_filename = f"{config.filename_prefix}_{candidate_id[:8]}.mp4"
    render_path = renders_dir / out_filename

    cmd = [
        ffmpeg_path(),
        "-y",
        "-ss", str(start),
        "-to", str(end),
        "-i", str(source_path),
        "-c", "copy",
        "-movflags", "+faststart",
        str(render_path),
    ]

    log.info("FastExport: %s [%.1f-%.1f]", source_path.name, start, end)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=300,
        )
    except subprocess.TimeoutExpired:
        raise ExportError(f"FFmpeg timed out exporting {candidate_id}")

    if result.returncode != 0:
        raise ExportError(f"FFmpeg error (exit {result.returncode}): {result.stderr[-500:]}")

    val = validate_export(render_path, expected_duration=duration, duration_tolerance=3.0)

    if not val.ok:
        # Stream copy sometimes has duration issues — fall through to caller
        log.warning("FastExport validation warnings: %s", val.errors)

    elapsed = time.perf_counter() - t_start
    return ExportResult(
        ok=val.ok,
        output_path=render_path if val.ok else None,
        validation=val,
        mode="fast",
        duration_seconds=elapsed,
        error="; ".join(val.errors) if not val.ok else None,
    )


def precise_export(
    source_path: pathlib.Path,
    start: float,
    end: float,
    renders_dir: pathlib.Path,
    config: ExportConfig,
    candidate_id: str,
    video_width: Optional[int] = None,
    video_height: Optional[int] = None,
) -> ExportResult:
    """
    Export using full decode/encode — supports crop, subtitle, quality settings.
    """
    t_start = time.perf_counter()
    duration = end - start
    out_filename = f"{config.filename_prefix}_{candidate_id[:8]}_hq.mp4"
    render_path = renders_dir / out_filename

    video_filters = []
    if config.target_aspect and video_width and video_height:
        crop = _build_crop_filter(video_width, video_height, config.target_aspect)
        if crop:
            video_filters.append(crop)

    cmd = [
        ffmpeg_path(),
        "-y",
        "-ss", str(start),
        "-to", str(end),
        "-i", str(source_path),
        "-c:v", config.video_codec,
        "-crf", str(config.crf),
        "-preset", config.preset,
        "-c:a", config.audio_codec,
        "-b:a", config.audio_bitrate,
        "-movflags", "+faststart",
    ]

    if video_filters:
        cmd += ["-vf", ",".join(video_filters)]

    cmd.append(str(render_path))

    log.info("PreciseExport: %s [%.1f-%.1f] filters=%s", source_path.name, start, end, video_filters)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=600,
        )
    except subprocess.TimeoutExpired:
        raise ExportError(f"FFmpeg timed out in precise export for {candidate_id}")

    if result.returncode != 0:
        raise ExportError(f"FFmpeg error (exit {result.returncode}): {result.stderr[-500:]}")

    val = validate_export(render_path, expected_duration=duration, duration_tolerance=5.0)
    elapsed = time.perf_counter() - t_start

    return ExportResult(
        ok=val.ok,
        output_path=render_path if val.ok else None,
        validation=val,
        mode="precise",
        duration_seconds=elapsed,
        error="; ".join(val.errors) if not val.ok else None,
    )


def export_candidate(
    source_path: pathlib.Path,
    start: float,
    end: float,
    renders_dir: pathlib.Path,
    final_output_dir: pathlib.Path,
    config: ExportConfig,
    candidate_id: str,
    video_width: Optional[int] = None,
    video_height: Optional[int] = None,
    prefer_fast: bool = True,
) -> ExportResult:
    """
    Export a candidate clip, validate, and move to final output directory.
    Tries fast export first; falls back to precise if fast validation fails.
    """
    renders_dir.mkdir(parents=True, exist_ok=True)
    final_output_dir.mkdir(parents=True, exist_ok=True)

    result = None
    if prefer_fast and not config.target_aspect:
        try:
            result = fast_export(source_path, start, end, renders_dir, config, candidate_id)
        except ExportError as e:
            log.warning("FastExport failed, trying PreciseExport: %s", e)
            result = None

    if result is None or not result.ok:
        result = precise_export(
            source_path, start, end, renders_dir, config, candidate_id,
            video_width=video_width, video_height=video_height,
        )

    if result.ok and result.output_path:
        final_path = final_output_dir / result.output_path.name
        shutil.move(str(result.output_path), str(final_path))
        result.output_path = final_path
        log.info("Clip exported to: %s", final_path)

    return result

