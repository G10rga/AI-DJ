"""Reference recordings: immutable imports/estimates, append-only human review."""
from pathlib import Path
from copy import deepcopy
import hashlib
import json
import math
from importlib.metadata import version
import numpy as np
from .audio.probe import probe
from .audio.reference import VERSION, spectral_features, suggest_matches, ordered_suggestions
from .config import Settings
from .db import Database
from .storage import Storage
from .timelines import canonical
from scripts.setup_timeline import sha256


def number(value, lower, upper):
    if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError('Expected finite seconds inside the audio bounds')
    return value


class ReferenceStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.storage = Storage(settings.data_root)
        self.storage.initialize()
        self.database = Database(settings.data_root/'app.sqlite3')
        self.database.initialize()
        self.cache = settings.data_root/'analysis'/'references'
        self.cache.mkdir(exist_ok=True)

    def import_manifest(self, manifest_path):
        manifest_path = Path(manifest_path).resolve(strict=True)
        manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
        def inspect(value):
            path = Path(value)
            if not path.is_absolute():
                path = manifest_path.parent/path
            path = path.resolve(strict=True)
            info = probe(path, self.settings)
            if info.duration > 8*3600:
                raise ValueError('Reference inputs must be at most eight hours long')
            return {'path': str(path), 'content_hash': sha256(path), 'duration_seconds': info.duration}
        recording = inspect(manifest['recording'])
        if not isinstance(manifest['tracks'], list) or not 2 <= len(manifest['tracks']) <= 200:
            raise ValueError('Provide 2–200 ordered tracks')
        tracks = []
        for position, track in enumerate(manifest['tracks']):
            if not isinstance(track.get('title'), str) or not track['title'].strip():
                raise ValueError('Every track needs a title')
            sources = track.get('sources', [])
            if not isinstance(sources, list) or len(sources) > 5:
                raise ValueError('Provide up to five explicit source alternatives per track')
            tracks.append({'position': position, 'title': track['title'], 'note': track.get('note', ''),
                           'sources': [inspect(p) for p in sources]})
        snapshot = {'version': 'reference-import-1', 'title': manifest.get('title', manifest_path.stem),
                    'recording': recording, 'tracks': tracks}
        payload = canonical(snapshot)
        identity = hashlib.sha256(payload.encode()).hexdigest()
        with self.database.connection() as c:
            c.execute('INSERT OR IGNORE INTO reference_imports(id,snapshot_json) VALUES (?,?)', (identity, payload))
        return self.get(identity)

    def get(self, reference_id):
        with self.database.connection() as c:
            row = c.execute('SELECT snapshot_json FROM reference_imports WHERE id=?', (reference_id,)).fetchone()
            if row is None:
                raise KeyError(reference_id)
            annotations = c.execute('SELECT revision,annotation_json FROM reference_annotations WHERE reference_id=? ORDER BY revision DESC LIMIT 1', (reference_id,)).fetchone()
            alignments = c.execute('SELECT id,snapshot_json FROM reference_alignments WHERE reference_id=? ORDER BY rowid', (reference_id,)).fetchall()
        return {'id': reference_id, 'import': json.loads(row[0]),
                'revision': annotations[0] if annotations else 0,
                'annotation': json.loads(annotations[1]) if annotations else None,
                'alignments': [{'id': r[0], **json.loads(r[1])} for r in alignments]}

    def _features(self, source):
        path = Path(source['path'])
        if sha256(path) != source['content_hash']:
            raise ValueError('Reference source changed; import again: '+path.name)
        destination = self.cache/(source['content_hash']+'-'+VERSION+'.npy')
        if destination.exists():
            return np.load(destination, allow_pickle=False)
        result = spectral_features(path, source['duration_seconds'], self.settings, self.storage.root/'tmp')
        # Atomic replacement: interrupted extraction cannot publish a partial cache.
        from uuid import uuid4
        temporary = destination.with_name(uuid4().hex+'.tmp')
        try:
            with temporary.open('wb') as stream:
                np.save(stream, result, allow_pickle=False)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return result

    def align(self, reference_id, progress=None):
        imported = self.get(reference_id)['import']
        recording = self._features(imported['recording'])
        tracks = []
        for track in imported['tracks']:
            if progress:
                progress(track['position'], len(imported['tracks']), track['title'])
            alternatives = []
            for source in track['sources']:
                alternatives.append({'source_hash': source['content_hash'],
                                     'hypotheses': suggest_matches(recording, self._features(source))})
            status = ('missing_source' if not alternatives else
                      'needs_review' if any(a['hypotheses'] for a in alternatives) else 'no_match')
            tracks.append({'position': track['position'], 'title': track['title'], 'alternatives': alternatives,
                           'status': status})
        snapshot = {'version': VERSION, 'step_seconds': .25, 'scale_range': [.92, 1.08],
                    'runtime': {name: version(name) for name in ('numpy', 'scipy')},
                    'feature_config': {'sample_rate': 8000, 'fft_samples': 2048, 'log_bands': 32,
                                       'window_seconds': 16, 'scale_step': .01, 'max_source_windows': 12},
                    'method': 'time-centered log spectral correlation; scores are not probabilities',
                    'status': 'unreviewed', 'tracks': tracks,
                    'ordered_suggestions': ordered_suggestions(tracks)}
        return self._save_alignment(reference_id, snapshot)

    def _save_alignment(self, reference_id, snapshot):
        payload = canonical(snapshot)
        identity = hashlib.sha256((reference_id+payload).encode()).hexdigest()
        with self.database.connection() as c:
            c.execute('INSERT OR IGNORE INTO reference_alignments(id,reference_id,snapshot_json) VALUES (?,?,?)',
                      (identity, reference_id, payload))
        return {'id': identity, **snapshot}

    def refine(self, reference_id, progress=None, *, detailed=False):
        """Retain the global search, append bounded searches for unresolved slots."""
        reference = self.get(reference_id)
        if not reference['alignments']:
            raise ValueError('Run alignment before refinement')
        parent = reference['alignments'][-1]
        snapshot = deepcopy(parent)
        snapshot.pop('id')
        snapshot['parent_alignment_id'] = parent['id']
        snapshot['refinement_runtime'] = {name: version(name) for name in ('numpy', 'scipy')}
        choices = ordered_suggestions(snapshot['tracks'])
        imported = reference['import']
        for source in [imported['recording'], *(s for t in imported['tracks'] for s in t['sources'])]:
            if sha256(Path(source['path'])) != source['content_hash']:
                raise ValueError('Reference source changed; import again')
        recording = self._features(imported['recording'])
        for i, choice in enumerate(choices):
            if choice is not None:
                continue
            previous = next((c['anchor_mix_seconds'] for c in reversed(choices[:i]) if c), 0.)
            following = next((c['anchor_mix_seconds'] for c in choices[i+1:] if c), len(recording)*.25)
            start, end = int(previous/.25), min(len(recording), int(following/.25))
            if end-start < 64:
                continue
            track = snapshot['tracks'][i]
            if progress:
                progress(i, len(choices), track['title'])
            bounds = [start*.25, end*.25]
            track['refinement_bounds_seconds'] = bounds
            for alternative, source in zip(track['alternatives'], imported['tracks'][i]['sources']):
                hypotheses = suggest_matches(recording[start:end], self._features(source),
                                             window_seconds=8 if detailed else 16,
                                             scales=np.arange(.8, 1.201, .01) if detailed else None,
                                             max_windows=64 if detailed else 24)
                for hypothesis in hypotheses:
                    if detailed:
                        hypothesis['minimum_supporting_windows'] = 4
                    hypothesis['offset_seconds'] += start*.25
                    hypothesis['search_bounds_seconds'] = bounds
                    for anchor in hypothesis['anchors']:
                        anchor['mix_seconds'] += start*.25
                        anchor['offset_seconds'] += start*.25
                alternative['hypotheses'].extend(hypotheses)
            track['status'] = 'needs_review' if any(a['hypotheses'] for a in track['alternatives']) else track['status']
        snapshot['ordered_suggestions'] = ordered_suggestions(snapshot['tracks'])
        snapshot['refinement_config'] = {'version': 'ordered-gap-1', 'max_source_windows': 64 if detailed else 24,
                                         'window_seconds': 8 if detailed else 16,
                                         'minimum_supporting_windows': 4 if detailed else 2,
                                         'scale_range': [.8, 1.2] if detailed else [.92, 1.08]}
        return self._save_alignment(reference_id, snapshot)

    def review_template(self, reference_id):
        reference = self.get(reference_id)
        return {'reference_id': reference_id, 'expected_revision': reference['revision'],
                'reviewed': False, 'note': '',
                'tracks': [{'position': t['position'], 'title': t['title'], 'source_hash': None, 'source_in': None,
                            'source_out': None, 'mix_in': None, 'mix_out': None} for t in reference['import']['tracks']],
                'transitions': [{'position': i, 'mix_start': None, 'mix_end': None, 'recipe': None,
                                 'overlap_bars': None, 'vocal_behavior': None, 'energy_behavior': None}
                                for i in range(len(reference['import']['tracks'])-1)]}

    def report(self, reference_id):
        reference = self.get(reference_id)
        if not reference['alignments']:
            raise ValueError('Run alignment before exporting a report')
        alignment = reference['alignments'][-1]
        tracks = alignment['tracks']
        choices = alignment.get('ordered_suggestions', ordered_suggestions(tracks))
        lines = [f"# {reference['import']['title']}", '',
                 'Unreviewed source-to-recording anchor proposals. Times are matched passage centers,',
                 'not track start times. Scores are spectral similarity, not confidence or quality.', '',
                 f"Reference: `{reference_id}`. Alignment: `{alignment['id']}`.", '',
                 '| # | Song | Recording anchor | Source file | Supporting windows | Similarity |',
                 '|---|---|---|---|---|---|']
        def clean(text):
            return str(text).replace('|', '/').replace('\n', ' ').replace('\r', ' ')
        for original, track, choice in zip(reference['import']['tracks'], tracks, choices):
            title = clean(track['title'])
            if choice is None:
                lines.append(f"| {track['position']+1} | {title} | Unresolved | — | — | — |")
            else:
                alternative = next(a for a in track['alternatives'] if a['source_hash'] == choice['source_hash'])
                hypothesis = alternative['hypotheses'][choice['hypothesis_index']]
                source = next(s for s in original['sources'] if s['content_hash'] == choice['source_hash'])
                seconds = round(choice['anchor_mix_seconds'])
                time = f'{seconds//60:02}:{seconds%60:02}'
                lines.append(f"| {track['position']+1} | {title} | {time} | {clean(Path(source['path']).name)} | {hypothesis['supporting_windows']} | {hypothesis['similarity']:.3f} |")
        notes = [f"- Entry {t['position']+1}: {clean(t['note'])}" for t in reference['import']['tracks'] if t.get('note')]
        if notes:
            lines.extend(['', 'Import-time source notes (preserved with the immutable import):', '', *notes])
        lines.extend(['', 'No listening approval or training labels have been recorded by this report.', ''])
        return '\n'.join(lines)

    def annotate(self, reference_id, payload):
        reference = self.get(reference_id)
        if payload.get('reference_id') != reference_id or payload.get('reviewed') is not True:
            raise ValueError('Explicit human review of this reference is required')
        revision = payload.get('expected_revision')
        if type(revision) is not int or revision < 0:
            raise ValueError('Invalid expected revision')
        imported = reference['import']
        if len(payload['tracks']) != len(imported['tracks']) or len(payload['transitions']) != len(imported['tracks'])-1:
            raise ValueError('Review must preserve every ordered track and adjacent transition')
        duration = imported['recording']['duration_seconds']
        previous_in = previous_out = -1
        for position, (track, original) in enumerate(zip(payload['tracks'], imported['tracks'])):
            if type(track['position']) is not int or track['position'] != position:
                raise ValueError('Track positions must preserve the supplied order')
            source = next((s for s in original['sources'] if s['content_hash'] == track['source_hash']), None)
            if source is None:
                raise ValueError('Select an imported source for every track')
            a, b = (number(track[k], 0, source['duration_seconds']) for k in ('source_in', 'source_out'))
            x, y = (number(track[k], 0, duration) for k in ('mix_in', 'mix_out'))
            if not a < b or not x < y or x < previous_in or y < previous_out:
                raise ValueError('Reviewed intervals must be positive and preserve track order')
            previous_in, previous_out = x, y
        for position, transition in enumerate(payload['transitions']):
            if type(transition['position']) is not int or transition['position'] != position:
                raise ValueError('Transition positions must preserve track order')
            start, end = transition.get('mix_start'), transition.get('mix_end')
            if (start is None) != (end is None):
                raise ValueError('Transition boundaries must both be known or both unknown')
            if start is not None:
                number(start, 0, duration)
                number(end, start, duration)
                left, right = payload['tracks'][position:position+2]
                if (start < left['mix_in'] or end > right['mix_out']
                        or start > left['mix_out'] or end < right['mix_in']):
                    raise ValueError('Transition lies outside its adjacent track intervals')
            if transition.get('recipe') not in (None, 'groove_32', 'controlled_16', 'eq_8', 'cut', 'other'):
                raise ValueError('Unknown recipe category')
            bars = transition.get('overlap_bars')
            if bars is not None:
                number(bars, 0, 512)
            for key in ('vocal_behavior', 'energy_behavior'):
                if transition.get(key) is not None and not isinstance(transition[key], str):
                    raise ValueError('Observed behavior must be text or null')
        canonical(payload)
        with self.database.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            current = c.execute('SELECT COALESCE(MAX(revision),0) FROM reference_annotations WHERE reference_id=?', (reference_id,)).fetchone()[0]
            if current != revision:
                raise ValueError('Review is stale; reload before saving')
            c.execute('INSERT INTO reference_annotations VALUES (?,?,?,CURRENT_TIMESTAMP)',
                      (reference_id, revision+1, canonical(payload)))
        return self.get(reference_id)
