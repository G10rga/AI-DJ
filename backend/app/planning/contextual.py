"""Conservative cue/recipe proposals from revisioned musical context, not learned taste."""
from copy import deepcopy
import hashlib
import math
import json
import numpy as np
from backend.app.models import Excerpt, MixPlan, Transition
from backend.app.timelines import canonical, validate_timeline

VERSION = 'contextual-candidates-2'
RECIPES = {'groove_32': ('smooth', 32), 'controlled_16': ('controlled', 16),
           'eq_8': ('eq_cut', 8), 'phrase_cut': ('phrase_cut', 0)}


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def cosine_distance(a, b):
    if a is None or b is None:
        return None
    a, b = np.asarray(a), np.asarray(b)
    denominator = np.linalg.norm(a)*np.linalg.norm(b)
    return float(np.clip(1-np.dot(a, b)/denominator, 0, 2)) if denominator > 1e-10 else None


def weighted(rows, start, end, field):
    values, weights = [], []
    for row in rows:
        width = max(0, min(end, row['end'])-max(start, row['start']))
        if width:
            values.append(row[field])
            weights.append(width)
    return np.average(values, axis=0, weights=weights).tolist() if weights else None


def context(timeline, start, end):
    rows = timeline['features']
    middle = (start+end)/2
    before, after = weighted(rows, start, middle, 'rms'), weighted(rows, middle, end, 'rms')
    energy = weighted(rows, start, end, 'rms')
    beats = [t for t in timeline['beats']['times'] if start <= t < end]
    intervals = np.diff(beats)
    regularity = None
    if len(intervals) >= 7:
        median = float(np.median(intervals))
        regularity = float(np.mean(abs(intervals-median) <= .04*median))
    vocal = weighted(timeline.get('vocal_activity', []), start, end, 'active') if timeline.get('vocal_status', {}).get('available') else None
    return {'energy_rms': energy,
            'energy_trend_db': 20*math.log10(max(after, 1e-8)/max(before, 1e-8)) if before is not None and after is not None else None,
            'bass_rms': weighted(rows, start, end, 'bass_rms'),
            'transient_density': weighted(rows, start, end, 'transient_peaks_per_second'),
            'chroma': weighted(rows, start, end, 'chroma'),
            'embedding': weighted(timeline.get('embeddings', []), start, end, 'vector'),
            'vocal_fraction': vocal, 'beat_regularity': regularity}


def estimate_bpm(timeline):
    intervals = np.diff(timeline['beats']['times'])
    if len(intervals) < 8:
        raise ValueError('Insufficient beat evidence')
    period = float(np.median(intervals))
    if period <= 0:
        raise ValueError('Invalid beat period')
    return 60/period


def anchor_evidence(timeline, time):
    phrase = any(abs(t-time) <= .08 for t in timeline['phrase_boundaries']['times'])
    section = any(abs(s['time']-time) <= 2 for s in timeline.get('sections', []))
    human = timeline['phrase_boundaries']['provenance']
    human = isinstance(human, dict) and human.get('method') == 'human correction'
    bars = [b for b in timeline.get('bars', []) if abs(b['start']-time) <= 4 or abs(b['end']-time) <= 4]
    stable_bars = len(bars) >= 2 and all(b['beat_count'] == 4 for b in bars)
    return {'phrase_candidate': phrase, 'section_candidate': section,
            'human_phrase': bool(human and phrase), 'regular_bars': stable_bars}


def anchor_options(timeline, preferred, count=5):
    downs = timeline['downbeats']['times']
    choices = set(timeline['phrase_boundaries']['times'])
    for section in timeline.get('sections', []):
        nearby = [t for t in downs if abs(t-section['time']) <= 2]
        if nearby:
            choices.add(min(nearby, key=lambda t: abs(t-section['time'])))
    choices = [t for t in choices if any(abs(t-d) <= .08 for d in downs)]
    return sorted(choices, key=lambda t: (abs(t-preferred), t))[:count]


def propose_pair(left, right, *, bpms=None, target_bpm=None, preferred=None, maximum=12):
    if type(maximum) is not int or not 1 <= maximum <= 12:
        raise ValueError('Generate at most twelve candidates per pair')
    records = [left, right]
    timelines = [deepcopy(validate_timeline(record['effective'])) for record in records]
    for timeline in timelines:
        # Re-derive after manual marker edits, rather than trust a cached bar list.
        from backend.app.timelines import derive_bars
        timeline['bars'] = derive_bars(timeline)
    rejected = []
    try:
        tempos = list(bpms) if bpms is not None else [estimate_bpm(t) for t in timelines]
        target = target_bpm if target_bpm is not None else math.sqrt(tempos[0]*tempos[1])
        if not all(math.isfinite(x) and x > 0 for x in (*tempos, target)) or any(abs(target/b-1) > .06000001 for b in tempos):
            raise ValueError('No common target within the six-percent stretch limit')
    except ValueError as exc:
        return {'version': VERSION, 'candidates': [], 'rejections': [{'reason': str(exc)}]}
    durations = [t['duration_seconds'] for t in timelines]
    ratios = [target/b for b in tempos]
    side = min(64., *(d/r*.4 for d, r in zip(durations, ratios)))
    preferences = preferred or (durations[0]*.6, durations[1]*.3)
    options = [anchor_options(t, p) for t, p in zip(timelines, preferences)]
    refs = [{'track_id': r['track_id'], 'content_hash': t['content_hash'], 'timeline_id': r['timeline_id'],
             'correction_revision': r['revision'], 'model_config': t.get('config')}
            for r, t in zip(records, timelines)]
    pair_key = digest([r['content_hash'] for r in refs])
    pool = []
    for a in options[0]:
        for b in options[1]:
            anchors = [anchor_evidence(t, time) for t, time in zip(timelines, (a, b))]
            for recipe, (style, bars) in RECIPES.items():
                overlap = bars*240/target if bars else .04
                rejection = {'recipe': recipe, 'anchors': [a, b]}
                if overlap+4 > side*2:
                    rejected.append(dict(rejection, reason='Insufficient solo context for this overlap'))
                    continue
                bounds = [(a-side*ratios[0], a+overlap/2*ratios[0]),
                          (b-overlap/2*ratios[1], b+side*ratios[1])]
                if any(start < 0 or end > duration for (start, end), duration in zip(bounds, durations)):
                    rejected.append(dict(rejection, reason='Candidate exceeds source bounds'))
                    continue
                span = max(overlap/2, 4*60/target)
                contexts = [context(t, max(0, cue-span*ratio), min(d, cue+span*ratio))
                            for t, cue, ratio, d in zip(timelines, (a, b), ratios, durations)]
                ca, cb = contexts
                reason = None
                if any(c['beat_regularity'] is None or c['beat_regularity'] < .85 for c in contexts):
                    reason = 'Insufficient local rhythmic stability'
                elif any(not e['regular_bars'] for e in anchors):
                    reason = 'Uncertain local downbeat/bar geometry'
                elif ca['energy_rms'] is None or cb['energy_rms'] is None or min(ca['energy_rms'], cb['energy_rms']) < .003:
                    reason = 'Missing energy evidence or a near-silent handoff'
                energy_db = 20*math.log10(max(cb['energy_rms'] or 0, 1e-8)/max(ca['energy_rms'] or 0, 1e-8))
                if energy_db < -9:
                    reason = 'Incoming region would collapse energy by over 9 dB'
                # A rising outgoing section must finish before a handoff is proposed.
                rise = context(timelines[0], max(0, a-8*ratios[0]), min(durations[0], a+8*ratios[0]))['energy_trend_db']
                if rise is not None and rise > 3:
                    reason = 'Outgoing energy is still rising; preserve the buildup'
                # Longer blends begin changing the outgoing mids before the
                # nominal handoff. Do not fade through a rise in that interval.
                mid_width = min((64 if bars == 32 else 16 if bars == 16 else 8)*60/target, overlap/2) if bars else 0
                rise_windows = []
                for t in np.arange(a-mid_width/2*ratios[0], a, 2*ratios[0]):
                    trend = context(timelines[0], max(0, float(t)-4*ratios[0]), min(durations[0],float(t)+4*ratios[0]))['energy_trend_db']
                    if trend is not None:
                        rise_windows.append(trend)
                if rise_windows and max(rise_windows) > 3:
                    reason = 'Outgoing midrange fade would interrupt a rising section; preserve the buildup'
                if not bars:
                    if not all(e['human_phrase'] or (e['phrase_candidate'] and e['section_candidate']) for e in anchors):
                        reason = 'A cut needs phrase plus section evidence, or corrected phrase boundaries'
                    local_voices = [context(t, max(0, cue-.75*ratio), min(d, cue+.75*ratio))['vocal_fraction']
                                    for t, cue, ratio, d in zip(timelines, (a, b), ratios, durations)]
                    if any(v is None or v > .1 for v in local_voices):
                        reason = 'A cut needs known vocal gaps at both boundaries'
                if reason:
                    rejected.append(dict(rejection, reason=reason))
                    continue
                harmonic = cosine_distance(ca['chroma'], cb['chroma'])
                embedding = cosine_distance(ca['embedding'], cb['embedding'])
                voice_collision = ca['vocal_fraction']*cb['vocal_fraction'] if ca['vocal_fraction'] is not None and cb['vocal_fraction'] is not None else None
                contrast = harmonic if harmonic is not None else .5
                desired = 32 if contrast < .25 and abs(energy_db) < 3 and (voice_collision or 0) < .4 else 16 if contrast < .5 else 8
                score = 3-abs(energy_db)/6-contrast-(embedding if embedding is not None else .5)*.3
                score -= abs(bars-desired)/32 if bars else .65
                score -= (voice_collision if voice_collision is not None else .5)*(.4 if bars else 0)
                score += .2*sum(e['human_phrase'] or e['section_candidate'] for e in anchors)
                score -= .1*(abs(a-preferences[0])/durations[0]+abs(b-preferences[1])/durations[1])
                excerpts = tuple(Excerpt(ref['track_id'], start, end, duration, bpm, target)
                                 for ref, (start, end), duration, bpm in zip(refs, bounds, durations, tempos))
                plan = MixPlan('proposal', 1, excerpts, (Transition(style, overlap, bars),))
                plan.validate()
                evidence = {'contexts': contexts, 'anchors': anchors, 'energy_change_db': energy_db,
                            'outgoing_trend_db': rise, 'midrange_rise_db': max(rise_windows) if rise_windows else None,
                            'harmonic_distance': harmonic, 'embedding_distance': embedding,
                            'uncontrolled_vocal_collision': voice_collision,
                            'vocal_policy': 'independent non-overlapping vocal handoff' if bars else 'short exchange inside known gaps'}
                candidate = {'version': VERSION, 'pair_key': pair_key, 'sources': refs, 'recipe': recipe,
                             'anchors_seconds': [a, b], 'handoff_seconds': side, 'duration_seconds': 2*side,
                             'context_score': float(score), 'score_method': 'deterministic heuristic; not learned preference',
                             'evidence': evidence, 'plan': json.loads(plan.to_json()),
                             'warnings': ['Proposed only; waveform validation is mandatory.', 'Musical acceptance and phrase labels require listening.']}
                candidate['id'] = digest(candidate)[:24]
                pool.append(candidate)
    pool.sort(key=lambda c: (-c['context_score'], c['id']))
    # Keep recipe diversity so one cue/length family cannot fill all twelve slots.
    chosen = []
    for recipe in RECIPES:
        first = next((c for c in pool if c['recipe'] == recipe), None)
        if first is not None and len(chosen) < maximum:
            chosen.append(first)
    selected = {c['id'] for c in chosen}
    chosen.extend(c for c in pool if c['id'] not in selected)
    chosen = sorted(chosen[:maximum], key=lambda c: (-c['context_score'], c['id']))
    return {'version': VERSION, 'pair_key': pair_key, 'candidates': chosen, 'rejections': rejected,
            'pool_count': len(pool), 'limit': maximum}
