"""
Tests for WorkspaceManager and CleanupManager.
"""

import json
import pathlib
import tempfile
import pytest

from engine.workspace_manager import WorkspaceManager, Session
from engine.cleanup_manager import CleanupManager


@pytest.fixture
def temp_root(tmp_path):
    return tmp_path / "clipforge_sessions"


@pytest.fixture
def workspace(temp_root):
    return WorkspaceManager(temp_root=temp_root)


@pytest.fixture
def cleanup(temp_root):
    return CleanupManager(temp_root=temp_root)


class TestWorkspaceManager:
    def test_create_session(self, workspace):
        session = workspace.create_session("job-abc123")
        assert session.session_dir.is_dir()
        assert session.source_dir.is_dir()
        assert session.audio_dir.is_dir()
        assert session.renders_dir.is_dir()
        assert session.manifest_path.exists()

    def test_manifest_has_correct_fields(self, workspace):
        session = workspace.create_session("job-xyz", source_info={"type": "local"})
        manifest = session.read_manifest()
        assert manifest["job_id"] == "job-xyz"
        assert manifest["status"] == "active"
        assert "created_at" in manifest
        assert manifest["source"]["type"] == "local"

    def test_get_session_by_id(self, workspace):
        session = workspace.create_session("job-get")
        found = workspace.get_session(session.session_id)
        assert found is not None
        assert found.session_id == session.session_id

    def test_get_nonexistent_session(self, workspace):
        assert workspace.get_session("does-not-exist") is None

    def test_get_session_by_job(self, workspace):
        session = workspace.create_session("job-byjob")
        found = workspace.get_session_by_job("job-byjob")
        assert found is not None
        assert found.session_id == session.session_id

    def test_list_active_sessions(self, workspace):
        s1 = workspace.create_session("job-1")
        s2 = workspace.create_session("job-2")
        active = workspace.list_active_sessions()
        ids = [s.session_id for s in active]
        assert s1.session_id in ids
        assert s2.session_id in ids

    def test_mark_finalized(self, workspace):
        session = workspace.create_session("job-final")
        workspace.mark_finalized(session)
        manifest = session.read_manifest()
        assert manifest["status"] == "finalized"

    def test_mark_failed(self, workspace):
        session = workspace.create_session("job-fail")
        workspace.mark_failed(session, "test error")
        manifest = session.read_manifest()
        assert manifest["status"] == "failed"
        assert manifest["error"] == "test error"


class TestCleanupManager:
    def test_refuses_unsafe_path(self, cleanup, tmp_path):
        # Create a fake session outside the temp root
        class FakeSession:
            session_id = "fake"
            session_dir = tmp_path / "outside"
            manifest_path = session_dir / "manifest.json"
            def read_manifest(self): return {}
            def update_manifest(self, **kwargs): pass

        result = cleanup.cleanup_session(FakeSession())  # type: ignore
        assert len(result["errors"]) > 0

    def test_cleanup_removes_audio_dir(self, cleanup, workspace):
        session = workspace.create_session("job-clean", source_info={"type": "local"})
        # Write a dummy file
        (session.audio_dir / "audio.wav").write_bytes(b"data")
        result = cleanup.cleanup_session(session, youtube_only=True)
        # audio/ should be removed (always cleaned)
        assert not session.audio_dir.exists()

    def test_cleanup_preserves_source_for_local(self, cleanup, workspace):
        session = workspace.create_session("job-local-clean", source_info={"type": "local"})
        (session.source_dir / "video.mp4").write_bytes(b"fake")
        result = cleanup.cleanup_session(session, youtube_only=True)
        # source/ should NOT be removed for local files
        assert session.source_dir.exists()

    def test_cleanup_removes_source_for_youtube(self, cleanup, workspace):
        session = workspace.create_session("job-yt-clean", source_info={"type": "youtube"})
        (session.source_dir / "downloaded.mp4").write_bytes(b"fake")
        result = cleanup.cleanup_session(session, youtube_only=True)
        # source/ SHOULD be removed for YouTube downloads
        assert not session.source_dir.exists()

    def test_recover_abandoned_sessions(self, cleanup, workspace):
        s1 = workspace.create_session("job-abandoned-1")
        s2 = workspace.create_session("job-abandoned-2")
        workspace.mark_finalized(s2)  # s2 is finalized, not abandoned
        recovered = cleanup.recover_abandoned_sessions()
        assert s1.session_id in recovered
        assert s2.session_id not in recovered
        # s1 should now be "interrupted"
        assert s1.read_manifest()["status"] == "interrupted"

