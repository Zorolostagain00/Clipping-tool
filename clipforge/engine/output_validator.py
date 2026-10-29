"""
Output validator — verifies exported clips with ffprobe.
Never trust an export without validating it.
"""

import logging
import pathlib
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    ok: bool
    path: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    actual_duration: Optional[float] = None
    file_size: Optional[int] = None


def validate_export(
    path: str | pathlib.Path,
    expected_duration: Optional[float] = None,
    duration_tolerance: float = 2.0,
    min_size_bytes: int = 1024,
) -> ValidationResult:
    """
    Validate an exported video file.

    Args:
        path: Path to the exported file.
        expected_duration: Expected duration in seconds (optional).
        duration_tolerance: Allowed deviation from expected duration.
        min_size_bytes: Minimum acceptable file size.

    Returns:
        ValidationResult with ok=True if all checks pass.
    """
    from engine.media_probe import probe, MediaInspectionError

    path = pathlib.Path(path)
    errors = []
    warnings = []

    if not path.exists():
        return ValidationResult(ok=False, path=str(path), errors=["File does not exist"])

    file_size = path.stat().st_size
    if file_size < min_size_bytes:
        errors.append(f"File too small: {file_size} bytes (minimum {min_size_bytes})")

    try:
        info = probe(path)
    except MediaInspectionError as e:
        errors.append(f"ffprobe failed: {e}")
        return ValidationResult(ok=False, path=str(path), errors=errors, file_size=file_size)

    if not info.has_video:
        errors.append("No video stream found in exported file")

    actual_duration = info.duration

    if expected_duration is not None:
        deviation = abs(actual_duration - expected_duration)
        if deviation > duration_tolerance:
            errors.append(
                f"Duration mismatch: expected {expected_duration:.1f}s, "
                f"got {actual_duration:.1f}s (deviation {deviation:.1f}s > tolerance {duration_tolerance:.1f}s)"
            )
        elif deviation > duration_tolerance * 0.5:
            warnings.append(f"Minor duration deviation: {deviation:.2f}s")

    ok = len(errors) == 0
    if ok:
        log.info("Export validated OK: %s (%.1fs, %d bytes)", path.name, actual_duration, file_size)
    else:
        log.error("Export validation FAILED: %s — %s", path.name, "; ".join(errors))

    return ValidationResult(
        ok=ok,
        path=str(path),
        errors=errors,
        warnings=warnings,
        actual_duration=actual_duration,
        file_size=file_size,
    )

