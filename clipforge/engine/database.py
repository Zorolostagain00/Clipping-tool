"""
SQLite schema and connection management for ClipForge Studio.
All persistent state (jobs, projects, candidates, transcript cache index)
lives in a single SQLite file at config.DB_PATH.
"""

import sqlite3
import contextlib
import json
import pathlib
from typing import Generator

from engine.config import DB_PATH


# ── Schema ─────────────────────────────────────────────────────────────────
_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS jobs (
    id              TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    state           TEXT NOT NULL DEFAULT 'QUEUED',
    source_path     TEXT,
    source_url      TEXT,
    source_type     TEXT NOT NULL DEFAULT 'local',   -- local | youtube
    config_json     TEXT NOT NULL DEFAULT '{}',
    progress        REAL NOT NULL DEFAULT 0.0,
    stage           TEXT NOT NULL DEFAULT '',
    message         TEXT NOT NULL DEFAULT '',
    error           TEXT,
    session_dir     TEXT,
    output_dir      TEXT
);

CREATE TABLE IF NOT EXISTS candidates (
    id              TEXT PRIMARY KEY,
    job_id          TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    start_time      REAL NOT NULL,
    end_time        REAL NOT NULL,
    duration        REAL NOT NULL,
    score           REAL NOT NULL DEFAULT 0.0,
    score_breakdown TEXT NOT NULL DEFAULT '{}',
    warnings        TEXT NOT NULL DEFAULT '[]',
    transcript_text TEXT,
    export_path     TEXT,
    validated       INTEGER NOT NULL DEFAULT 0,
    selected        INTEGER NOT NULL DEFAULT 1,
    rank            INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transcript_cache (
    cache_key       TEXT PRIMARY KEY,
    job_id          TEXT REFERENCES jobs(id) ON DELETE SET NULL,
    model_id        TEXT NOT NULL,
    language        TEXT,
    created_at      TEXT NOT NULL,
    cache_path      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_candidates_job ON candidates(job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_state    ON jobs(state);
"""


def get_connection(db_path: pathlib.Path = DB_PATH) -> sqlite3.Connection:
    """Return a raw sqlite3 connection with row_factory set."""
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextlib.contextmanager
def get_db(db_path: pathlib.Path = DB_PATH) -> Generator[sqlite3.Connection, None, None]:
    """Context manager yielding an open, auto-committing sqlite3 connection."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: pathlib.Path = DB_PATH) -> None:
    """Create tables and indexes if they do not exist."""
    with get_db(db_path) as conn:
        conn.executescript(_SCHEMA)


def row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a plain dict, deserializing JSON fields."""
    d = dict(row)
    for key in ("config_json", "score_breakdown", "warnings"):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return d

