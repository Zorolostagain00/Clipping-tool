"""
Tests for OutputValidator.
"""

import pathlib
import subprocess
import tempfile
import pytest

from engine.output_validator import validate_export, ValidationResult


def create_minimal_mp4(path: pathlib.Path, duration: float = 5.0) -> None:
    """Create a real (tiny) mp4 using FFmpeg for testing."""
    import shutil
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg not available")
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi", "-i", f"color=c=black:s=64x64:d={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-c:v", "libx264", "-c:a", "aac",
        "-t", str(duration),
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode != 0:
        pytest.skip(f"Could not create test mp4: {result.stderr.decode()[:200]}")


class TestOutputValidator:
    def test_valid_mp4_passes(self, tmp_path):
        mp4 = tmp_path / "test.mp4"
        create_minimal_mp4(mp4, duration=5.0)
        result = validate_export(mp4, expected_duration=5.0, duration_tolerance=2.0)
        assert result.ok is True
        assert len(result.errors) == 0

    def test_missing_file_fails(self, tmp_path):
        result = validate_export(tmp_path / "nonexistent.mp4")
        assert result.ok is False
        assert any("not exist" in e for e in result.errors)

    def test_empty_file_fails(self, tmp_path):
        empty = tmp_path / "empty.mp4"
        empty.write_bytes(b"")
        result = validate_export(empty)
        assert result.ok is False

    def test_returns_validation_result_type(self, tmp_path):
        result = validate_export(tmp_path / "missing.mp4")
        assert isinstance(result, ValidationResult)

    def test_duration_mismatch_fails(self, tmp_path):
        mp4 = tmp_path / "test_dur.mp4"
        create_minimal_mp4(mp4, duration=5.0)
        # Expect 60s but got 5s → fail
        result = validate_export(mp4, expected_duration=60.0, duration_tolerance=2.0)
        assert result.ok is False
        assert any("duration" in e.lower() for e in result.errors)

    def test_file_size_reported(self, tmp_path):
        mp4 = tmp_path / "test_size.mp4"
        create_minimal_mp4(mp4, duration=3.0)
        result = validate_export(mp4, expected_duration=3.0, duration_tolerance=2.0)
        assert result.file_size is not None
        assert result.file_size > 0

