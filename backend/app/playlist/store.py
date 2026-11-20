"""Revisioned projects; old artifacts survive edits and stale workers cannot publish."""
from copy import deepcopy
from functools import lru_cache
import json
import math
from pathlib import Path
from uuid import uuid4
from . import PIPELINE
from .planner import BARS, PRESETS, validate_automation
from ..timelines import canonical

SCHEMA = '''
CREATE TABLE IF NOT EXISTS playlist_projects (
 id TEXT PRIMARY KEY, revision INTEGER NOT NULL, snapshot TEXT NOT NULL,
 playable_job TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS playlist_revisions (
 project_id TEXT NOT NULL, revision INTEGER NOT NULL, snapshot TEXT NOT NULL,
 PRIMARY KEY(project_id, revision));
CREATE TABLE IF NOT EXISTS playlist_plans (
 job_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, revision INTEGER NOT NULL,
 plan_json TEXT NOT NULL, result_json TEXT NOT NULL);
'''


@lru_cache(maxsize=256)
def artifact_digest(path, size, modified_ns):
    from scripts.setup_timeline import sha256
    return sha256(path)


class Projects:
    def __init__(self, workflow):
        self.workflow = workflow; self.db = workflow.db
        with self.db.connection() as c: c.executescript(SCHEMA)

    def sources(self, ids):
        if not isinstance(ids, list) or not 1 <= len(ids) <= 50 or any(not isinstance(i, str) for i in ids):
            raise ValueError('Choose 1–50 songs')
        catalog = {s['id']: s for s in self.workflow.catalog(internal=True)}
        if any(i not in catalog for i in ids): raise ValueError('A selected song is unavailable')
        return [catalog[i] for i in ids]

    def create(self, ids, name='Untitled playlist'):
        sources = self.sources(ids)
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 160:
            raise ValueError('Use a playlist name of 1–160 characters')
        p = {'id': uuid4().hex, 'revision': 1, 'name': name.strip(), 'pipeline': PIPELINE,
             'sources': sources, 'transitions': {}, 'grids': {}}
        with self.db.connection() as c:
            c.execute('INSERT INTO playlist_projects(id,revision,snapshot) VALUES (?,?,?)', (p['id'], 1, canonical(p)))
            c.execute('INSERT INTO playlist_revisions VALUES (?,?,?)', (p['id'], 1, canonical(p)))
        return self.get(p['id'])

    def get(self, identity, internal=False):
        with self.db.connection() as c:
            row = c.execute('SELECT * FROM playlist_projects WHERE id=?', (identity,)).fetchone()
            if row is None: raise KeyError(identity)
            p = json.loads(row['snapshot'])
            if internal:
                return p
            jobs = [r[0] for r in c.execute("SELECT id FROM workflow_jobs WHERE json_extract(payload_json,'$.project_id')=? ORDER BY rowid DESC LIMIT 15", (identity,))]
        p['sources'] = [{k: v for k, v in s.items() if k != 'path'} for s in p['sources']]
        p['jobs'] = [self.workflow.job(j) for j in jobs]
        p['playable_job'] = row['playable_job']
        p['playable'] = self.workflow.job(row['playable_job'])['result'] if row['playable_job'] else None
        return p

    def list(self):
        with self.db.connection() as c:
            return [dict(r) for r in c.execute("SELECT id,revision,json_extract(snapshot,'$.name') AS name FROM playlist_projects ORDER BY rowid DESC")]

    def mutate(self, identity, expected, action, value):
        with self.db.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT revision,snapshot FROM playlist_projects WHERE id=?', (identity,)).fetchone()
            if row is None: raise KeyError(identity)
            if type(expected) is not int or row['revision'] != expected:
                raise ValueError('Project changed; reload before saving')
            p = json.loads(row['snapshot'])
            if action == 'update':
                if 'track_ids' in value:
                    p['sources'] = self.sources(value['track_ids']); p['transitions'] = {}
                if 'name' in value:
                    if not isinstance(value['name'], str) or not 1 <= len(value['name'].strip()) <= 160:
                        raise ValueError('Use a playlist name of 1–160 characters')
                    p['name'] = value['name'].strip()
            elif action in ('transition', 'reset'):
                index = value.get('index')
                if type(index) is not int or not 0 <= index < len(p['sources'])-1:
                    raise ValueError('Choose an existing transition')
                if action == 'reset': p['transitions'].pop(str(index), None)
                else:
                    edit = value.get('settings')
                    if not isinstance(edit, dict) or set(edit)-{'a_cue', 'b_cue', 'bars', 'preset', 'automation', 'vocal_ending'}:
                        raise ValueError('Unknown transition setting')
                    if 'bars' in edit and (type(edit['bars']) is not int or edit['bars'] not in BARS):
                        raise ValueError('Choose 2, 4, 8, 16 or 32 bars')
                    if 'preset' in edit and edit['preset'] not in PRESETS: raise ValueError('Unknown preset')
                    for k in ('a_cue', 'b_cue', 'vocal_ending'):
                        if k in edit and (type(edit[k]) not in (int, float) or not math.isfinite(edit[k]) or edit[k] < 0):
                            raise ValueError('Cue times must be finite and nonnegative')
                    if 'automation' in edit: validate_automation(edit['automation'])
                    p['transitions'][str(index)] = deepcopy(edit)
            elif action == 'grid':
                index = value.get('index'); grid = value.get('grid')
                if type(index) is not int or not 0 <= index < len(p['sources']): raise ValueError('Choose an existing song')
                if not isinstance(grid, dict) or set(grid)-{'bpm', 'first_downbeat', 'bar_phase', 'anchors', 'vocal_ending', 'use_detected_intervals'}:
                    raise ValueError('Invalid grid correction')
                if type(grid.get('use_detected_intervals', False)) is not bool:
                    raise ValueError('Choose whether to retain detected beat intervals')
                for key, lo, hi in (('bpm', 30, 300), ('first_downbeat', 0, 1200)):
                    if type(grid.get(key)) not in (int, float) or not math.isfinite(grid[key]) or not lo <= grid[key] <= hi:
                        raise ValueError('Enter a valid BPM and first downbeat')
                if type(grid.get('bar_phase', 0)) is not int or grid.get('bar_phase', 0) not in range(4):
                    raise ValueError('Bar phase must be 0–3')
                anchors = grid.get('anchors', [])
                if not isinstance(anchors, list) or len(anchors) > 1000: raise ValueError('Invalid local anchors')
                last = [-1, -1]
                for point in anchors:
                    if (not isinstance(point, list) or len(point) != 2 or type(point[0]) is not int or
                        type(point[1]) not in (int, float) or not math.isfinite(point[1]) or
                        point[0] <= last[0] or point[1] <= last[1] or min(point) < 0):
                        raise ValueError('Local beat indices and source seconds must increase')
                    last = point
                if 'vocal_ending' in grid and (type(grid['vocal_ending']) not in (int, float) or
                     not math.isfinite(grid['vocal_ending']) or not 0 <= grid['vocal_ending'] <= 1200):
                    raise ValueError('Invalid vocal ending')
                p['grids'][p['sources'][index]['content_hash']] = deepcopy(grid)
            elif action == 'restore':
                revision = value.get('revision')
                old = c.execute('SELECT snapshot FROM playlist_revisions WHERE project_id=? AND revision=?', (identity, revision)).fetchone()
                if old is None: raise ValueError('Saved revision unavailable')
                p = json.loads(old[0])
            else: raise ValueError('Unknown project edit')
            p['revision'] = expected+1
            c.execute('UPDATE playlist_projects SET revision=?,snapshot=? WHERE id=?', (p['revision'], canonical(p), identity))
            c.execute('INSERT INTO playlist_revisions VALUES (?,?,?)', (identity, p['revision'], canonical(p)))
            # Running work is fenced at publication and can also stop early.
            c.execute("""UPDATE workflow_jobs SET cancel_requested=1
                WHERE status='running' AND json_extract(payload_json,'$.project_id')=?
                AND json_extract(payload_json,'$.project_revision')<?""", (identity, p['revision']))
            c.execute("""UPDATE workflow_jobs SET status='interrupted',stage='Superseded',
                finished_at=CURRENT_TIMESTAMP WHERE status='queued'
                AND json_extract(payload_json,'$.project_id')=?
                AND json_extract(payload_json,'$.project_revision')<?""", (identity, p['revision']))
        return self.get(identity)

    def enqueue(self, identity, expected, action='auto'):
        if action not in ('auto', 'preview', 'export', 'reorder'): raise ValueError('Unknown operation')
        p = self.get(identity, internal=True)
        if type(expected) is not int or p['revision'] != expected: raise ValueError('Project changed; reload before mixing')
        def check(c):
            current = c.execute('SELECT revision FROM playlist_projects WHERE id=?', (identity,)).fetchone()
            if current is None or current[0] != expected:
                raise ValueError('Project changed; reload before mixing')
        return self.workflow.enqueue('playlist', {'pipeline': PIPELINE, 'project_id': identity,
            'project_revision': expected, 'action': action, 'snapshot': p, 'sources': p['sources']}, precondition=check)

    def media(self, identity, job_id, name):
        job = self.workflow.job(job_id, internal=True)
        if job['payload'].get('project_id') != identity or job['status'] not in ('succeeded', 'needs_review'):
            raise KeyError(job_id)
        artifact = next((a for a in (job['result'] or {}).get('artifacts', []) if a['name'] == name), None)
        if artifact is None: raise KeyError(name)
        root = self.workflow.storage.root.resolve()
        path = (root/artifact['path']).resolve()
        if not path.is_relative_to(root) or not path.is_file(): raise KeyError(name)
        stat = path.stat()
        if artifact_digest(path, stat.st_size, stat.st_mtime_ns) != artifact['sha256']:
            raise ValueError('Prepared audio changed; regenerate it')
        return path

    def original(self, identity, index, revision=None):
        if revision is None:
            sources = self.get(identity, internal=True)['sources']
        else:
            with self.db.connection() as c:
                row = c.execute('SELECT snapshot FROM playlist_revisions WHERE project_id=? AND revision=?',
                                (identity, revision)).fetchone()
            if row is None:
                raise KeyError(revision)
            sources = json.loads(row[0])['sources']
        if not 0 <= index < len(sources):
            raise KeyError(index)
        source = sources[index]
        path = Path(source['path']).resolve()
        if not path.is_file():
            raise KeyError(index)
        stat = path.stat()
        if artifact_digest(path, stat.st_size, stat.st_mtime_ns) != source['content_hash']:
            raise ValueError('The original song changed; upload it again')
        return path, source['name']

    def cancel(self, identity, expected, job_id):
        with self.db.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            project = c.execute('SELECT revision FROM playlist_projects WHERE id=?', (identity,)).fetchone()
            if project is None:
                raise KeyError(identity)
            if type(expected) is not int or expected != project['revision']:
                raise ValueError('Project changed; reload before cancelling')
            job = c.execute("SELECT status FROM workflow_jobs WHERE id=? AND json_extract(payload_json,'$.project_id')=?",
                            (job_id, identity)).fetchone()
            if job is None:
                raise KeyError(job_id)
            if job['status'] == 'queued':
                c.execute("UPDATE workflow_jobs SET status='cancelled',stage='Cancelled',finished_at=CURRENT_TIMESTAMP WHERE id=?", (job_id,))
            elif job['status'] == 'running':
                c.execute('UPDATE workflow_jobs SET cancel_requested=1 WHERE id=?', (job_id,))
        return self.workflow.job(job_id)


def publish(connection, row, payload, result):
    """Called inside Workflow.finish's lease/cancellation transaction."""
    current = connection.execute('SELECT revision FROM playlist_projects WHERE id=?', (payload['project_id'],)).fetchone()
    if current is None or current[0] != payload['project_revision']: return False
    connection.execute('INSERT INTO playlist_plans VALUES (?,?,?,?,?)',
        (row['id'], payload['project_id'], current[0], canonical(result.get('plan')), canonical(result)))
    if result.get('status') == 'validated' and result.get('audio_url'):
        connection.execute('UPDATE playlist_projects SET playable_job=? WHERE id=?', (row['id'], payload['project_id']))
    return True
