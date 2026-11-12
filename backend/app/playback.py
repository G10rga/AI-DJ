"""Read-only listening catalog for validated mixes and rendered auditions."""
import json
import hashlib
from pathlib import Path
from .db import Database
from .storage import Storage
from .timelines import canonical

RECIPE_NAMES = {'controlled_16': '16-bar controlled blend', 'eq_8': '8-bar EQ handoff',
                'groove_32': '32-bar groove blend', 'phrase_cut': 'Phrase-aligned cut'}


class PlaybackLibrary:
    def __init__(self, root):
        self.storage = Storage(root)
        self.database = Database(Path(root)/'app.sqlite3')
        self.database.initialize()

    def media_path(self, storage_name):
        try:
            path = self.storage.path('renders', storage_name)
        except ValueError:
            raise KeyError('Invalid render filename')
        if not path.is_file():
            raise FileNotFoundError('Rendered audio is unavailable')
        return path

    def mixes(self):
        with self.database.connection() as c:
            rows = c.execute('''SELECT m.id,m.requested_revision,m.playable_revision,r.storage_name,r.metadata_json,
                (SELECT error FROM render_attempts a WHERE a.mix_id=m.id AND a.revision=m.requested_revision
                 AND a.status='failed' ORDER BY a.rowid DESC LIMIT 1) AS last_error
                FROM mixes m JOIN renders r ON r.mix_id=m.id AND r.revision=m.playable_revision
                ORDER BY r.rowid DESC LIMIT 50''').fetchall()
            track_rows = list(c.execute('SELECT id,original_name,content_hash FROM tracks'))
            names = {r['id']: r['original_name'] for r in track_rows}
            hashes = {r['id']: r['content_hash'] for r in track_rows}
        result = []
        for row in rows:
            report = json.loads(row['metadata_json'])
            plan = report.get('applied_plan', report.get('plan', {}))
            tracklist = report.get('tracks', [])
            if not tracklist and plan.get('excerpts'):
                position = 0.
                tracklist = []
                for i, cue in enumerate(plan['excerpts']):
                    duration = (cue['source_out']-cue['source_in'])*cue['source_bpm']/cue['target_bpm']
                    tracklist.append({'name': names.get(cue['track_id'], cue['track_id']),
                                      'start_seconds': position, 'duration': duration})
                    position += duration-(plan['transitions'][i]['overlap_seconds'] if i < len(plan['transitions']) else 0)
            tracks = [{'name': t.get('name', names.get(t.get('entry_id'), 'Track')),
                       'start_seconds': t.get('start_seconds', 0), 'duration_seconds': t.get('duration')}
                      for t in tracklist]
            transitions = []
            for i, join in enumerate(plan.get('transitions', [])):
                if i >= len(tracks) or tracks[i]['duration_seconds'] is None:
                    continue
                end = tracks[i]['start_seconds']+tracks[i]['duration_seconds']
                start = end-join['overlap_seconds']
                transitions.append({'start_seconds': start, 'end_seconds': end,
                                    'handoff_seconds': (start+end)/2, 'bars': join['bars'], 'style': join['style']})
            duration = report.get('duration') or report.get('audio', {}).get('duration')
            if duration is None and tracks:
                duration = tracks[-1]['start_seconds']+(tracks[-1]['duration_seconds'] or 0)
            try:
                self.media_path(row['storage_name'])
                available = True
            except (KeyError, FileNotFoundError):
                available = False
            excerpts = plan.get('excerpts', [])
            pair_keys = [hashlib.sha256(canonical([hashes[a['track_id']], hashes[b['track_id']]]).encode()).hexdigest()
                         for a,b in zip(excerpts,excerpts[1:]) if a['track_id'] in hashes and b['track_id'] in hashes]
            result.append({'id': row['id'], 'revision': row['playable_revision'], 'pair_keys': pair_keys,
                           'title': ' → '.join(Path(t['name']).stem for t in tracks) or 'Rendered mix',
                           'duration_seconds': duration, 'tracks': tracks, 'transitions': transitions,
                           'available': available, 'previous_version_kept': row['playable_revision'] != row['requested_revision'],
                           'latest_render_failed': bool(row['last_error']),
                           'audio_url': f'/api/v1/mixes/{row["id"]}/audio?revision={row["playable_revision"]}',
                           'download_url': f'/api/v1/mixes/{row["id"]}/audio?revision={row["playable_revision"]}&download=true'})
        with self.database.connection() as c:
            improved=c.execute('''SELECT p.*,j.payload_json FROM improved_plans p JOIN workflow_jobs j ON j.id=p.job_id
                WHERE j.kind='test_mix' AND j.status='succeeded' AND p.slot='mix' ORDER BY j.rowid DESC LIMIT 50''').fetchall()
        for row in reversed(improved):
            report=json.loads(row['report_json']); plan=report['plan']; payload=json.loads(row['payload_json'])
            tracks=[{'name':source['name'],'start_seconds':planned['start_seconds'],'duration_seconds':planned['duration_seconds']}
                    for source,planned in zip(payload['sources'],plan['sources'])]
            result.insert(0,{'id':'workflow-'+row['job_id'],'revision':1,'pair_keys':[],
                'title':' → '.join(Path(t['name']).stem for t in tracks),'duration_seconds':plan['duration_seconds'],
                'tracks':tracks,'transitions':[{'start_seconds':j['entry_seconds'],'end_seconds':j['end_seconds'],
                    'handoff_seconds':j['fade_start_seconds'],'bars':j['candidate']['bars'],'style':j['candidate']['recipe']} for j in plan['joins']],
                'available':self.storage.path('renders',row['storage_name']).is_file(),'previous_version_kept':False,'latest_render_failed':False,
                'audio_url':f'/api/v1/learning/jobs/{row["job_id"]}/audio/mix',
                'download_url':f'/api/v1/learning/jobs/{row["job_id"]}/audio/mix?download=true'})
        return result

    def mix_audio(self, mix_id, revision=None):
        if mix_id.startswith('workflow-'):
            from .workflow import Workflow
            from .transition_review import media
            from .config import Settings
            return media(Workflow(Settings(data_root=self.storage.root)),mix_id.removeprefix('workflow-'))
        with self.database.connection() as c:
            row = c.execute('''SELECT r.storage_name FROM mixes m JOIN renders r
                ON r.mix_id=m.id AND r.revision=COALESCE(?,m.playable_revision) WHERE m.id=?''', (revision,mix_id)).fetchone()
        if row is None:
            raise KeyError(mix_id)
        return self.media_path(row[0])

    def auditions(self):
        # Read only summaries from SQLite, rather than repeatedly decoding large
        # context-vector snapshots. Only measured, matched artifacts appear.
        with self.database.connection() as c:
            rows = c.execute('''SELECT e.id,e.candidate_id,t.pair_key,e.created_at,
                json_extract(e.payload_json,'$.output') AS output,
                json_extract(e.payload_json,'$.duration') AS duration,
                json_extract(e.payload_json,'$.handoff_seconds') AS handoff,
                json_extract(e.payload_json,'$.loudness.integrated_lufs') AS lufs,
                json_extract(t.snapshot_json,'$.recipe') AS recipe,
                json_extract(e.payload_json,'$.tracks') AS tracks
                FROM candidate_events e JOIN transition_candidates t ON t.id=e.candidate_id
                WHERE e.kind='audition' AND json_type(e.payload_json,'$.loudness')='object'
                AND e.id=(SELECT MAX(latest.id) FROM candidate_events latest
                  WHERE latest.candidate_id=e.candidate_id AND latest.kind='audition'
                  AND json_type(latest.payload_json,'$.loudness')='object')
                ORDER BY e.id DESC LIMIT 20''').fetchall()
        result = []
        for row in rows:
            try:
                path = Path(row['output'])
                if self.media_path(path.name) != path.resolve():
                    continue
            except (KeyError, FileNotFoundError, TypeError):
                continue
            tracks = json.loads(row['tracks'] or '[]')
            result.append({'id': str(row['id']), 'pair_key': row['pair_key'], 'candidate_id': row['candidate_id'],
                           'title': RECIPE_NAMES.get(row['recipe'], row['recipe']), 'recipe': row['recipe'],
                           'tracks': [Path(t['path']).stem for t in tracks],
                           'duration_seconds': row['duration'], 'handoff_seconds': row['handoff'],
                           'integrated_lufs': row['lufs'], 'created_at': row['created_at'],
                           'audio_url': f'/api/v1/auditions/{row["id"]}/audio',
                           'download_url': f'/api/v1/auditions/{row["id"]}/audio?download=true'})
        return result

    def audition_audio(self, event_id):
        with self.database.connection() as c:
            row = c.execute('''SELECT json_extract(payload_json,'$.output') FROM candidate_events
                WHERE id=? AND kind='audition' AND json_type(payload_json,'$.loudness')='object' ''', (event_id,)).fetchone()
        if row is None:
            raise KeyError(event_id)
        path = Path(row[0])
        # Event metadata cannot redirect media serving to another directory.
        resolved = self.media_path(path.name)
        if resolved != path.resolve():
            raise KeyError('Audition is outside render storage')
        return resolved
