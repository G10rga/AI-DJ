"""SQLite persistence. Connections are short-lived and owned by the caller's thread."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from .models import MixPlan

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
 id TEXT PRIMARY KEY, content_hash TEXT NOT NULL, original_name TEXT NOT NULL,
 storage_name TEXT NOT NULL UNIQUE, metadata_json TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS analyses (
 content_hash TEXT NOT NULL, version TEXT NOT NULL, config_hash TEXT NOT NULL,
 result_json TEXT NOT NULL, confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
 PRIMARY KEY(content_hash, version, config_hash)
);
CREATE TABLE IF NOT EXISTS mixes (
 id TEXT PRIMARY KEY, requested_revision INTEGER NOT NULL DEFAULT 0,
 playable_revision INTEGER
);
CREATE TABLE IF NOT EXISTS mix_tracks (
 mix_id TEXT NOT NULL REFERENCES mixes(id), track_id TEXT NOT NULL REFERENCES tracks(id),
 position INTEGER NOT NULL CHECK(position >= 0),
 PRIMARY KEY(mix_id, track_id), UNIQUE(mix_id, position)
);
CREATE TABLE IF NOT EXISTS plans (
 mix_id TEXT NOT NULL REFERENCES mixes(id), revision INTEGER NOT NULL CHECK(revision > 0),
 plan_json TEXT NOT NULL, PRIMARY KEY(mix_id, revision)
);
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, mix_id TEXT NOT NULL REFERENCES mixes(id), revision INTEGER,
 stage TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed','interrupted')),
 progress REAL NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 1), error TEXT,
 heartbeat_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS renders (
 mix_id TEXT NOT NULL, revision INTEGER NOT NULL, storage_name TEXT NOT NULL UNIQUE,
 metadata_json TEXT NOT NULL,
 PRIMARY KEY(mix_id, revision), FOREIGN KEY(mix_id, revision) REFERENCES plans(mix_id, revision)
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 1}:
                raise RuntimeError("Unsupported database version")
            connection.executescript(SCHEMA)
            connection.execute("PRAGMA user_version = 1")

    def save_plan(self, plan: MixPlan):
        payload = plan.to_json()
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            mix = connection.execute("SELECT requested_revision FROM mixes WHERE id=?", (plan.mix_id,)).fetchone()
            if mix is None:
                raise ValueError("Unknown mix")
            members = {r[0] for r in connection.execute("SELECT track_id FROM mix_tracks WHERE mix_id=?", (plan.mix_id,))}
            if members != {e.track_id for e in plan.excerpts}:
                raise ValueError("Plan must include every mix member exactly once")
            if plan.revision != mix[0] + 1:
                raise ValueError("Plan revision is stale or skips a revision")
            connection.execute("INSERT INTO plans VALUES (?, ?, ?)", (plan.mix_id, plan.revision, payload))
            connection.execute("UPDATE mixes SET requested_revision=? WHERE id=?", (plan.revision, plan.mix_id))

    def load_plan(self, mix_id: str, revision: int) -> MixPlan:
        with self.connection() as connection:
            row = connection.execute("SELECT plan_json FROM plans WHERE mix_id=? AND revision=?", (mix_id, revision)).fetchone()
        if row is None:
            raise KeyError((mix_id, revision))
        return MixPlan.from_json(row[0])
