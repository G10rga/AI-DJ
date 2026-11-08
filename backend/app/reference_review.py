"""Draft handoff evidence and explicit, append-only per-transition listening review."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from .references import ReferenceStore, number
from .timelines import canonical
from scripts.setup_timeline import sha256

VERSION = 'reference-transition-drafts-1'
TIMES = ('mix_start', 'mix_end', 'outgoing_source_in', 'outgoing_source_out',
         'incoming_source_in', 'incoming_source_out')
RECIPES = (None, 'groove_32', 'controlled_16', 'eq_8', 'cut', 'other')


def fit_mapping(hypothesis):
    anchors = hypothesis['anchors']
    scale = float(hypothesis['scale'])
    source = np.array([a['source_seconds']+a['window_seconds']/2 for a in anchors])
    mix = np.array([a['mix_seconds']+a['window_seconds']*a['scale']/2 for a in anchors])
    offset = float(np.median(mix-source*scale))
    good = np.abs(mix-(offset+source*scale)) <= 2
    if good.sum() >= 3 and np.ptp(source[good]) >= 24:
        fitted, intercept = np.linalg.lstsq(np.column_stack((source[good], np.ones(good.sum()))), mix[good], rcond=None)[0]
        if .8 <= fitted <= 1.2:
            scale, offset = float(fitted), float(intercept)
    return {'offset_seconds': offset, 'scale': scale,
            'anchor_residual_seconds': float(np.median(np.abs(mix-offset-source*scale))),
            'method': 'affine anchor fit; requires listening review'}


def presence(recording, source, mapping, bounds, anchor_center):
    """Four-second temporal spectral agreement, at one-second intervals.

    This detects agreement with a source, not its exact audible fade boundaries.
    """
    offset, scale = mapping['offset_seconds'], mapping['scale']
    start = max(bounds[0], 2., offset+2*scale)
    end = min(bounds[1], len(recording)*.25-2, offset+(len(source)*.25-2)*scale)
    curve = []
    source_grid = np.arange(len(source))
    for center in np.arange(math.ceil(start), math.floor(end)+.1, 1.):
        indices = np.arange(round((center-2)*4), round((center+2)*4))
        mix = recording[indices].astype(np.float64)
        mapped = (indices*.25-offset)/scale*4
        original = np.column_stack([np.interp(mapped, source_grid, source[:, band]) for band in range(32)])
        mix -= mix.mean(axis=0)
        original -= original.mean(axis=0)
        denominator = np.linalg.norm(mix)*np.linalg.norm(original)
        score = float(np.clip(np.sum(mix*original)/denominator, -1, 1)) if denominator > 1e-5 else 0.
        curve.append({'seconds': float(center), 'similarity': score})
    scores = np.array([row['similarity'] for row in curve])
    stable = []
    for i in range(max(0, len(curve)-4)):
        if np.sum(scores[i:i+5] >= .45) >= 4:
            stable.extend(range(i, i+5))
    if not stable:
        return {'entry': None, 'exit': None, 'curve': curve, 'reason': 'No sustained source agreement'}
    entry = max(0., curve[min(stable)]['seconds']-2)
    exit = min(len(recording)*.25, curve[max(stable)]['seconds']+2)
    if not entry <= anchor_center <= exit:
        return {'entry': None, 'exit': None, 'curve': curve, 'reason': 'Agreement does not contain selected anchor'}
    return {'entry': entry, 'exit': exit, 'curve': curve,
            'reason': 'Draft bounds from sustained spectral agreement; audible fades may extend beyond them'}


class ReferenceReviewStore:
    def __init__(self, settings):
        self.references = ReferenceStore(settings)
        self.database = self.references.database

    def extract(self, reference_id, progress=None):
        reference = self.references.get(reference_id)
        if not reference['alignments']:
            raise ValueError('Align the reference before extracting transitions')
        alignment = reference['alignments'][-1]
        choices = alignment.get('ordered_suggestions')
        if not choices:
            raise ValueError('Ordered reference alignment is required')
        original = reference['import']
        recording = self.references._features(original['recording'])
        located = [i for i, c in enumerate(choices) if c]
        if not located:
            raise ValueError('No located sources to extract')
        centers = np.interp(np.arange(len(choices)), located, [choices[i]['anchor_mix_seconds'] for i in located])
        tracks = []
        for i, (track, choice) in enumerate(zip(original['tracks'], choices)):
            if progress:
                progress(i, len(choices), track['title'])
            options = [{'content_hash': s['content_hash'], 'name': Path(s['path']).name,
                        'duration_seconds': s['duration_seconds'],
                        'audio_url': f"/api/v1/references/{reference_id}/sources/{i}/{s['content_hash']}/audio"}
                       for s in track['sources']]
            item = {'position': i, 'title': track['title'], 'sources': options,
                    'source_hash': choice['source_hash'] if choice else None,
                    'mapping': None, 'presence': None, 'anchor_center': float(centers[i])}
            if choice:
                alternative = next(a for a in alignment['tracks'][i]['alternatives'] if a['source_hash'] == choice['source_hash'])
                hypothesis = alternative['hypotheses'][choice['hypothesis_index']]
                item['mapping'] = fit_mapping(hypothesis)
                source = next(s for s in track['sources'] if s['content_hash'] == choice['source_hash'])
                bounds = (max(0., centers[i-1]-16) if i else 0.,
                          min(original['recording']['duration_seconds'], centers[i+1]+16) if i+1 < len(choices)
                          else original['recording']['duration_seconds'])
                item['presence'] = presence(recording, self.references._features(source), item['mapping'], bounds, centers[i])
                item['anchor_span'] = [min(a['mix_seconds'] for a in hypothesis['anchors']),
                                       max(a['mix_seconds']+a['window_seconds']*a['scale'] for a in hypothesis['anchors'])]
            tracks.append(item)
        transitions = []
        for i, (a, b) in enumerate(zip(tracks, tracks[1:])):
            draft = {key: None for key in TIMES}
            draft.update(outgoing_hash=a['source_hash'], incoming_hash=b['source_hash'], recipe=None,
                         overlap_bars=None, vocal_behavior=None, energy_behavior=None, note='')
            entry = b['presence']['entry'] if b['presence'] else None
            exit = a['presence']['exit'] if a['presence'] else None
            coarse = False
            if entry is None and b.get('anchor_span'):
                entry, coarse = b['anchor_span'][0], True
            if exit is None and a.get('anchor_span'):
                exit, coarse = a['anchor_span'][1], True
            reason = 'Source timing needs manual review'
            kind = 'unresolved'
            if entry is not None and exit is not None and abs(exit-entry) <= 128:
                start, end = min(entry, exit), max(entry, exit)
                kind = 'anchor_search_bracket' if coarse else 'overlap_evidence' if entry <= exit else 'handoff_search_bracket'
                available = [next(s for s in track['sources'] if s['content_hash'] == track['source_hash']) for track in (a,b)]
                lower = max(track['mapping']['offset_seconds'] for track in (a,b))
                upper = min(track['mapping']['offset_seconds']+track['mapping']['scale']*source['duration_seconds']
                            for track, source in zip((a,b), available))
                clipped_start, clipped_end = max(start, lower), min(end, upper)
                clipped = clipped_start != start or clipped_end != end
                if clipped_start <= clipped_end:
                    start, end = clipped_start, clipped_end
                draft.update(mix_start=start, mix_end=end)
                for prefix, track in (('outgoing', a), ('incoming', b)):
                    mapping = track['mapping']
                    source = next(s for s in track['sources'] if s['content_hash'] == track['source_hash'])
                    values = [(t-mapping['offset_seconds'])/mapping['scale'] for t in (start, end)]
                    if -1e-6 <= values[0] <= values[1] <= source['duration_seconds']+1e-6:
                        draft[prefix+'_source_in'], draft[prefix+'_source_out'] = [min(source['duration_seconds'],max(0,v)) for v in values]
                reason = ('Coarse search range from matched passages; locate exact timing by listening' if coarse else
                          'Estimated overlap; listen and correct before including in training' if entry <= exit else
                          'Search range between source matches; locate exact entry and exit by listening')
                if clipped and clipped_start <= clipped_end:
                    reason += '. Range limited to the available source audio'
            elif entry is not None and exit is not None:
                reason = 'Estimated sources leave a gap or an uncertain long overlap; locate by listening'
            focus = (entry+exit)/2 if entry is not None and exit is not None else (a['anchor_center']+b['anchor_center'])/2
            transitions.append({'position': i, 'title': a['title']+' → '+b['title'],
                                'draft': draft, 'kind': kind, 'reason': reason, 'focus_seconds': float(focus)})
        snapshot = {'version': VERSION, 'reference_id': reference_id, 'alignment_id': alignment['id'],
                    'recording_hash': original['recording']['content_hash'], 'title': original['title'],
                    'duration_seconds': original['recording']['duration_seconds'],
                    'audio_url': f'/api/v1/references/{reference_id}/audio',
                    'config': {'window_seconds': 4, 'step_seconds': 1, 'similarity_threshold': .45,
                               'sustained': '4 of 5', 'interval_method': 'source-bounded support brackets with anchor fallback v3'},
                    'tracks': tracks, 'transitions': transitions, 'status': 'unreviewed draft'}
        payload = canonical(snapshot)
        identity = hashlib.sha256(payload.encode()).hexdigest()
        with self.database.connection() as c:
            c.execute('INSERT OR IGNORE INTO reference_transition_drafts(id,reference_id,alignment_id,snapshot_json) VALUES (?,?,?,?)',
                      (identity, reference_id, alignment['id'], payload))
        return self.batch(identity)

    def list(self):
        with self.database.connection() as c:
            imports = c.execute('SELECT id,snapshot_json FROM reference_imports ORDER BY rowid DESC').fetchall()
            latest = {r['reference_id']: r['id'] for r in c.execute('SELECT id,reference_id FROM reference_transition_drafts ORDER BY rowid')}
        result = []
        for row in imports:
            snapshot = json.loads(row['snapshot_json'])
            batch_id = latest.get(row['id'])
            counts = self.batch(batch_id)['counts'] if batch_id else None
            result.append({'id': row['id'], 'title': snapshot['title'],
                           'duration_seconds': snapshot['recording']['duration_seconds'],
                           'draft_id': batch_id, 'counts': counts})
        return result

    def batch(self, draft_id):
        with self.database.connection() as c:
            row = c.execute('SELECT snapshot_json FROM reference_transition_drafts WHERE id=?', (draft_id,)).fetchone()
            if row is None:
                raise KeyError(draft_id)
            reviews = c.execute('SELECT position,revision,review_json FROM reference_transition_reviews WHERE draft_id=? ORDER BY revision', (draft_id,)).fetchall()
        result = json.loads(row[0])
        result['id'] = draft_id
        latest = {r['position']: r for r in reviews}
        for transition in result['transitions']:
            review = latest.get(transition['position'])
            transition['revision'] = review['revision'] if review else 0
            transition['review'] = json.loads(review['review_json']) if review else None
        values = [json.loads(r['review_json']) for r in latest.values()]
        completed = [r for r in values if r.get('reviewed') is True]
        result['counts'] = {'total': len(result['transitions']), 'reviewed': len(completed),
                            'included': sum(r['learn'] is True for r in completed),
                            'excluded': sum(r['learn'] is False for r in completed),
                            'draft_saved': len(values)-len(completed)}
        return result

    def save(self, draft_id, position, expected_revision, review):
        batch = self.batch(draft_id)
        if type(position) is not int or not 0 <= position < len(batch['transitions']):
            raise KeyError(position)
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError('Invalid review revision')
        if not isinstance(review, dict) or type(review.get('reviewed')) is not bool:
            raise ValueError('Specify whether this is saved timing or a completed listening review')
        if review.get('learn') is not None and type(review['learn']) is not bool:
            raise ValueError('Learning choice must be include, exclude or undecided')
        if review['reviewed'] and type(review.get('learn')) is not bool:
            raise ValueError('Choose include/exclude before completing a listening review')
        allowed = {*TIMES, 'outgoing_hash', 'incoming_hash', 'recipe', 'overlap_bars', 'vocal_behavior',
                   'energy_behavior', 'note', 'learn', 'reviewed'}
        if set(review)-allowed:
            raise ValueError('Unexpected review fields')
        payload = {key: review.get(key) for key in allowed}
        for name, limit in (('note', 2000), ('vocal_behavior', 500), ('energy_behavior', 500)):
            value = payload[name]
            if value is not None and (not isinstance(value, str) or len(value) > limit):
                raise ValueError('Review notes must be short text')
        if payload['recipe'] not in RECIPES:
            raise ValueError('Unknown transition category')
        if payload['overlap_bars'] is not None:
            number(payload['overlap_bars'], 0, 512)
        left, right = batch['tracks'][position:position+2]
        sources = []
        for key, track in (('outgoing_hash', left), ('incoming_hash', right)):
            source = next((s for s in track['sources'] if s['content_hash'] == payload[key]), None)
            if payload[key] is not None and source is None:
                raise ValueError('Select a registered source for each song')
            if payload['reviewed'] and payload['learn'] and source is None:
                raise ValueError('Included transitions require both source identities')
            sources.append(source)
        for key in TIMES:
            if payload['reviewed'] and payload['learn'] and payload[key] is None:
                raise ValueError('Included transitions require all six timing fields')
        ranges = [('mix_start', 'mix_end', batch['duration_seconds'])]
        for prefix, source in zip(('outgoing', 'incoming'), sources):
            ranges.append((prefix+'_source_in', prefix+'_source_out', source['duration_seconds'] if source else 0))
        for first, last, limit in ranges:
            a, b = payload[first], payload[last]
            if payload['reviewed'] and (a is None) != (b is None):
                raise ValueError('Start and end times must both be known or both unknown')
            if a is not None or b is not None:
                # The editor displays milliseconds; round-tripping a media
                # endpoint can round up by half a millisecond. Preserve bounds
                # in stored training observations rather than rejecting that UI.
                label = {'mix_start': 'Recording entry/exit', 'outgoing_source_in': 'Outgoing source cues',
                         'incoming_source_in': 'Incoming source cues'}[first]
                try:
                    if a is not None:
                        number(a, 0, limit+.0005001)
                    if b is not None:
                        number(b, a if a is not None else 0, limit+.0005001)
                except ValueError as exc:
                    raise ValueError(label+': times must be in bounds, with exit at or after entry') from exc
                a, b = min(a, limit) if a is not None else None, min(b, limit) if b is not None else None
                payload[first], payload[last] = a, b
                if payload['reviewed'] and (a == b) != (payload['mix_start'] == payload['mix_end']):
                    raise ValueError('Positive recording intervals need positive source intervals')
        with self.database.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            current = c.execute('SELECT COALESCE(MAX(revision),0) FROM reference_transition_reviews WHERE draft_id=? AND position=?',
                                (draft_id, position)).fetchone()[0]
            if current != expected_revision:
                raise ValueError('This review changed in another window; reload before saving')
            c.execute('INSERT INTO reference_transition_reviews VALUES (?,?,?,?,CURRENT_TIMESTAMP)',
                      (draft_id, position, current+1, canonical(payload)))
        return self.batch(draft_id)

    def export(self, draft_id):
        batch = self.batch(draft_id)
        rows = []
        for transition in batch['transitions']:
            if transition['review'] and transition['review'].get('reviewed') is True and transition['review']['learn'] is True:
                rows.append({'position': transition['position'], 'review_revision': transition['revision'],
                             'source_positions': [transition['position'], transition['position']+1],
                             'decision': transition['review']})
        return {'version': 'reviewed-reference-decisions-1', 'draft_id': draft_id,
                'reference_id': batch['reference_id'], 'alignment_id': batch['alignment_id'],
                'recording_hash': batch['recording_hash'], 'examples': rows,
                'style_examples': sum(row['decision']['recipe'] is not None for row in rows),
                'meaning': 'Explicitly reviewed observed decisions; no preference negatives'}

    def audio(self, reference_id, position=None, digest=None):
        reference = self.references.get(reference_id)['import']
        if position is None:
            source = reference['recording']
        else:
            if type(position) is not int or not 0 <= position < len(reference['tracks']):
                raise KeyError(position)
            source = next((s for s in reference['tracks'][position]['sources'] if s['content_hash'] == digest), None)
            if source is None:
                raise KeyError(digest)
        path = Path(source['path'])
        if sha256(path) != source['content_hash']:
            raise ValueError('Source audio changed; re-import before reviewing')
        return path
