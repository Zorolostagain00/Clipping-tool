"""
Workspace manager — creates and tracks temporary session directories.

Each job gets an isolated session directory inside OS temp:
  %TEMP%/ClipForge/sessions/session_<uuid>/
    source/     — downloaded or symlinked source video
    audio/      — extracted audio for transcription
    proxies/    — low-res proxies for preview
    frames/     — sampled frames for visual analysis
    analysis/   — JSON analysis artefacts
    renders/    — exported clip renders (moved to output/ on success)
    manifest.json

Workspace cleanup is handled by CleanupManager; this module only creates
and tracks sessions.
"""

import json
import pathlib
import shutil
import uuid
from datetime import datetime, timezone
from typing import Optional

from engine.config import TEMP_ROOT


SESSION_SUBDIRS = ["source", "audio", "proxies", "frames", "analysis", "renders"]


class WorkspaceError(Exception):
    pass


class Session:
    """Represents one processing session's directory structure."""

    def __init__(self, session_id: str, session_dir: pathlib.Path):
        self.session_id = session_id
        self.session_dir = session_dir

    # Convenience paths
    @property
    def source_dir(self) -> pathlib.Path:
        return self.session_dir / "source"

    @property
    def audio_dir(self) -> pathlib.Path:
        return self.session_dir / "audio"

    @property
    def proxies_dir(self) -> pathlib.Path:
        return self.session_dir / "proxies"

    @property
    def frames_dir(self) -> pathlib.Path:
        return self.session_dir / "frames"

    @property
    def analysis_dir(self) -> pathlib.Path:
        return self.session_dir / "analysis"

    @property
    def renders_dir(self) -> pathlib.Path:
        return self.session_dir / "renders"

    @property
    def manifest_path(self) -> pathlib.Path:
        return self.session_dir / "manifest.json"

    def read_manifest(self) -> dict:
        if not self.manifest_path.exists():
            return {}
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def write_manifest(self, data: dict) -> None:
        self.manifest_path.write_text(
            json.dumps(data, indent=2, default=str), encoding="utf-8"
        )

    def update_manifest(self, **kwargs) -> None:
        manifest = self.read_manifest()
        manifest.update(kwargs)
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.write_manifest(manifest)

    def __repr__(self) -> str:
        return f"<Session {self.session_id} @ {self.session_dir}>"


class WorkspaceManager:
    """Creates and tracks ClipForge processing sessions."""

    def __init__(self, temp_root: pathlib.Path = TEMP_ROOT):
        self.temp_root = temp_root
        self.temp_root.mkdir(parents=True, exist_ok=True)

    def create_session(self, job_id: str, source_info: Optional[dict] = None) -> Session:
        """Create a fresh session directory for a job."""
        session_id = f"session_{uuid.uuid4().hex[:12]}"
        session_dir = self.temp_root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        for sub in SESSION_SUBDIRS:
            (session_dir / sub).mkdir(exist_ok=True)

        manifest = {
            "session_id": session_id,
            "job_id": job_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "active",
            "source": source_info or {},
        }
        session = Session(session_id, session_dir)
        session.write_manifest(manifest)
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Return an existing session by ID, or None if it does not exist."""
        session_dir = self.temp_root / session_id
        if not session_dir.is_dir():
            return None
        return Session(session_id, session_dir)

    def get_session_by_job(self, job_id: str) -> Optional[Session]:
        """Find a session belonging to the given job_id by scanning manifests."""
        for d in self.temp_root.iterdir():
            if not d.is_dir():
                continue
            manifest_path = d / "manifest.json"
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    if manifest.get("job_id") == job_id:
                        return Session(d.name, d)
                except Exception:
                    continue
        return None

    def list_active_sessions(self) -> list[Session]:
        """Return all sessions that have status 'active'."""
        sessions = []
        for d in self.temp_root.iterdir():
            if not d.is_dir():
                continue
            manifest_path = d / "manifest.json"
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    if manifest.get("status") == "active":
                        sessions.append(Session(d.name, d))
                except Exception:
                    continue
        return sessions

    def mark_finalized(self, session: Session) -> None:
        """Mark session as finalized (ready for cleanup)."""
        session.update_manifest(status="finalized")

    def mark_failed(self, session: Session, reason: str = "") -> None:
        """Mark session as failed."""
        session.update_manifest(status="failed", error=reason)

