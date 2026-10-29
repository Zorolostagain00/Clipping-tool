"""
Pipeline orchestrator — runs all processing stages for a job in sequence.

Stages (in order):
  1. INSPECTING   — ffprobe the source file
  2. TRANSCRIBING — run Whisper on extracted audio
  3. ANALYZING    — score and generate candidates
  4. COMPLETED    — all done

Each stage updates job progress. Cancellation is checked between stages.
Long-running work is done in-process (not subprocess) for Phase 1.
"""

import logging
import pathlib
import subprocess
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Optional

from engine.config import (
    ffmpeg_path,
    DEFAULT_WHISPER_MODEL,
    DEFAULT_LANGUAGE,
    DEFAULT_MIN_DURATION,
    DEFAULT_MAX_DURATION,
    DEFAULT_WINDOW_SIZE,
    DEFAULT_WINDOW_STEP,
    DEFAULT_MIN_SCORE,
    OUTPUT_DIR,
)
from engine.media_probe import probe, MediaInfo, MediaInspectionError
from engine.transcriber import get_transcriber, TranscriptionResult
from engine.candidate_generator import generate_candidates, CandidateInterval
from engine.job_manager import JobManager
from engine.workspace_manager import WorkspaceManager, Session
from engine.cleanup_manager import CleanupManager

log = logging.getLogger(__name__)


class PipelineError(Exception):
    pass


@dataclass
class PipelineConfig:
    whisper_model: str = DEFAULT_WHISPER_MODEL
    language: Optional[str] = DEFAULT_LANGUAGE
    min_duration: float = DEFAULT_MIN_DURATION
    max_duration: float = DEFAULT_MAX_DURATION
    window_size: float = DEFAULT_WINDOW_SIZE
    window_step: float = DEFAULT_WINDOW_STEP
    min_score: float = DEFAULT_MIN_SCORE
    max_candidates: int = 15
    use_transcript_cache: bool = True
    auto_clean_youtube: bool = True  # Remove YouTube downloads after finalization

    @classmethod
    def from_dict(cls, d: dict) -> "PipelineConfig":
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in allowed})


@dataclass
class PipelineResult:
    job_id: str
    ok: bool
    media_info: Optional[MediaInfo]
    transcript: Optional[TranscriptionResult]
    candidates: list[CandidateInterval]
    error: Optional[str] = None
    session_id: Optional[str] = None


def _extract_audio(
    source_path: pathlib.Path,
    audio_dir: pathlib.Path,
    job_id: str,
) -> pathlib.Path:
    """Extract mono 16kHz WAV audio from source for Whisper."""
    audio_path = audio_dir / f"{job_id}_audio.wav"
    cmd = [
        ffmpeg_path(),
        "-y",
        "-i", str(source_path),
        "-vn",
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(audio_path),
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=600,
    )
    if result.returncode != 0:
        raise PipelineError(f"Audio extraction failed: {result.stderr[-400:]}")
    return audio_path


def run_pipeline(
    job_id: str,
    source_path: Optional[pathlib.Path],
    config: PipelineConfig,
    job_manager: JobManager,
    workspace_manager: WorkspaceManager,
    cancelled_check: Optional[Callable[[], bool]] = None,
    source_url: Optional[str] = None,
) -> PipelineResult:
    """
    Run the full processing pipeline for a job.

    Args:
        job_id: The job ID (must already exist in DB).
        source_path: Absolute path to the source video (or None if downloading from source_url).
        config: Pipeline configuration.
        job_manager: JobManager instance for progress updates.
        workspace_manager: WorkspaceManager for temp directories.
        cancelled_check: Callable that returns True if the job was cancelled.
        source_url: Optional YouTube URL to download into session.source_dir.

    Returns:
        PipelineResult with all outputs.
    """
    def update(state: str, progress: float, stage: str, message: str):
        job_manager.update_job(
            job_id, state=state, progress=progress,
            stage=stage, message=message,
        )

    def is_cancelled() -> bool:
        return cancelled_check() if cancelled_check else False

    session: Optional[Session] = None
    is_youtube = bool(source_url)
    try:
        # ── Create workspace session ──────────────────────────────────────────
        source_info = {"type": "youtube" if is_youtube else "local"}
        if source_path:
            source_info["path"] = str(source_path)
        if source_url:
            source_info["url"] = source_url

        session = workspace_manager.create_session(
            job_id=job_id,
            source_info=source_info,
        )
        job_manager.update_job(job_id, session_dir=str(session.session_dir))

        # ── Stage 0: Ingest if YouTube URL ────────────────────────────────────
        if is_youtube and (not source_path or not source_path.exists()):
            if is_cancelled():
                raise PipelineError("Cancelled before ingestion")
            update("INGESTING", 0.02, "Ingesting", "Downloading YouTube source...")
            from engine.youtube_source import ingest_youtube_video

            def _yt_progress(pct: float, msg: str):
                update("INGESTING", min(0.02 + pct * 0.08, 0.10), "Ingesting", msg)

            downloaded_path, _ = ingest_youtube_video(
                url=source_url,
                output_dir=session.source_dir,
                progress_callback=_yt_progress,
            )
            source_path = downloaded_path
            job_manager.update_job(job_id, source_path=str(source_path))

        if not source_path or not source_path.exists():
            raise PipelineError(f"Source video file not found: {source_path}")

        # ── Stage 1: Inspect ─────────────────────────────────────────────────
        if is_cancelled():
            raise PipelineError("Cancelled before inspection")
        update("INSPECTING", 0.05, "Inspecting", f"Probing {source_path.name}…")

        try:
            media_info = probe(source_path)
        except MediaInspectionError as e:
            raise PipelineError(f"Media inspection failed: {e}")

        log.info(
            "Media: %s | duration=%.1fs | res=%s | fps=%s",
            source_path.name, media_info.duration,
            media_info.resolution, media_info.fps,
        )

        if not media_info.has_audio:
            raise PipelineError("Source has no audio stream — transcription requires audio")

        # ── Stage 2: Extract audio ────────────────────────────────────────────
        if is_cancelled():
            raise PipelineError("Cancelled before audio extraction")
        update("TRANSCRIBING", 0.10, "Extracting audio", "Extracting audio track…")

        audio_path = _extract_audio(source_path, session.audio_dir, job_id)
        log.info("Audio extracted: %s", audio_path)

        # ── Stage 3: Transcribe ───────────────────────────────────────────────
        if is_cancelled():
            raise PipelineError("Cancelled before transcription")
        update("TRANSCRIBING", 0.15, "Transcribing", f"Running {config.whisper_model} transcription…")

        transcriber = get_transcriber()

        def transcription_progress(frac: float):
            p = 0.15 + frac * 0.45  # 15% → 60%
            job_manager.update_job(
                job_id, progress=p,
                stage="Transcribing",
                message=f"Transcription {frac * 100:.0f}%…",
            )

        transcript = transcriber.transcribe(
            audio_path=audio_path,
            model_id=config.whisper_model,
            language=config.language,
            use_cache=config.use_transcript_cache,
            progress_callback=transcription_progress,
        )
        log.info(
            "Transcript: %d segments, lang=%s, %.1fs (cached=%s)",
            len(transcript.segments), transcript.language,
            transcript.transcription_time, transcript.cached,
        )

        # ── Stage 4: Generate candidates ─────────────────────────────────────
        if is_cancelled():
            raise PipelineError("Cancelled before candidate generation")
        update("ANALYZING", 0.65, "Analyzing", "Scoring transcript and generating candidates…")

        candidates = generate_candidates(
            transcript=transcript,
            total_duration=media_info.duration,
            window_size=config.window_size,
            window_step=config.window_step,
            min_duration=config.min_duration,
            max_duration=config.max_duration,
            min_score=config.min_score,
            max_candidates=config.max_candidates,
        )

        update("SCORING", 0.85, "Scoring", f"Ranked {len(candidates)} candidates")

        # ── Save candidates to DB ─────────────────────────────────────────────
        job_manager.save_candidates(job_id, [c.to_dict() for c in candidates])

        # ── Mark session finalized (cleanup ready) ────────────────────────────
        workspace_manager.mark_finalized(session)

        job_manager.complete_job(job_id, output_dir=str(OUTPUT_DIR))

        return PipelineResult(
            job_id=job_id,
            ok=True,
            media_info=media_info,
            transcript=transcript,
            candidates=candidates,
            session_id=session.session_id if session else None,
        )

    except PipelineError as e:
        log.error("Pipeline error for job %s: %s", job_id, e)
        if session:
            workspace_manager.mark_failed(session, str(e))
        job_manager.fail_job(job_id, str(e))
        return PipelineResult(
            job_id=job_id, ok=False,
            media_info=None, transcript=None, candidates=[],
            error=str(e),
            session_id=session.session_id if session else None,
        )
    except Exception as e:
        log.exception("Unexpected error in pipeline for job %s", job_id)
        if session:
            workspace_manager.mark_failed(session, str(e))
        job_manager.fail_job(job_id, f"Unexpected error: {e}")
        return PipelineResult(
            job_id=job_id, ok=False,
            media_info=None, transcript=None, candidates=[],
            error=str(e),
            session_id=session.session_id if session else None,
        )

