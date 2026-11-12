"""SQLite persistence. Connections are short-lived and owned by the caller's thread."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import json
import hashlib
from uuid import uuid4
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
CREATE TABLE IF NOT EXISTS render_attempts (
 id TEXT PRIMARY KEY, mix_id TEXT NOT NULL, revision INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('running','succeeded','failed')),
 snapshot_json TEXT NOT NULL, report_json TEXT, error TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(mix_id, revision) REFERENCES plans(mix_id, revision)
);
CREATE TABLE IF NOT EXISTS timelines (
 id TEXT PRIMARY KEY, content_hash TEXT NOT NULL, config_json TEXT NOT NULL,
 prediction_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS track_timelines (
 track_id TEXT NOT NULL REFERENCES tracks(id), timeline_id TEXT NOT NULL REFERENCES timelines(id),
 PRIMARY KEY(track_id,timeline_id)
);
CREATE TABLE IF NOT EXISTS timeline_corrections (
 timeline_id TEXT NOT NULL REFERENCES timelines(id), revision INTEGER NOT NULL,
 changes_json TEXT NOT NULL, note TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(timeline_id,revision)
);
CREATE TABLE IF NOT EXISTS transition_candidates (
 id TEXT PRIMARY KEY, pair_key TEXT NOT NULL, snapshot_json TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS candidate_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id TEXT NOT NULL REFERENCES transition_candidates(id),
 kind TEXT NOT NULL CHECK(kind IN ('validated','rejected','audition')),
 payload_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS reference_imports (
 id TEXT PRIMARY KEY, snapshot_json TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS reference_alignments (
 id TEXT PRIMARY KEY, reference_id TEXT NOT NULL REFERENCES reference_imports(id),
 snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS reference_annotations (
 reference_id TEXT NOT NULL REFERENCES reference_imports(id), revision INTEGER NOT NULL,
 annotation_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(reference_id, revision)
);
CREATE TABLE IF NOT EXISTS reference_transition_drafts (
 id TEXT PRIMARY KEY, reference_id TEXT NOT NULL REFERENCES reference_imports(id),
 alignment_id TEXT NOT NULL REFERENCES reference_alignments(id), snapshot_json TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS reference_transition_reviews (
 draft_id TEXT NOT NULL REFERENCES reference_transition_drafts(id), position INTEGER NOT NULL,
 revision INTEGER NOT NULL, review_json TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(draft_id,position,revision)
);
CREATE TABLE IF NOT EXISTS workflow_jobs (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('train','test_mix','transition_analysis','pair_audition','join_preview')),
 request_key TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed','interrupted','cancelled','needs_review')),
 payload_json TEXT NOT NULL, result_json TEXT, error TEXT, stage TEXT NOT NULL DEFAULT 'Queued',
 progress REAL NOT NULL DEFAULT 0, cancel_requested INTEGER NOT NULL DEFAULT 0,
 owner TEXT, heartbeat REAL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 finished_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS workflow_active_request ON workflow_jobs(request_key)
 WHERE status IN ('queued','running');
CREATE TABLE IF NOT EXISTS workflow_leases (
 name TEXT PRIMARY KEY, owner TEXT NOT NULL, expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS decision_models (
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES workflow_jobs(id),
 draft_id TEXT NOT NULL REFERENCES reference_transition_drafts(id),
 storage_name TEXT NOT NULL UNIQUE, manifest_json TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS transition_contexts (
 job_id TEXT PRIMARY KEY REFERENCES workflow_jobs(id), snapshot_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transition_reviews (
 job_id TEXT NOT NULL REFERENCES workflow_jobs(id), revision INTEGER NOT NULL,
 snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(job_id,revision)
);
CREATE TABLE IF NOT EXISTS improved_plans (
 job_id TEXT NOT NULL REFERENCES workflow_jobs(id), slot TEXT NOT NULL,
 plan_json TEXT NOT NULL, report_json TEXT NOT NULL, storage_name TEXT NOT NULL,
 audio_hash TEXT NOT NULL, PRIMARY KEY(job_id,slot)
);
CREATE TABLE IF NOT EXISTS improved_listening_reviews (
 job_id TEXT NOT NULL REFERENCES workflow_jobs(id), revision INTEGER NOT NULL,
 choice TEXT NOT NULL, notes TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(job_id,revision)
);
CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
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
            if version not in {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10}:
                raise RuntimeError("Unsupported database version")
            if 0 < version < 10 and connection.execute("SELECT 1 FROM sqlite_master WHERE name='workflow_jobs'").fetchone():
                # Rebuild only the CHECK constraint; retain IDs referenced by models.
                connection.execute('PRAGMA foreign_keys = OFF')
                definition = SCHEMA.split('CREATE TABLE IF NOT EXISTS workflow_jobs (', 1)[1].split(');', 1)[0]
                try:
                    connection.execute('BEGIN IMMEDIATE')
                    connection.execute('CREATE TABLE workflow_jobs_new ('+definition+');')
                    connection.execute('INSERT INTO workflow_jobs_new SELECT * FROM workflow_jobs')
                    connection.execute('DROP TABLE workflow_jobs')
                    connection.execute('ALTER TABLE workflow_jobs_new RENAME TO workflow_jobs')
                    if connection.execute('PRAGMA foreign_key_check').fetchone():
                        raise RuntimeError('Workflow migration failed referential integrity check')
                    connection.execute('PRAGMA user_version = 10')
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                finally:
                    connection.execute('PRAGMA foreign_keys = ON')
            connection.executescript(SCHEMA)
            connection.execute("PRAGMA user_version = 10")

    def register_plan(self, entries, plan):
        """Register members and their initial plan in one transaction."""
        payload = plan.to_json()
        ids = [entry['entry_id'] for entry in entries]
        if len(ids) != len(set(ids)) or set(ids) != {e.track_id for e in plan.excerpts}:
            raise ValueError('Plan must include every input entry exactly once')
        if plan.revision != 1:
            raise ValueError('Initial plan must be revision one')
        with self.connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            connection.execute('INSERT INTO mixes(id,requested_revision) VALUES (?,1)', (plan.mix_id,))
            for position, entry in enumerate(entries):
                identity = entry['entry_id']
                content_hash = entry['analysis']['content_hash']
                metadata = json.dumps({'external_path': str(Path(entry['path']).resolve())})
                old = connection.execute('SELECT content_hash,metadata_json FROM tracks WHERE id=?', (identity,)).fetchone()
                if old and (old['content_hash'] != content_hash or old['metadata_json'] != metadata):
                    raise ValueError('Track entry identity conflicts with an existing source')
                connection.execute('INSERT OR IGNORE INTO tracks(id,content_hash,original_name,storage_name,metadata_json) VALUES (?,?,?,?,?)',
                                   (identity, content_hash, Path(entry['path']).name, 'external:'+identity, metadata))
                connection.execute('INSERT INTO mix_tracks VALUES (?,?,?)', (plan.mix_id, identity, position))
                analysis = entry['analysis']
                rhythm = analysis.get('rhythm', {})
                if 'version' in analysis and 'version' in rhythm and 'config' in analysis:
                    connection.execute('INSERT OR REPLACE INTO analyses VALUES (?,?,?,?,?)',
                                       (content_hash, analysis['version']+'+'+rhythm['version'],
                                        hashlib.sha256(analysis['config'].encode()).hexdigest(),
                                        json.dumps(analysis, allow_nan=False), min(1, max(0, rhythm['confidence']))))
            connection.execute('INSERT INTO plans VALUES (?,?,?)', (plan.mix_id, 1, payload))

    def begin_render(self, plan, provenance):
        snapshot = json.dumps({'plan': json.loads(plan.to_json()), 'provenance': provenance}, allow_nan=False, sort_keys=True)
        identity = uuid4().hex
        with self.connection() as connection:
            saved = connection.execute('SELECT plan_json FROM plans WHERE mix_id=? AND revision=?', (plan.mix_id, plan.revision)).fetchone()
            if saved is None or saved[0] != plan.to_json():
                raise ValueError('Render must use the saved immutable plan')
            connection.execute('INSERT INTO render_attempts(id,mix_id,revision,status,snapshot_json) VALUES (?,?,?,?,?)',
                               (identity, plan.mix_id, plan.revision, 'running', snapshot))
        return identity

    def fail_render(self, attempt_id, error):
        with self.connection() as connection:
            cursor = connection.execute("UPDATE render_attempts SET status='failed',error=? WHERE id=? AND status='running'", (str(error), attempt_id))
            if cursor.rowcount != 1:
                raise ValueError('Render attempt is missing or already finished')

    def finish_render(self, attempt_id, storage_name, report):
        """Publish only current revisions; older completions remain in history."""
        payload = json.dumps(report, allow_nan=False, sort_keys=True)
        with self.connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            attempt = connection.execute('SELECT * FROM render_attempts WHERE id=?', (attempt_id,)).fetchone()
            if attempt is None or attempt['status'] != 'running':
                raise ValueError('Render attempt is missing or already finished')
            current = connection.execute('SELECT requested_revision FROM mixes WHERE id=?', (attempt['mix_id'],)).fetchone()[0]
            published = current == attempt['revision'] and connection.execute('SELECT 1 FROM renders WHERE mix_id=? AND revision=?', (attempt['mix_id'], current)).fetchone() is None
            if published:
                connection.execute('INSERT INTO renders VALUES (?,?,?,?)', (attempt['mix_id'], current, storage_name, payload))
                connection.execute('UPDATE mixes SET playable_revision=? WHERE id=?', (current, attempt['mix_id']))
            connection.execute("UPDATE render_attempts SET status='succeeded',report_json=? WHERE id=?", (payload, attempt_id))
        return published

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
