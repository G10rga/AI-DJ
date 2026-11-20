"""Inspectable candidate costs and continuous variable-tempo playlist geometry."""
from copy import deepcopy
import hashlib
import json
import math
from bisect import bisect_right
import numpy as np

VERSION = 'playlist-plan-1'
WEIGHT_VERSION = 'playlist-costs-development-1'
WEIGHTS = dict(vocal_collision=.24, vocal_truncation=.20, structure=.10,
               harmony=.08, bass=.08, energy=.08, stretch=.08, omitted=.14)
BARS = (2, 4, 8, 16, 32)
PRESETS = ('blend', 'bass-swap', 'filter')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def curve(points, position):
    return float(np.interp(position, [p[0] for p in points], [p[1] for p in points]))


def automation(preset):
    result = {}
    for side in ('a', 'b'):
        incoming = side == 'b'
        result[side] = {'gain': [[0, 0 if incoming else 1], [1, 1 if incoming else 0]],
                        'low': [[0, 0], [1, 0]], 'mid': [[0, 0], [1, 0]],
                        'high': [[0, 0], [1, 0]], 'hp': [[0, 20], [1, 20]],
                        'lp': [[0, 20000], [1, 20000]]}
        if preset == 'bass-swap':
            result[side]['low'] = ([[0, -24], [.45, -24], [.55, 0], [1, 0]] if incoming
                                   else [[0, 0], [.45, 0], [.55, -24], [1, -24]])
        if preset == 'filter':
            result[side]['hp' if not incoming else 'lp'] = ([[0, 20], [1, 1500]] if not incoming
                                                          else [[0, 800], [1, 20000]])
    return result


def validate_automation(value):
    limits = {'gain': (0, 1.5), 'low': (-24, 12), 'mid': (-24, 12), 'high': (-24, 12),
              'hp': (20, 18000), 'lp': (40, 20000)}
    if not isinstance(value, dict) or set(value) != {'a', 'b'}:
        raise ValueError('Provide automation for both songs')
    for side in value.values():
        if not isinstance(side, dict) or set(side) != set(limits):
            raise ValueError('Provide gain, low, mid, high, hp and lp curves')
        for name, points in side.items():
            if not isinstance(points, list) or not 2 <= len(points) <= 64:
                raise ValueError('Each curve needs 2–64 points')
            last = -1
            for p in points:
                if (not isinstance(p, list) or len(p) != 2 or
                    any(type(x) not in (int, float) or not math.isfinite(x) for x in p) or
                    not last < p[0] <= 1 or not limits[name][0] <= p[1] <= limits[name][1]):
                    raise ValueError('Invalid automation point or range')
                last = p[0]
            if points[0][0] != 0 or points[-1][0] != 1:
                raise ValueError('Curves must cover the whole overlap')
    return value


def corrected_grid(timeline, correction):
    beats = np.asarray(timeline['beats']['times'], dtype=float)
    downs = np.asarray(timeline['downbeats']['times'], dtype=float)
    if correction:
        bpm = correction['bpm']; first = correction['first_downbeat']; phase = correction.get('bar_phase', 0)
        duration = timeline['duration_seconds']
        if correction.get('use_detected_intervals') and len(beats) >= 9:
            nearest = int(np.argmin(abs(beats-first)))
            original_period = float(np.median(np.diff(beats)))
            if not .85 <= original_period*bpm/60 <= 1.15:
                raise ValueError('Turn off detected intervals to correct a substantially different BPM')
            beats = first + (beats[nearest:]-beats[nearest])*(60/bpm/original_period)
        else:
            beats = np.arange(first, duration, 60 / bpm)
        anchors = correction.get('anchors', [])
        if anchors:
            if anchors[0][0] != 0:
                anchors = [[0, first], *anchors]
            if abs(anchors[0][1]-first) > 1e-6 or anchors[-1][0] >= len(beats) or anchors[-1][1] >= duration:
                raise ValueError('Local anchors must agree with the first downbeat and stay within the song')
            indices = np.array([a[0] for a in anchors], dtype=float)
            times = np.array([a[1] for a in anchors], dtype=float)
            shifts = times - beats[indices.astype(int)]
            beats += np.interp(np.arange(len(beats)), indices, shifts)
        beats = beats[(beats >= 0) & (beats < duration)]
        downs = beats[phase::4]
    if len(beats) < 9 or np.any(np.diff(beats) <= 0) or not np.isfinite(beats).all():
        raise ValueError('Beat grid needs correction: insufficient or nonmonotonic markers')
    return beats, downs


def evidence(record, correction=None):
    t = record['effective']; beats, downs = corrected_grid(t, correction)
    rows = t.get('vocal_activity', [])
    vocals = []
    for r in rows:
        ratio = r.get('vocal_ratio')
        # Low-level separation residuals may be leakage. The confidence is a
        # heuristic bounded below certainty, independent of vocal prominence.
        confidence = min(.8, .3+.5*ratio) if ratio is not None else None
        vocals.append({'start': r['start'], 'end': r['end'],
                       'prominence': min(1., max(0., ratio)) if ratio is not None else .5,
                       'confidence': confidence, 'observed': ratio is not None})
    events = []
    for a, b in zip(vocals, vocals[1:]):
        if a['observed'] and b['observed'] and (a['prominence'] >= .2) != (b['prominence'] >= .2):
            events.append({'time': b['start'], 'kind': 'onset' if b['prominence'] >= .2 else 'offset',
                           'confidence': min(a['confidence'], b['confidence']),
                           'meaning': 'Uncalibrated MDX estimate; leakage possible'})
    features = t.get('features', [])
    sync = []
    for start, end in zip(beats, beats[1:]):
        selected = [r for r in features if r['start'] < end and r['end'] > start]
        if not selected: continue
        weights = np.array([min(end, r['end']) - max(start, r['start']) for r in selected])
        row = {'start': float(start), 'end': float(end)}
        for key in ('rms', 'bass_rms', 'chroma'):
            row[key] = np.average([r[key] for r in selected], axis=0, weights=weights).tolist()
        row['spectral_change'] = float(np.linalg.norm(np.array(row['chroma']) - np.array(sync[-1]['chroma']))) if sync else 0.
        sync.append(row)
    ref = {'timeline_id': record['timeline_id'], 'revision': record['revision'], 'config': t.get('config'),
           'source_hash': t['content_hash'], 'correction': correction, 'version': VERSION}
    return {'id': digest(ref), 'reference': ref, 'duration': t['duration_seconds'], 'beats': beats.tolist(),
            'downbeats': downs.tolist(), 'bpm': float(60 / np.median(np.diff(beats))),
            'vocals': vocals, 'vocal_events': events, 'features': sync,
            'sections': t.get('sections', []), 'waveform': features,
            'vocal_ending': (correction or {}).get('vocal_ending'),
            'human_grid': bool(correction), 'key': key_name(sync)}


def key_name(rows):
    if not rows: return 'Unknown'
    chroma = np.mean([r['chroma'] for r in rows], axis=0)
    if not np.any(chroma):
        return 'Unknown'
    major = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    minor = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    choices = [(float(np.dot(chroma, np.roll(p / np.linalg.norm(p), i))), i, name)
               for p, name in ((major, 'major'), (minor, 'minor')) for i in range(12)]
    _, i, name = max(choices)
    return ['C', 'C♯', 'D', 'E♭', 'E', 'F', 'F♯', 'G', 'A♭', 'A', 'B♭', 'B'][i] + ' ' + name + ' (estimate)'


def trajectory(a, b):
    """Smoothstep beat-duration interpolation, including varying local source tempo."""
    da, db = np.diff(a), np.diff(b)
    if len(da) != len(db) or np.any(da <= 0) or np.any(db <= 0):
        raise ValueError('Invalid beat map')
    x = (np.arange(len(da)) + .5) / len(da)
    smooth = x*x*(3-2*x)
    durations = da*(1-smooth) + db*smooth
    return np.r_[0., np.cumsum(durations)]


def candidates(a, b, edit=None, *, expand=False):
    edit = edit or {}; options = []
    ab, bb = np.array(a['beats']), np.array(b['beats'])
    downbeat_indices = []
    for item, beats in ((a, ab), (b, bb)):
        downbeat_indices.append({int(np.argmin(abs(beats-time))) for time in item['downbeats']
                                 if len(beats) and np.min(abs(beats-time)) <= .08})

    def bar_consistency(side, start, count):
        predicted = set(range(start, start+count+1, 4))
        observed = {i for i in downbeat_indices[side] if start <= i <= start+count}
        return len(predicted & observed)/max(len(predicted | observed), 1)
    def starts(e, beats, lo, hi, manual):
        if manual is not None:
            # Exact user cue with a local grid translated to it, validated independently later.
            return [(int(np.argmin(abs(beats-manual))), float(manual))]
        indices = sorted(set(int(np.argmin(abs(beats-d))) for d in e['downbeats'] if lo <= d <= hi))
        # Bound the search while preserving the endpoints and structural neighborhoods.
        if len(indices) > 18:
            indices = [indices[i] for i in np.linspace(0, len(indices)-1, 18).astype(int)]
        return [(i, float(beats[i])) for i in indices]
    lookup = [{key: [row['start'] for row in e[key]] for key in ('features', 'vocals')} for e in (a, b)]
    for expanded in ((True,) if expand else (False, True)):
        ast = starts(a, ab, a['duration']*(.6 if expanded else .75), a['duration'], edit.get('a_cue'))
        bst = starts(b, bb, 0, b['duration']*(.4 if expanded else .2), edit.get('b_cue'))
        for bars in ([edit['bars']] if 'bars' in edit else BARS):
            n = bars*4
            for ia, acue in ast:
                if ia+n >= len(ab): continue
                if 'a_cue' not in edit and bar_consistency(0, ia, n) < .72: continue
                aa = ab[ia:ia+n+1] - ab[ia] + acue
                if aa[-1] > a['duration']: continue
                for ib, bcue in bst:
                    if ib+n >= len(bb): continue
                    if 'b_cue' not in edit and bar_consistency(1, ib, n) < .72: continue
                    ba = bb[ib:ib+n+1] - bb[ib] + bcue
                    if ba[-1] > b['duration']: continue
                    output = trajectory(aa, ba)
                    for preset in ([edit['preset']] if 'preset' in edit else PRESETS):
                        auto = deepcopy(edit.get('automation') or automation(preset))
                        ending = edit.get('vocal_ending', a.get('vocal_ending'))
                        if ending is not None:
                            if ending >= aa[-1] - 2: continue
                            hold = max(0., float(np.interp(ending, aa, output) / output[-1]))
                            if hold > 0:
                                gain = auto['a']['gain']
                                auto['a']['gain'] = [[0, 1], [hold, 1], *[
                                    [hold+(1-hold)*x, y] for x, y in gain[1:-1]
                                ], [1, 0]]
                        choice = {'bars': bars, 'preset': preset, 'a_cue': acue, 'b_cue': bcue,
                                  'a_end': float(aa[-1]), 'b_end': float(ba[-1]),
                                  'a_beats': aa.tolist(), 'b_beats': ba.tolist(), 'output_beats': output.tolist(),
                                  'duration': float(output[-1]), 'automation': auto, 'expanded': expanded}
                        choice['scores'] = costs(a, b, choice, lookup)
                        choice['cost'] = sum(choice['scores'][k]*v for k, v in WEIGHTS.items())
                        ratios = np.r_[np.diff(output)/np.diff(aa), np.diff(output)/np.diff(ba)]
                        choice['warnings'] = ['Large tempo change: audible stretching possible'] if max(ratios.max(), 1/ratios.min()) > 1.12 else []
                        choice['geometry_id'] = digest([choice['a_beats'], choice['b_beats']])[:24]
                        choice['id'] = digest(choice)[:24]; options.append(choice)
        if options: break
    return sorted(options, key=lambda c: (c['cost'], c['id']))


def costs(a, b, c, lookup=None):
    lookup = lookup or [{key: [row['start'] for row in e[key]] for key in ('features', 'vocals')} for e in (a, b)]
    x = np.linspace(0, 1, 33)
    def row_at(side, kind, time):
        index = bisect_right(lookup[side][kind], time)-1
        if index < 0:
            return {}
        row = (a, b)[side][kind][index]
        return row if time < row['end'] else {}
    def prominence(side, times):
        return np.array([row_at(side, 'vocals', t).get('prominence', .5) for t in times])
    def values(side, key):
        points = np.array(c['automation'][side][key])
        return np.interp(x, points[:, 0], points[:, 1])
    ta = np.interp(x*c['duration'], c['output_beats'], c['a_beats'])
    tb = np.interp(x*c['duration'], c['output_beats'], c['b_beats'])
    va, vb = prominence(0, ta), prominence(1, tb)
    ga, gb = values('a', 'gain'), values('b', 'gain')
    fa, fb = row_at(0, 'features', c['a_cue']), row_at(1, 'features', c['b_cue'])
    ca, cb = np.array(fa.get('chroma', [0]*12)), np.array(fb.get('chroma', [0]*12))
    harmony = 1 - float(np.dot(ca, cb) / max(np.linalg.norm(ca)*np.linalg.norm(cb), 1e-8))
    ea, eb = fa.get('rms', .1), fb.get('rms', .1)
    bass_a, bass_b = fa.get('bass_rms', .05), fb.get('bass_rms', .05)
    bass = np.mean(np.maximum(0., ga*bass_a*10**(values('a', 'low')/20) +
                      gb*bass_b*10**(values('b', 'low')/20) - max(bass_a, bass_b)) /
                     max(bass_a, bass_b, 1e-6))
    boundaries = [r.get('time', r.get('start', 0)) for r in a['sections']]
    structural = min([abs(c['a_cue']-t)/16 for t in boundaries] or [1])
    return {k: float(np.clip(v, 0, 1)) for k, v in dict(
        vocal_collision=np.mean(np.minimum(va*ga, vb*gb)),
        vocal_truncation=np.sum(va[1:]*np.maximum(0, -np.diff(ga))), structure=structural,
        harmony=harmony, bass=bass, energy=abs(ea-eb)/max(ea, eb, 1e-6),
        stretch=abs(math.log(a['bpm']/b['bpm']))/math.log(2),
        omitted=((a['duration']-c['a_end'])/a['duration']+c['b_cue']/b['duration'])/2).items()}


def joint_plan(evidences, edits=None, excluded=None, pools=None, diagnostic=None):
    edits = edits or {}; excluded = excluded or {}; diagnostic = diagnostic or {}
    pools = pools if pools is not None else {}
    beam = [(0., [])]
    for i, (a, b) in enumerate(zip(evidences, evidences[1:])):
        key = (i, bool(excluded.get(i)))
        if key not in pools:
            pools[key] = candidates(a, b, edits.get(str(i)), expand=key[1])
        pool = pools[key]
        if i in diagnostic:
            pool = [c for c in pool if c['geometry_id'] == diagnostic[i]]
        next_beam = []
        for cost, path in beam:
            compatible = [c for c in pool if (i in diagnostic or c['geometry_id'] not in excluded.get(i, [])) and
                          (not path or c['a_cue'] >= path[-1]['b_end'] + .01)]
            for c in compatible[:24]: next_beam.append((cost+c['cost'], path+[c]))
        if not next_beam and not key[1]:
            expanded = candidates(a, b, edits.get(str(i)), expand=True)
            pools[key] = expanded
            for cost, path in beam:
                compatible = [c for c in expanded if not path or c['a_cue'] >= path[-1]['b_end'] + .01]
                next_beam.extend((cost+c['cost'], path+[c]) for c in compatible[:24])
        if not next_beam:
            raise ValueError(f'Transition {i+1} needs grid/cue correction; no continuous beatmatched placement')
        beam = sorted(next_beam, key=lambda item: item[0])[:24]
    joins = deepcopy(beam[0][1])
    tracks = []; cursor = 0.
    for i, e in enumerate(evidences):
        previous = joins[i-1] if i else None
        following = joins[i] if i < len(joins) else None
        source_in = previous['b_cue'] if previous else 0.
        source_out = following['a_end'] if following else e['duration']
        anchors = [[source_in, 0.]]
        if previous:
            anchors = [[s, o] for s, o in zip(previous['b_beats'], previous['output_beats'])]
        if following:
            local_start = anchors[-1][1] + following['a_cue'] - anchors[-1][0]
            anchors += [[s, local_start+o] for s, o in zip(following['a_beats'], following['output_beats'])
                        if s > anchors[-1][0]+1e-7]
            following['start'] = cursor+local_start
        if source_out > anchors[-1][0]:
            anchors.append([source_out, anchors[-1][1]+source_out-anchors[-1][0]])
        tracks.append({'index': i, 'evidence_id': e['id'], 'source_in': source_in, 'source_out': source_out,
                       'start': cursor, 'duration': anchors[-1][1], 'map': anchors,
                       'grid_confirmed': e.get('human_grid', False)})
        if following: cursor = following['start']
    result = {'version': VERSION, 'weights_version': WEIGHT_VERSION, 'weights': WEIGHTS,
              'tracks': tracks, 'joins': joins, 'duration': tracks[-1]['start']+tracks[-1]['duration'],
              'evidence_ids': [e['id'] for e in evidences], 'validation': {'status': 'pending'}}
    validate_plan(result)
    result['id'] = digest(result)
    return result


def validate_plan(plan):
    for track in plan['tracks']:
        mapping = np.array(track['map'])
        if not np.isfinite(mapping).all() or np.any(np.diff(mapping, axis=0) <= 0):
            raise ValueError('Source/output anchors must increase strictly')
        if mapping[0, 0] != track['source_in'] or mapping[-1, 0] != track['source_out']:
            raise ValueError('Source continuity failed')
    for i, join in enumerate(plan['joins']):
        for side, track in (('a', plan['tracks'][i]), ('b', plan['tracks'][i+1])):
            mapped = np.interp(join[side+'_beats'], *np.array(track['map']).T) + track['start']
            if not np.allclose(mapped, np.array(join['output_beats'])+join['start'], atol=1e-6):
                raise ValueError('Beat maps disagree across the handoff')
    return plan


def smart_order(evidences):
    remaining = list(range(1, len(evidences))); order = [0]
    while remaining:
        a = evidences[order[-1]]
        def initial_score(i):
            b = evidences[i]
            harmonic = .04 if a.get('key') != b.get('key') else 0.
            return abs(math.log(a['bpm']/b['bpm'])) + harmonic
        def score(i):
            options = candidates(a, evidences[i])
            return options[0]['cost'] + initial_score(i) if options else 1e6 + initial_score(i)
        shortlist = sorted(remaining, key=initial_score)[:6]
        chosen = min(shortlist, key=score); remaining.remove(chosen); order.append(chosen)
    return order
