"""Immutable musical predictions with explicit, revisioned human overrides."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from .db import Database

VERSION = 'musical-timeline-1'
MARKERS = ('beats', 'downbeats', 'phrase_boundaries')


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':'))


def identity(content_hash, config):
    return hashlib.sha256((VERSION+':'+content_hash+':'+canonical(config)).encode()).hexdigest()


def validate_times(values, duration):
    if not isinstance(values, list) or any(type(t) not in (int, float) or not math.isfinite(t) or not 0 <= t < duration for t in values):
        raise ValueError('Markers must be finite seconds inside the song')
    if any(b-a < .02 for a, b in zip(values, values[1:])):
        raise ValueError('Markers must be sorted and at least 20 ms apart')


def validate_timeline(data):
    if data.get('version') != VERSION or not data.get('content_hash'):
        raise ValueError('Unsupported or unidentified timeline')
    duration = data.get('duration_seconds')
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('Invalid timeline duration')
    canonical(data)
    for name in MARKERS:
        layer = data[name]
        validate_times(layer['times'], duration)
        confidence = layer.get('confidence')
        if confidence is not None and (type(confidence) not in (int, float) or not 0 <= confidence <= 1):
            raise ValueError('Invalid confidence')
        if not layer.get('provenance'):
            raise ValueError('Prediction provenance is required')
    beats = data['beats']['times']
    if any(not any(abs(t-b) <= .05 for b in beats) for t in data['downbeats']['times']):
        raise ValueError('Downbeats must coincide with a beat')
    for series in ('features', 'embeddings', 'vocal_activity'):
        previous = 0
        for item in data.get(series, []):
            if not 0 <= item['start'] < item['end'] <= duration+.001 or item['start'] < previous-.001:
                raise ValueError('Invalid or overlapping timeline intervals')
            previous = item['end']
            if series == 'embeddings':
                vector = item['vector']
                if len(vector) != 768 or any(type(x) not in (int, float) or not math.isfinite(x) for x in vector):
                    raise ValueError('MERT embeddings must contain 768 finite values')
            elif series == 'features':
                for field in ('rms', 'peak', 'bass_rms', 'transient_peaks_per_second'):
                    if type(item.get(field)) not in (int, float) or item[field] < 0:
                        raise ValueError('Invalid DSP feature value')
                if len(item.get('chroma', [])) != 12 or any(type(x) not in (int, float) or x < 0 for x in item['chroma']):
                    raise ValueError('Chroma must contain twelve nonnegative values')
            elif type(item.get('rms')) not in (int, float) or item['rms'] < 0 or type(item.get('active')) is not bool:
                raise ValueError('Invalid vocal activity evidence')
    for section in data.get('sections', []):
        validate_times([section['time']], duration)
    if data.get('config', {}).get('analysis_profile') == 'transition-foundation-1':
        from .audio.analysis_evidence import validate_vocal_rows, VERSION as EVIDENCE_VERSION
        validate_vocal_rows(data.get('vocal_activity', []))
        if data.get('analysis_evidence', {}).get('version') != EVIDENCE_VERSION:
            raise ValueError('Missing versioned foundation evidence')
        chunks = {row['index']: row for row in data.get('vocal_chunks', [])}
        for row in data.get('vocal_activity', []):
            chunk = chunks.get(row.get('chunk_index'))
            if (chunk is None or chunk.get('original_sha256') != data['content_hash']
                    or not chunk['context_source_interval'][0] <= row['start'] < row['end'] <= chunk['context_source_interval'][1]+1e-6
                    or not chunk['core_interval'][0] <= row['start'] < row['end'] <= chunk['core_interval'][1]+1e-6
                    or not chunk.get('context_sha256') or not chunk.get('stem_sha256', {}).get('vocals')
                    or chunk.get('configuration', {}).get('model') != data['config'].get('separator')):
                raise ValueError('Missing or inconsistent vocal source/model/coverage provenance')
    return data


def derive_bars(data):
    beats, downbeats = data['beats']['times'], data['downbeats']['times']
    bars = []
    for start, end in zip(downbeats, downbeats[1:]):
        count = sum(start-.05 <= beat < end-.05 for beat in beats)
        bars.append({'start': start, 'end': end, 'beat_count': count,
                     'meter': '4/4 candidate' if count == 4 else 'uncertain'})
    return bars


class TimelineStore:
    def __init__(self, root):
        self.database = Database(Path(root)/'app.sqlite3')
        self.database.initialize()

    def find(self, content_hash, config):
        key = identity(content_hash, config)
        with self.database.connection() as c:
            row = c.execute('SELECT prediction_json FROM timelines WHERE id=?', (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def save(self, source, prediction, config):
        validate_timeline(prediction)
        if (prediction.get('config', {}).get('analysis_profile') == 'transition-foundation-1'
                and prediction['config'] != config):
            raise ValueError('Foundation prediction/configuration mismatch')
        source = Path(source).resolve(strict=True)
        with source.open('rb') as audio:
            if hashlib.file_digest(audio, 'sha256').hexdigest() != prediction['content_hash']:
                raise ValueError('Source changed since timeline analysis')
        key = identity(prediction['content_hash'], config)
        track_id = 'timeline-'+hashlib.sha256((str(source)+':'+prediction['content_hash']).encode()).hexdigest()[:24]
        payload = canonical(prediction)
        with self.database.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            existing = c.execute('SELECT prediction_json FROM timelines WHERE id=?', (key,)).fetchone()
            if existing and existing[0] != payload:
                raise ValueError('Cannot change a cached prediction; change its configuration/version')
            c.execute('INSERT OR IGNORE INTO timelines(id,content_hash,config_json,prediction_json) VALUES (?,?,?,?)',
                      (key, prediction['content_hash'], canonical(config), payload))
            c.execute('INSERT OR IGNORE INTO tracks(id,content_hash,original_name,storage_name,metadata_json) VALUES (?,?,?,?,?)',
                      (track_id, prediction['content_hash'], source.name, 'external:'+track_id, canonical({'external_path': str(source)})))
            c.execute('INSERT OR IGNORE INTO track_timelines VALUES (?,?)', (track_id, key))
        return {'track_id': track_id, 'timeline_id': key}

    def tracks(self, *, profile=None):
        # Experimental evidence is explicitly selected; merely caching it must
        # not hide the existing editor's latest prediction/human corrections.
        selection = ("COALESCE(json_extract(tl.config_json,'$.analysis_profile'),'') != 'transition-foundation-1'"
                     if profile is None else "json_extract(tl.config_json,'$.analysis_profile') = ?")
        newest_selection = selection.replace('tl.config_json', 'newest.config_json')
        with self.database.connection() as c:
            return [dict(row) for row in c.execute('''SELECT t.id,t.original_name,tt.timeline_id,tl.created_at
                FROM tracks t JOIN track_timelines tt ON tt.track_id=t.id
                JOIN timelines tl ON tl.id=tt.timeline_id
                WHERE '''+selection+''' AND tl.rowid=(SELECT newest.rowid FROM timelines newest JOIN track_timelines link ON link.timeline_id=newest.id
                    WHERE link.track_id=t.id AND '''+newest_selection+''' ORDER BY newest.created_at DESC,newest.rowid DESC LIMIT 1)
                ORDER BY tl.created_at DESC,t.original_name''', () if profile is None else (profile, profile))]

    def source(self, track_id):
        with self.database.connection() as c:
            row = c.execute('SELECT metadata_json,content_hash FROM tracks WHERE id=?', (track_id,)).fetchone()
        if row is None:
            raise KeyError(track_id)
        return Path(json.loads(row[0])['external_path']), row[1]

    def for_content(self, content_hash, *, profile=None):
        """Resolve a current analysis by audio identity, including manual overrides."""
        selection = ("COALESCE(json_extract(tl.config_json,'$.analysis_profile'),'') != 'transition-foundation-1'"
                     if profile is None else "json_extract(tl.config_json,'$.analysis_profile') = ?")
        with self.database.connection() as c:
            row = c.execute('''SELECT tt.track_id,tl.id FROM timelines tl
                JOIN track_timelines tt ON tt.timeline_id=tl.id WHERE tl.content_hash=? AND '''+selection+'''
                ORDER BY tl.created_at DESC,tl.rowid DESC,tt.track_id LIMIT 1''',
                (content_hash,) if profile is None else (content_hash, profile)).fetchone()
        if row is None:
            raise KeyError(content_hash)
        return self.get(row[0], row[1])

    def get(self, track_id, timeline_id):
        with self.database.connection() as c:
            row = c.execute('''SELECT prediction_json FROM timelines tl JOIN track_timelines tt ON tt.timeline_id=tl.id
                WHERE tt.track_id=? AND tl.id=?''', (track_id, timeline_id)).fetchone()
            if row is None:
                raise KeyError((track_id, timeline_id))
            history = [dict(r) for r in c.execute('SELECT revision,changes_json,note,created_at FROM timeline_corrections WHERE timeline_id=? ORDER BY revision', (timeline_id,))]
        prediction = json.loads(row[0])
        effective = deepcopy(prediction)
        for edit in history:
            for field, times in json.loads(edit.pop('changes_json')).items():
                effective[field] = {'times': times, 'confidence': None,
                                    'provenance': {'method': 'human correction', 'revision': edit['revision']}}
        effective['bars'] = derive_bars(effective)
        return {'track_id': track_id, 'timeline_id': timeline_id, 'revision': len(history),
                'prediction': prediction, 'effective': effective, 'history': history}

    def correct(self, track_id, timeline_id, expected_revision, changes, note=''):
        if type(expected_revision) is not int or expected_revision < 0 or not isinstance(changes, dict) or not changes or set(changes)-set(MARKERS):
            raise ValueError('Provide marker corrections and the current revision')
        if not isinstance(note, str) or len(note) > 2000:
            raise ValueError('Correction note is too long')
        current = self.get(track_id, timeline_id)
        if current['revision'] != expected_revision:
            raise ValueError('Timeline changed; reload before saving corrections')
        effective = deepcopy(current['effective'])
        for name, times in changes.items():
            effective[name]['times'] = times
        validate_timeline(effective)
        with self.database.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            revision = c.execute('SELECT COALESCE(MAX(revision),0) FROM timeline_corrections WHERE timeline_id=?', (timeline_id,)).fetchone()[0]
            if expected_revision != revision:
                raise ValueError('Timeline changed; reload before saving corrections')
            c.execute('INSERT INTO timeline_corrections(timeline_id,revision,changes_json,note) VALUES (?,?,?,?)',
                      (timeline_id, revision+1, canonical(changes), note))
        return self.get(track_id, timeline_id)
