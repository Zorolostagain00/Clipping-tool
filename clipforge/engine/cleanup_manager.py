"""
CleanupManager — safely removes ClipForge-owned temporary session directories.

Key guarantees:
- Never deletes paths outside TEMP_ROOT.
- Handles Windows file locks with retry + backoff.
- On startup, recovers abandoned sessions (status != 'active').
- Only clears YouTube-sourced downloads; local files are never touched.
"""

import json
import logging
import pathlib
import shutil
import time
from typing import Optional

from engine.config import TEMP_ROOT
from engine.workspace_manager import WorkspaceManager, Session

log = logging.getLogger(__name__)


class CleanupManager:
    def __init__(self, temp_root: pathlib.Path = TEMP_ROOT):
        self.temp_root = temp_root.resolve()
        self.workspace = WorkspaceManager(temp_root)

    def _safe_path(self, path: pathlib.Path) -> bool:
        """Return True only if path is safely inside our temp root."""
        try:
            path.resolve().relative_to(self.temp_root)
            return True
        except ValueError:
            return False

    def _remove_with_retry(self, path: pathlib.Path, retries: int = 5, delay: float = 1.0) -> bool:
        """Attempt to remove a file or directory tree, retrying on Windows lock errors."""
        for attempt in range(retries):
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                elif path.exists():
                    path.unlink()
                return True
            except PermissionError as e:
                if attempt < retries - 1:
                    log.warning("File locked (%s), retry %d/%d in %.1fs", path, attempt + 1, retries, delay)
                    time.sleep(delay)
                    delay *= 1.5
                else:
                    log.error("Could not remove %s after %d retries: %s", path, retries, e)
                    return False
            except FileNotFoundError:
                return True  # Already gone — success
        return False

    def cleanup_session(self, session: Session, youtube_only: bool = True) -> dict:
        """
        Remove temp files for a session.

        Args:
            session: Session object to clean.
            youtube_only: If True, only remove the source/ dir if the source
                          was a YouTube download. Always removes audio/, proxies/,
                          frames/, analysis/ dirs.
        Returns:
            dict with 'removed', 'skipped', 'errors' lists.
        """
        result = {"removed": [], "skipped": [], "errors": []}

        if not self._safe_path(session.session_dir):
            log.error("Refusing to clean unsafe path: %s", session.session_dir)
            result["errors"].append(str(session.session_dir))
            return result

        manifest = session.read_manifest()
        source_type = manifest.get("source", {}).get("type", "local")

        # Directories that are always cleaned
        always_clean = ["audio", "proxies", "frames", "analysis"]
        # Source only cleaned for YouTube downloads (local files are user's)
        if source_type == "youtube":
            always_clean.append("source")

        for sub in always_clean:
            sub_path = session.session_dir / sub
            if sub_path.exists():
                ok = self._remove_with_retry(sub_path)
                if ok:
                    result["removed"].append(str(sub_path))
                else:
                    result["errors"].append(str(sub_path))

        # After cleanup, mark session cleaned in manifest
        try:
            session.update_manifest(status="cleaned")
        except Exception:
            pass

        return result

    def cleanup_session_fully(self, session: Session) -> dict:
        """Remove the entire session directory (including renders)."""
        result = {"removed": [], "skipped": [], "errors": []}
        if not self._safe_path(session.session_dir):
            log.error("Refusing to clean unsafe path: %s", session.session_dir)
            result["errors"].append(str(session.session_dir))
            return result
        ok = self._remove_with_retry(session.session_dir)
        if ok:
            result["removed"].append(str(session.session_dir))
        else:
            result["errors"].append(str(session.session_dir))
        return result

    def recover_abandoned_sessions(self) -> list[str]:
        """
        Called on startup — finds sessions that were interrupted (status == 'active')
        and marks them as 'interrupted' so they can be reviewed or cleaned.
        Returns list of recovered session IDs.
        """
        recovered = []
        for session in self.workspace.list_active_sessions():
            session.update_manifest(status="interrupted")
            log.info("Marked abandoned session as interrupted: %s", session.session_id)
            recovered.append(session.session_id)
        return recovered

