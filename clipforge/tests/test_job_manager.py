"""
Tests for JobManager — state transitions, persistence, candidate storage.
"""

import pathlib
import tempfile
import pytest

from engine.database import init_db
from engine.job_manager import JobManager


@pytest.fixture
def db_path(tmp_path):
    p = tmp_path / "test_clipforge.db"
    init_db(p)
    return p


@pytest.fixture
def jm(db_path):
    return JobManager(db_path=db_path)


class TestJobManager:
    def test_create_job(self, jm):
        job_id = jm.create_job(source_path="/tmp/video.mp4", source_type="local")
        assert isinstance(job_id, str) and len(job_id) == 32

    def test_get_job_after_create(self, jm):
        job_id = jm.create_job(source_path="/tmp/video.mp4")
        job = jm.get_job(job_id)
        assert job is not None
        assert job.state == "QUEUED"
        assert job.source_path == "/tmp/video.mp4"

    def test_get_nonexistent_job(self, jm):
        assert jm.get_job("nonexistent") is None

    def test_update_job_state(self, jm):
        job_id = jm.create_job(source_path="/tmp/v.mp4")
        jm.update_job(job_id, state="TRANSCRIBING", progress=0.3, stage="Transcribing", message="50%")
        job = jm.get_job(job_id)
        assert job.state == "TRANSCRIBING"
        assert abs(job.progress - 0.3) < 0.001
        assert job.stage == "Transcribing"

    def test_invalid_state_raises(self, jm):
        job_id = jm.create_job(source_path="/tmp/v.mp4")
        with pytest.raises(ValueError, match="Invalid state"):
            jm.update_job(job_id, state="BOGUS_STATE")

    def test_fail_job(self, jm):
        job_id = jm.create_job(source_path="/tmp/v.mp4")
        jm.fail_job(job_id, "Something went wrong")
        job = jm.get_job(job_id)
        assert job.state == "FAILED"
        assert "Something went wrong" in job.error

    def test_complete_job(self, jm):
        job_id = jm.create_job(source_path="/tmp/v.mp4")
        jm.complete_job(job_id, "/output/dir")
        job = jm.get_job(job_id)
        assert job.state == "COMPLETED"
        assert job.progress == 1.0
        assert job.output_dir == "/output/dir"

    def test_list_jobs(self, jm):
        id1 = jm.create_job(source_path="/tmp/a.mp4")
        id2 = jm.create_job(source_path="/tmp/b.mp4")
        jobs = jm.list_jobs()
        ids = [j.id for j in jobs]
        assert id1 in ids
        assert id2 in ids

    def test_save_and_get_candidates(self, jm):
        job_id = jm.create_job(source_path="/tmp/v.mp4")
        candidates = [
            {
                "id": "cand001", "start": 10.0, "end": 70.0, "duration": 60.0,
                "score": 0.75, "score_breakdown": {"keyword": 0.8},
                "warnings": [], "transcript_text": "Hello world", "rank": 1,
            },
            {
                "id": "cand002", "start": 120.0, "end": 180.0, "duration": 60.0,
                "score": 0.55, "score_breakdown": {"keyword": 0.6},
                "warnings": [], "transcript_text": "Another clip", "rank": 2,
            },
        ]
        jm.save_candidates(job_id, candidates)
        retrieved = jm.get_candidates(job_id)
        assert len(retrieved) == 2
        assert retrieved[0]["id"] == "cand001"

    def test_update_candidate_export(self, jm):
        job_id = jm.create_job(source_path="/tmp/v.mp4")
        jm.save_candidates(job_id, [{
            "id": "c1", "start": 0.0, "end": 60.0, "duration": 60.0,
            "score": 0.7, "score_breakdown": {}, "warnings": [],
            "transcript_text": "text", "rank": 1,
        }])
        jm.update_candidate_export("c1", "/output/clip_c1.mp4", validated=True)
        cands = jm.get_candidates(job_id)
        assert cands[0]["export_path"] == "/output/clip_c1.mp4"
        assert cands[0]["validated"] == 1

    def test_persistence_across_instances(self, db_path):
        """Job data must survive creating a new JobManager instance (SQLite persistence)."""
        jm1 = JobManager(db_path=db_path)
        job_id = jm1.create_job(source_path="/tmp/persist.mp4")
        jm1.update_job(job_id, state="TRANSCRIBING", message="In progress")

        jm2 = JobManager(db_path=db_path)
        job = jm2.get_job(job_id)
        assert job is not None
        assert job.state == "TRANSCRIBING"
        assert job.message == "In progress"

