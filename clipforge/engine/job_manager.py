"""
Job manager — persistent job state backed by SQLite.

Job states:
  QUEUED → INGESTING → INSPECTING → TRANSCRIBING → ANALYZING
  → SCORING → GENERATING → EXPORTING → VALIDATING → COMPLETED
  Failed states: FAILED | CANCELLED | INTERRUPTED

Progress broadcasts go to WebSocket subscribers via asyncio.Queue.
"""

import asyncio
import json
import logging
import pathlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from engine.database import get_db, init_db, row_to_dict, DB_PATH
from engine.config import DB_PATH as DEFAULT_DB

log = logging.getLogger(__name__)


VALID_STATES = {
    "QUEUED", "INGESTING", "INSPECTING", "TRANSCRIBING", "ANALYZING",
    "SCORING", "GENERATING", "EXPORTING", "VALIDATING",
    "COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED",
}

TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"}


@dataclass
class JobRecord:
    id: str
    state: str
    source_path: Optional[str]
    source_url: Optional[str]
    source_type: str
    config: dict
    progress: float
    stage: str
    message: str
    error: Optional[str]
    session_dir: Optional[str]
    output_dir: Optional[str]
    created_at: str
    updated_at: str


class JobManager:
    """Thread-safe job manager with SQLite persistence and WebSocket broadcast."""

    def __init__(self, db_path: pathlib.Path = DEFAULT_DB):
        self.db_path = db_path
        # WebSocket subscribers: job_id → list of asyncio.Queue
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        init_db(db_path)

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def create_job(
        self,
        source_path: Optional[str] = None,
        source_url: Optional[str] = None,
        source_type: str = "local",
        config: Optional[dict] = None,
    ) -> str:
        job_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        with get_db(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO jobs (id, created_at, updated_at, state, source_path,
                                  source_url, source_type, config_json)
                VALUES (?, ?, ?, 'QUEUED', ?, ?, ?, ?)
                """,
                (
                    job_id, now, now,
                    source_path, source_url, source_type,
                    json.dumps(config or {}),
                ),
            )
        log.info("Job created: %s (type=%s)", job_id, source_type)
        return job_id

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        with get_db(self.db_path) as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        d = row_to_dict(row)
        return JobRecord(
            id=d["id"],
            state=d["state"],
            source_path=d.get("source_path"),
            source_url=d.get("source_url"),
            source_type=d["source_type"],
            config=d.get("config_json", {}),
            progress=d["progress"],
            stage=d["stage"],
            message=d["message"],
            error=d.get("error"),
            session_dir=d.get("session_dir"),
            output_dir=d.get("output_dir"),
            created_at=d["created_at"],
            updated_at=d["updated_at"],
        )

    def list_jobs(self, limit: int = 50) -> list[JobRecord]:
        with get_db(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            JobRecord(
                id=d["id"], state=d["state"],
                source_path=d.get("source_path"), source_url=d.get("source_url"),
                source_type=d["source_type"], config=d.get("config_json", {}),
                progress=d["progress"], stage=d["stage"], message=d["message"],
                error=d.get("error"), session_dir=d.get("session_dir"),
                output_dir=d.get("output_dir"),
                created_at=d["created_at"], updated_at=d["updated_at"],
            )
            for d in [row_to_dict(r) for r in rows]
        ]

    def update_job(
        self,
        job_id: str,
        state: Optional[str] = None,
        progress: Optional[float] = None,
        stage: Optional[str] = None,
        message: Optional[str] = None,
        error: Optional[str] = None,
        session_dir: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        updates = ["updated_at = ?"]
        params: list[Any] = [now]

        if state is not None:
            if state not in VALID_STATES:
                raise ValueError(f"Invalid state: {state}")
            updates.append("state = ?")
            params.append(state)
        if progress is not None:
            updates.append("progress = ?")
            params.append(min(max(float(progress), 0.0), 1.0))
        if stage is not None:
            updates.append("stage = ?")
            params.append(stage)
        if message is not None:
            updates.append("message = ?")
            params.append(message)
        if error is not None:
            updates.append("error = ?")
            params.append(error)
        if session_dir is not None:
            updates.append("session_dir = ?")
            params.append(session_dir)
        if output_dir is not None:
            updates.append("output_dir = ?")
            params.append(output_dir)

        params.append(job_id)
        sql = f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?"
        with get_db(self.db_path) as conn:
            conn.execute(sql, params)

        # Broadcast progress to WebSocket subscribers
        update_msg = {
            "type": "progress",
            "job_id": job_id,
            "state": state,
            "progress": progress,
            "stage": stage,
            "message": message,
            "error": error,
            "timestamp": now,
        }
        self._broadcast(job_id, update_msg)

    def fail_job(self, job_id: str, error: str) -> None:
        log.error("Job %s FAILED: %s", job_id, error)
        self.update_job(job_id, state="FAILED", error=error, progress=0.0)

    def complete_job(self, job_id: str, output_dir: str) -> None:
        log.info("Job %s COMPLETED. Output: %s", job_id, output_dir)
        self.update_job(job_id, state="COMPLETED", progress=1.0, output_dir=output_dir)

    # ── Candidates ────────────────────────────────────────────────────────────

    def save_candidates(self, job_id: str, candidates: list[dict]) -> None:
        with get_db(self.db_path) as conn:
            # Clear existing
            conn.execute("DELETE FROM candidates WHERE job_id = ?", (job_id,))
            for cand in candidates:
                conn.execute(
                    """
                    INSERT INTO candidates (id, job_id, start_time, end_time, duration,
                        score, score_breakdown, warnings, transcript_text, rank)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cand["id"], job_id,
                        cand["start"], cand["end"], cand["duration"],
                        cand["score"],
                        json.dumps(cand.get("score_breakdown", {})),
                        json.dumps(cand.get("warnings", [])),
                        cand.get("transcript_text", ""),
                        cand.get("rank", 0),
                    ),
                )
        log.info("Saved %d candidates for job %s", len(candidates), job_id)

    def get_candidates(self, job_id: str) -> list[dict]:
        with get_db(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM candidates WHERE job_id = ? ORDER BY rank ASC",
                (job_id,),
            ).fetchall()
        return [row_to_dict(r) for r in rows]

    def update_candidate_export(self, candidate_id: str, export_path: str, validated: bool) -> None:
        with get_db(self.db_path) as conn:
            conn.execute(
                "UPDATE candidates SET export_path = ?, validated = ? WHERE id = ?",
                (export_path, 1 if validated else 0, candidate_id),
            )

    # ── WebSocket pub/sub ─────────────────────────────────────────────────────

    def subscribe(self, job_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.setdefault(job_id, []).append(q)
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue) -> None:
        if job_id in self._subscribers:
            try:
                self._subscribers[job_id].remove(q)
            except ValueError:
                pass

    def _broadcast(self, job_id: str, message: dict) -> None:
        for q in self._subscribers.get(job_id, []):
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                pass  # Drop if consumer is slow — never block the main thread

