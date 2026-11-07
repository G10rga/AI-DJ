"""Immutable proposal snapshots and append-only technical/audition evidence."""
import json
from pathlib import Path
from backend.app.db import Database
from backend.app.timelines import canonical
from .contextual import digest


class CandidateStore:
    def __init__(self, root):
        self.database = Database(Path(root)/'app.sqlite3')
        self.database.initialize()

    def register(self, candidate):
        snapshot = {k: v for k, v in candidate.items() if k != 'id'}
        if digest(snapshot)[:24] != candidate['id']:
            raise ValueError('Candidate snapshot differs from its immutable identity')
        payload = canonical(candidate)
        with self.database.connection() as c:
            old = c.execute('SELECT snapshot_json FROM transition_candidates WHERE id=?', (candidate['id'],)).fetchone()
            if old and old[0] != payload:
                raise ValueError('Candidate identity conflict')
            c.execute('INSERT OR IGNORE INTO transition_candidates(id,pair_key,snapshot_json) VALUES (?,?,?)',
                      (candidate['id'], candidate['pair_key'], payload))

    def event(self, candidate_id, kind, payload):
        if kind not in {'validated', 'rejected', 'audition'}:
            raise ValueError('Unknown candidate event')
        with self.database.connection() as c:
            c.execute('INSERT INTO candidate_events(candidate_id,kind,payload_json) VALUES (?,?,?)', (candidate_id, kind, canonical(payload)))

    def load(self, candidate_id):
        with self.database.connection() as c:
            row = c.execute('SELECT snapshot_json FROM transition_candidates WHERE id=?', (candidate_id,)).fetchone()
        if row is None:
            raise KeyError(candidate_id)
        return json.loads(row[0])

    def events(self, candidate_id):
        with self.database.connection() as c:
            return [dict(row) for row in c.execute('SELECT * FROM candidate_events WHERE candidate_id=? ORDER BY id', (candidate_id,))]
