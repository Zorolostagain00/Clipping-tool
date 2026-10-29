"""
ClipForge Studio — FastAPI backend entry point.

Endpoints:
  POST /api/jobs/create              Create a new processing job
  GET  /api/jobs                     List all jobs
  GET  /api/jobs/{id}                Get job status
  POST /api/jobs/{id}/cancel         Cancel a running job
  GET  /api/jobs/{id}/candidates     Get ranked candidates for a job
  POST /api/jobs/{id}/export         Export selected candidates
  GET  /api/system/diagnostics       System health check
  WS   /ws/jobs/{id}/progress        Real-time progress stream

Start with:
  python -m engine.main
  or
  uvicorn engine.main:app --host 127.0.0.1 --port 8765 --reload
"""

import asyncio
import concurrent.futures
import json
import logging
import pathlib
import sys
import uuid
from contextlib import asynccontextmanager
from typing import Optional

# Bootstrap environment (PATH, encoding) before anything else
import engine.config as _cfg  # noqa — side effects: PATH injection

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field

from engine.config import API_HOST, API_PORT, OUTPUT_DIR
from engine.database import init_db
from engine.job_manager import JobManager, TERMINAL_STATES
from engine.workspace_manager import WorkspaceManager
from engine.cleanup_manager import CleanupManager
from engine.pipeline import PipelineConfig, run_pipeline
from engine.clip_exporter import ExportConfig, export_candidate

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("clipforge.api")

# ── Global state ─────────────────────────────────────────────────────────────
job_manager = JobManager()
workspace_manager = WorkspaceManager()
cleanup_manager = CleanupManager()
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
_cancelled_jobs: set[str] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    init_db()
    recovered = cleanup_manager.recover_abandoned_sessions()
    if recovered:
        log.warning("Recovered %d abandoned sessions from previous run", len(recovered))
    log.info("ClipForge Studio engine started on %s:%d", API_HOST, API_PORT)
    yield
    _executor.shutdown(wait=False)
    log.info("ClipForge Studio engine stopped")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ClipForge Studio Engine",
    version="1.0.0",
    description="Local-first AI video clipping engine",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173",
                   "http://127.0.0.1:3000", "http://127.0.0.1:5173",
                   "app://.", "null"],  # Electron renderer
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic schemas ─────────────────────────────────────────────────────────

class CreateJobRequest(BaseModel):
    source_path: Optional[str] = None
    source_url: Optional[str] = None
    whisper_model: str = "base"
    language: Optional[str] = None
    min_duration: float = 20.0
    max_duration: float = 120.0
    min_score: float = 0.0
    max_candidates: int = 15
    window_size: float = 60.0
    window_step: float = 20.0
    use_transcript_cache: bool = True


class ExportRequest(BaseModel):
    candidate_ids: list[str]
    prefer_fast: bool = True
    target_aspect: Optional[str] = None   # e.g. "9:16"
    crf: int = Field(default=23, ge=0, le=51)
    audio_bitrate: str = "192k"
    filename_prefix: str = "clip"


# ── Background pipeline runner ────────────────────────────────────────────────

def _run_pipeline_sync(job_id: str, source_path: Optional[str], source_url: Optional[str], config: PipelineConfig):
    """Synchronous wrapper run in thread pool."""
    path_obj = pathlib.Path(source_path) if source_path else None
    return run_pipeline(
        job_id=job_id,
        source_path=path_obj,
        config=config,
        job_manager=job_manager,
        workspace_manager=workspace_manager,
        cancelled_check=lambda: job_id in _cancelled_jobs,
        source_url=source_url,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"service": "ClipForge Studio Engine", "version": "1.0.0", "status": "running"}


@app.get("/api/system/diagnostics")
async def diagnostics():
    import shutil
    results = {}
    # FFmpeg
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    results["ffmpeg"] = {"available": ffmpeg is not None, "path": ffmpeg}
    results["ffprobe"] = {"available": ffprobe is not None, "path": ffprobe}
    # Whisper backends
    try:
        import faster_whisper  # noqa
        results["faster_whisper"] = {"available": True}
    except ImportError:
        results["faster_whisper"] = {"available": False}
    try:
        import whisper  # noqa
        results["openai_whisper"] = {"available": True}
    except ImportError:
        results["openai_whisper"] = {"available": False}
    # yt-dlp
    ytdlp = shutil.which("yt-dlp")
    try:
        import yt_dlp  # noqa
        results["yt_dlp"] = {"available": True, "path": ytdlp}
    except ImportError:
        results["yt_dlp"] = {"available": False}
    # Storage
    import shutil as sh
    total, used, free = sh.disk_usage(str(OUTPUT_DIR))
    results["storage"] = {
        "output_dir": str(OUTPUT_DIR),
        "free_gb": round(free / 1e9, 2),
        "used_gb": round(used / 1e9, 2),
    }
    return results


@app.post("/api/jobs/create")
async def create_job(req: CreateJobRequest, background_tasks: BackgroundTasks):
    # Validate source
    if not req.source_path and not req.source_url:
        raise HTTPException(400, "Provide either source_path or source_url")

    source_type = "local" if req.source_path else "youtube"

    if req.source_path:
        p = pathlib.Path(req.source_path)
        if not p.exists():
            raise HTTPException(404, f"Source file not found: {req.source_path}")
        if not p.is_file():
            raise HTTPException(400, f"Source path is not a file: {req.source_path}")

    config = PipelineConfig(
        whisper_model=req.whisper_model,
        language=req.language,
        min_duration=req.min_duration,
        max_duration=req.max_duration,
        window_size=req.window_size,
        window_step=req.window_step,
        min_score=req.min_score,
        max_candidates=req.max_candidates,
        use_transcript_cache=req.use_transcript_cache,
    )

    job_id = job_manager.create_job(
        source_path=req.source_path,
        source_url=req.source_url,
        source_type=source_type,
        config=config.__dict__,
    )

    # Run pipeline in thread pool (non-blocking)
    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        _executor,
        _run_pipeline_sync,
        job_id, req.source_path, req.source_url, config,
    )

    return {"job_id": job_id, "state": "QUEUED", "message": "Pipeline started"}


@app.get("/api/jobs")
async def list_jobs(limit: int = 50):
    jobs = job_manager.list_jobs(limit=limit)
    return [
        {
            "id": j.id, "state": j.state, "progress": j.progress,
            "stage": j.stage, "message": j.message,
            "source_path": j.source_path, "source_type": j.source_type,
            "created_at": j.created_at, "updated_at": j.updated_at,
        }
        for j in jobs
    ]


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job not found: {job_id}")
    return {
        "id": job.id, "state": job.state, "progress": job.progress,
        "stage": job.stage, "message": job.message,
        "source_path": job.source_path, "source_url": job.source_url,
        "source_type": job.source_type, "config": job.config,
        "error": job.error, "session_dir": job.session_dir,
        "output_dir": job.output_dir,
        "created_at": job.created_at, "updated_at": job.updated_at,
    }


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job not found: {job_id}")
    if job.state in TERMINAL_STATES:
        raise HTTPException(400, f"Job already in terminal state: {job.state}")
    _cancelled_jobs.add(job_id)
    job_manager.update_job(job_id, state="CANCELLED", message="Cancelled by user")
    return {"job_id": job_id, "state": "CANCELLED"}


@app.get("/api/jobs/{job_id}/candidates")
async def get_candidates(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job not found: {job_id}")
    candidates = job_manager.get_candidates(job_id)
    return {"job_id": job_id, "candidates": candidates, "count": len(candidates)}


@app.post("/api/jobs/{job_id}/export")
async def export_clips(job_id: str, req: ExportRequest, background_tasks: BackgroundTasks):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job not found: {job_id}")
    if job.state != "COMPLETED":
        raise HTTPException(400, f"Job must be COMPLETED to export. Current state: {job.state}")

    candidates = job_manager.get_candidates(job_id)
    selected = [c for c in candidates if c["id"] in req.candidate_ids]
    if not selected:
        raise HTTPException(400, "No matching candidates found for provided IDs")

    source_path = pathlib.Path(job.source_path)
    if not source_path.exists():
        raise HTTPException(404, f"Source file no longer available: {source_path}")

    # Get session for renders dir
    session = workspace_manager.get_session_by_job(job_id)
    renders_dir = session.renders_dir if session else OUTPUT_DIR / "renders" / job_id
    renders_dir.mkdir(parents=True, exist_ok=True)

    export_config = ExportConfig(
        output_dir=OUTPUT_DIR,
        filename_prefix=req.filename_prefix,
        crf=req.crf,
        audio_bitrate=req.audio_bitrate,
        target_aspect=req.target_aspect,
    )

    # Probe for video dimensions
    video_width = video_height = None
    try:
        from engine.media_probe import probe as mp
        info = mp(source_path)
        if info.video:
            video_width, video_height = info.video.width, info.video.height
    except Exception:
        pass

    results = []
    for cand in selected:
        try:
            result = export_candidate(
                source_path=source_path,
                start=cand["start_time"],
                end=cand["end_time"],
                renders_dir=renders_dir,
                final_output_dir=OUTPUT_DIR,
                config=export_config,
                candidate_id=cand["id"],
                video_width=video_width,
                video_height=video_height,
                prefer_fast=req.prefer_fast,
            )
            if result.ok:
                job_manager.update_candidate_export(
                    cand["id"], str(result.output_path), validated=True
                )
            results.append({
                "candidate_id": cand["id"],
                "ok": result.ok,
                "output_path": str(result.output_path) if result.output_path else None,
                "error": result.error,
                "mode": result.mode,
            })
        except Exception as e:
            results.append({
                "candidate_id": cand["id"],
                "ok": False,
                "output_path": None,
                "error": str(e),
                "mode": "error",
            })

    return {"job_id": job_id, "exports": results}


@app.get("/api/clips")
async def list_clips():
    """List all exported clips in the output directory."""
    clips = []
    for f in sorted(OUTPUT_DIR.glob("*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True):
        stat = f.stat()
        clips.append({
            "name": f.name,
            "path": str(f),
            "size_bytes": stat.st_size,
            "modified": stat.st_mtime,
        })
    return {"clips": clips, "count": len(clips)}


# ── WebSocket progress stream ─────────────────────────────────────────────────

@app.websocket("/ws/jobs/{job_id}/progress")
async def ws_progress(websocket: WebSocket, job_id: str):
    await websocket.accept()

    job = job_manager.get_job(job_id)
    if not job:
        await websocket.send_json({"type": "error", "message": f"Job not found: {job_id}"})
        await websocket.close()
        return

    # Send current state immediately
    await websocket.send_json({
        "type": "state",
        "job_id": job_id,
        "state": job.state,
        "progress": job.progress,
        "stage": job.stage,
        "message": job.message,
    })

    if job.state in TERMINAL_STATES:
        await websocket.close()
        return

    # Subscribe to future updates
    q = job_manager.subscribe(job_id)
    try:
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=30.0)
                await websocket.send_json(msg)
                if msg.get("state") in TERMINAL_STATES:
                    break
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        pass
    finally:
        job_manager.unsubscribe(job_id, q)
    await websocket.close()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "engine.main:app",
        host=API_HOST,
        port=API_PORT,
        log_level="info",
        reload=False,
    )

