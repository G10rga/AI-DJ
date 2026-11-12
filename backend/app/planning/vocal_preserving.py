"""Pinned, conservative proposals for continuous vocal-preserving master blends."""
from copy import deepcopy
import hashlib
import math

import numpy as np

from backend.app.audio.analysis_evidence import foundation_evidence, interval_activity
from backend.app.audio.bar_evidence import regular_bar_spans
from backend.app.audio.stretch import tempo_ratio
from backend.app.timelines import canonical

VERSION = 'vocal-preserving-planner-1'
PIPELINE = 'improved-transitions-1'
RECIPES = ('plain_crossfade', 'protected_vocal')
TAIL_GUARD = 2.


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def review(code, message, *, join=None, source=None, details=None):
    return {'code': code, 'message': message, 'join_index': join, 'source_index': source,
            'details': details or {}, 'actions': ['Listen to the originals and mark outgoing vocal completion and incoming entry.',
                'Correct uncertain beat/downbeat evidence and revalidate.']}


def source_evidence(record):
    evidence = foundation_evidence(record)
    timeline = record['effective']
    return evidence, {'beats': evidence['beats']['times'], 'downbeats': evidence['downbeats']['times'],
                      'duration_seconds': timeline['duration_seconds']}


def source_tempos(records):
    tempos = []
    for record in records:
        evidence, _ = source_evidence(record)
        spans = evidence['regular_spans']
        if not spans:
            raise ValueError('No supported local eight-bar tempo')
        tempos.append(float(np.median([span['source_bpm'] for span in spans])))
    target = math.exp(sum(math.log(bpm) for bpm in tempos)/len(tempos))
    for bpm in tempos:
        tempo_ratio(bpm, target)
    return tempos, target


def region_features(timeline, start, end):
    rows = [row for row in timeline.get('features', []) if row['start'] < end and row['end'] > start]
    cursor = start
    weights, energy, chroma = [], [], []
    for row in rows:
        if row['start'] > cursor+.001:
            return None
        width = min(end, row['end'])-max(start, row['start'])
        weights.append(width); energy.append(row['rms']); chroma.append(row['chroma'])
        cursor = max(cursor, row['end'])
    if cursor < end-.001 or not weights:
        return None
    return {'rms': float(np.average(energy, weights=weights)),
            'chroma': np.average(chroma, axis=0, weights=weights).tolist()}


def structural_support(evidence, cue):
    return any(abs(section['time']-cue) <= 2 for section in evidence['structural_changes'])


def propose_pair(left, right, *, seconds=72., maximum=12, source_bpms=None, target_bpm=None, prediction=None):
    if type(maximum) is not int or not 1 <= maximum <= 12 or not math.isfinite(seconds) or seconds < 16:
        raise ValueError('Choose a finite play preference of at least 16s and at most twelve candidates')
    records = [left, right]
    evidence, sources = zip(*(source_evidence(record) for record in records))
    requested = {'seconds': seconds, 'prediction': deepcopy(prediction)}
    failures = []
    if prediction is not None:
        if not isinstance(prediction, dict):
            raise ValueError('Invalid model proposal')
        if prediction.get('recipe') not in (*RECIPES, None):
            return {'version': VERSION, 'candidates': [], 'review_items': [review('model_recipe_unsupported',
                'The requested model recipe is not supported by this pipeline; no substitute was rendered.', details=requested)]}
        for name in ('outgoing_source_in', 'incoming_source_in', 'overlap_seconds'):
            if name in prediction and (type(prediction[name]) not in (int, float) or not math.isfinite(prediction[name]) or prediction[name] < 0):
                raise ValueError('Invalid model cue or overlap')
    try:
        tempos, fitted_target = source_tempos(records) if source_bpms is None else (list(source_bpms), None)
        target = target_bpm if target_bpm is not None else fitted_target or math.sqrt(math.prod(tempos))
        ratios = [tempo_ratio(bpm, target) for bpm in tempos]
    except ValueError as exc:
        return {'version': VERSION, 'candidates': [], 'review_items': [review('timing_unknown', str(exc))]}
    if len(tempos) != 2:
        raise ValueError('Two source tempos are required')
    pool = []
    for bars in (8, 16):
        overlap = bars*240/target
        if prediction and 'overlap_seconds' in prediction and abs(prediction['overlap_seconds']-overlap) > .25:
            continue
        spans = [regular_bar_spans(source, bars=bars) for source in sources]
        for recipe in RECIPES:
            if prediction and prediction.get('recipe') not in (None, recipe):
                continue
            fade = overlap/2 if recipe == 'protected_vocal' else 0.
            choices = [[], []]
            for side in (0, 1):
                rows = evidence[side]['vocal_activity']
                for span in spans[side]:
                    cue = span['source_cue']; ratio = ratios[side]
                    # A fixed source stretch must agree with the observed local
                    # fit, including the end of this entire overlap.
                    if abs(span['source_bpm']/tempos[side]-1)*overlap > .025:
                        continue
                    if cue < 0 or cue+overlap*ratio > sources[side]['duration_seconds']:
                        continue
                    if bars == 16 and (cue < 4*60/tempos[side] or
                            cue+(overlap+4*60/target)*ratio > sources[side]['duration_seconds']):
                        continue
                    hint_key = 'outgoing_source_in' if side == 0 else 'incoming_source_in'
                    if prediction and hint_key in prediction and abs(cue-prediction[hint_key]) > 32:
                        continue
                    quiet_start = cue+fade*ratio-TAIL_GUARD if side == 0 else cue
                    if quiet_start < 0:
                        continue
                    activity = interval_activity(rows, quiet_start, cue+overlap*ratio)
                    if activity['status'] != 'quieter_candidate':
                        continue
                    features = region_features(records[side]['effective'], cue, cue+overlap*ratio)
                    if features is None or features['rms'] < .003:
                        continue
                    preferred = (prediction or {}).get(hint_key,
                        max(0., (seconds-overlap)*ratio) if side == 0 else 0.)
                    choices[side].append({'cue': cue, 'span': span, 'activity': activity, 'features': features,
                        'structure': structural_support(evidence[side], cue), 'distance': abs(cue-preferred)})
            # Independently filter safety on each side before pairing; the
            # returned proposal count is bounded even for very long songs.
            for items in choices:
                items.sort(key=lambda c: (-.15+c['activity']['max_vocal_ratio'], -int(c['structure']), c['distance'], c['cue']))
            for a in choices[0][:12]:
                for b in choices[1][:12]:
                    energy_db = 20*math.log10(b['features']['rms']/a['features']['rms'])
                    if abs(energy_db) > 9:
                        continue
                    ca, cb = np.array(a['features']['chroma']), np.array(b['features']['chroma'])
                    denominator = float(np.linalg.norm(ca)*np.linalg.norm(cb))
                    harmonic = float(1-np.dot(ca, cb)/denominator) if denominator > 1e-8 else None
                    if harmonic is None:
                        continue
                    margin = .15-max(a['activity']['max_vocal_ratio'], b['activity']['max_vocal_ratio'])
                    score = [int(bars == 8), margin, int(a['structure'])+int(b['structure']),
                             -abs(energy_db)/9-harmonic, -(a['distance']+b['distance'])/max(seconds, 1)]
                    candidate = {'version': VERSION, 'recipe': recipe, 'bars': bars, 'overlap_seconds': overlap,
                        'fade_start_local_seconds': fade, 'incoming_gain_at_outgoing_fade': .25 if fade else 0.,
                        'source_cues': [a['cue'], b['cue']], 'source_bpms': tempos, 'target_bpm': target,
                        'source_ratios': ratios, 'sources': [deepcopy(e['reference']) for e in evidence],
                        'requested': requested, 'applied': {'recipe': recipe, 'bars': bars,
                            'overlap_seconds': overlap, 'source_cues': [a['cue'], b['cue']]},
                        'evidence': {'outgoing_quiet_guard': a['activity'], 'incoming_full_overlap': b['activity'],
                            'vocal_safety_margin': margin, 'structural_support': [a['structure'], b['structure']],
                            'energy_change_db': energy_db, 'harmonic_distance': harmonic,
                            'bar_indices': [a['span']['bar_index'], b['span']['bar_index']],
                            'phrase_completion': 'unknown; sustained quieter evidence only'},
                        'rank': score, 'rank_method': 'hard constraints then deterministic safety/context/play-length preference'}
                    candidate['id'] = digest(candidate)
                    pool.append(candidate)
    pool.sort(key=lambda candidate: (candidate['rank'], candidate['id']), reverse=True)
    chosen = []
    for recipe in RECIPES:
        first = next((c for c in pool if c['recipe'] == recipe), None)
        if first and len(chosen) < maximum:
            chosen.append(first)
    selected = {candidate['id'] for candidate in chosen}
    chosen += [candidate for candidate in pool if candidate['id'] not in selected][:maximum-len(chosen)]
    chosen.sort(key=lambda candidate: (candidate['rank'], candidate['id']), reverse=True)
    if not chosen:
        failures.append(review('no_safe_candidate',
            'No supported handoff covers the outgoing fade and two-second guard and the entire incoming overlap.',
            details={'requested': requested, 'timing_spans': [len(e['regular_spans']) for e in evidence],
                     'vocal_coverage_bins': [len(e['vocal_activity']) for e in evidence]}))
    return {'version': VERSION, 'candidates': chosen, 'review_items': failures, 'limit': maximum,
            'eligible_count': len(pool), 'requested': requested}


def compatible(previous, following, minimum_solo=4.):
    ratio = previous['source_ratios'][1]
    return (abs(previous['target_bpm']-following['target_bpm']) < 1e-8
        and abs(previous['source_bpms'][1]-following['source_bpms'][0]) < 1e-8
        and following['source_cues'][0] >= previous['source_cues'][1]+(previous['overlap_seconds']+minimum_solo)*ratio)


def plan_set(records, *, seconds=72., predictions=None, selected_ids=None):
    if len(records) < 2:
        raise ValueError('Select at least two source entries')
    if predictions is not None and len(predictions) != len(records)-1:
        raise ValueError('One model proposal per join is required')
    if selected_ids is not None and len(selected_ids) != len(records)-1:
        raise ValueError('One selected candidate per join is required')
    try:
        tempos, target = source_tempos(records)
    except ValueError as exc:
        return {'status': 'needs_review', 'plan': None, 'review_items': [review('timing_unknown', str(exc))], 'proposals': []}
    proposals = []
    for i in range(len(records)-1):
        proposal = propose_pair(records[i], records[i+1], seconds=seconds, source_bpms=tempos[i:i+2], target_bpm=target,
            prediction=predictions[i] if predictions is not None else None)
        if selected_ids is not None:
            proposal['candidates'] = [c for c in proposal['candidates'] if c['id'] == selected_ids[i]]
            if not proposal['candidates']:
                proposal['review_items'].append(review('selected_candidate_unavailable', 'The pinned candidate is stale or unsafe; no replacement was selected.'))
        for item in proposal['review_items']:
            item['join_index'] = i
        proposals.append(proposal)
    failures = [item for proposal in proposals for item in proposal['review_items']]
    if failures:
        return {'status': 'needs_review', 'plan': None, 'review_items': failures, 'proposals': proposals}
    # Dynamic selection keeps each middle song continuous. A locally best join
    # cannot force source skips or collide with the next join's automation.
    paths = [(candidate, [candidate], tuple(candidate['rank'])) for candidate in proposals[0]['candidates']]
    for i, proposal in enumerate(proposals[1:], 1):
        next_paths = []
        for candidate in proposal['candidates']:
            options = []
            for previous, path, score in paths:
                if compatible(previous, candidate):
                    duration = (candidate['source_cues'][0]-previous['source_cues'][1])/candidate['source_ratios'][0]+candidate['overlap_seconds']
                    rank = tuple(a+b for a, b in zip(score, candidate['rank']))
                    rank = (*rank[:-1], rank[-1]-abs(duration-seconds)/seconds)
                    options.append((candidate, path+[candidate], rank))
            if options:
                next_paths.append(max(options, key=lambda item: item[2]))
        paths = next_paths
        if not paths:
            return {'status': 'needs_review', 'plan': None, 'review_items': [review('middle_track_conflict',
                'Adjacent joins cannot share a continuous source interval without overlapping automation.', join=i, source=i)], 'proposals': proposals}
    def ending(candidate):
        ratio = target/tempos[-1]
        begin = candidate['source_cues'][1]
        evidence, raw = source_evidence(records[-1])
        earliest = begin+(candidate['overlap_seconds']+4.)*ratio
        preferred = begin+seconds*ratio
        boundaries = [t for t in raw['downbeats'] if t >= earliest and t < raw['duration_seconds']
            and interval_activity(evidence['vocal_activity'], max(begin, t-TAIL_GUARD), t)['status'] == 'quieter_candidate']
        return min(boundaries, key=lambda t: abs(t-preferred)) if boundaries else None
    feasible = [(last, path, score, ending(last)) for last, path, score in paths]
    feasible = [item for item in feasible if item[3] is not None]
    if not feasible:
        return {'status': 'needs_review', 'plan': None, 'review_items': [review('ending_unknown',
            'No supported quieter ending preserves the final song after its incoming join.', source=len(records)-1)], 'proposals': proposals}
    _, chosen, _, last_end = max(feasible, key=lambda item: item[2])
    sources = []
    starts = [0.]
    for i, record in enumerate(records):
        evidence, raw = source_evidence(record)
        ratio = target/tempos[i]
        begin = chosen[i-1]['source_cues'][1] if i else 0.
        if i < len(chosen):
            end = chosen[i]['source_cues'][0]+chosen[i]['overlap_seconds']*ratio
        else:
            end = last_end
        source = {'entry_id': f'entry-{i}', 'reference': evidence['reference'], 'source_in': begin, 'source_out': end,
                  'source_duration': raw['duration_seconds'], 'source_bpm': tempos[i], 'target_bpm': target,
                  'start_seconds': starts[i], 'duration_seconds': (end-begin)/ratio}
        sources.append(source)
        if i < len(chosen):
            starts.append(starts[i]+source['duration_seconds']-chosen[i]['overlap_seconds'])
    joins = []
    for i, candidate in enumerate(chosen):
        entry = starts[i+1]
        joins.append({'candidate': candidate, 'entry_seconds': entry,
            'fade_start_seconds': entry+candidate['fade_start_local_seconds'],
            'end_seconds': entry+candidate['overlap_seconds'],
            'protected_interval': [joins[-1]['end_seconds'] if joins else starts[i], entry+candidate['fade_start_local_seconds']]})
    plan = {'version': VERSION, 'pipeline': PIPELINE, 'sample_rate': 44100,
        'sources': sources, 'joins': joins, 'duration_seconds': starts[-1]+sources[-1]['duration_seconds'],
        'requested': {'seconds': seconds, 'predictions': deepcopy(predictions)}, 'listening_accepted': None}
    plan['id'] = digest(plan)
    validate_plan(plan, records)
    return {'status': 'planned', 'plan': plan, 'review_items': [], 'proposals': proposals}


def validate_plan(plan, records):
    copy = deepcopy(plan); identity = copy.pop('id', None)
    if identity != digest(copy) or plan.get('version') != VERSION or plan.get('pipeline') != PIPELINE:
        raise ValueError('Plan identity or pipeline changed')
    if len(plan['sources']) != len(records) or len(plan['joins']) != len(records)-1:
        raise ValueError('Plan must preserve every ordered entry')
    if plan['sample_rate'] != 44100 or plan['sources'][0]['source_in'] != 0 or plan['sources'][0]['start_seconds'] != 0:
        raise ValueError('Unsupported format or initial source progression')
    for i, (source, record) in enumerate(zip(plan['sources'], records)):
        evidence, _ = source_evidence(record)
        if source['reference'] != evidence['reference']:
            raise ValueError('Source evidence revision changed')
        if (source['source_duration'] != record['effective']['duration_seconds']
                or source['entry_id'] != f'entry-{i}'
                or abs(source['target_bpm']-plan['sources'][0]['target_bpm']) > 1e-8):
            raise ValueError('Source identity or fixed tempo changed')
        ratio = tempo_ratio(source['source_bpm'], source['target_bpm'])
        if not 0 <= source['source_in'] < source['source_out'] <= source['source_duration']:
            raise ValueError('Source bounds changed')
        if abs(source['duration_seconds']-(source['source_out']-source['source_in'])/ratio) > 1e-7:
            raise ValueError('Source progression changed')
        incoming = plan['joins'][i-1]['candidate']['overlap_seconds'] if i else 0.
        outgoing = plan['joins'][i]['candidate']['overlap_seconds'] if i < len(plan['joins']) else 0.
        if incoming+outgoing >= source['duration_seconds']:
            raise ValueError('Adjacent automation consumes the source')
    for i, join in enumerate(plan['joins']):
        candidate = join['candidate']; snapshot = deepcopy(candidate); identity = snapshot.pop('id', None)
        if identity != digest(snapshot) or candidate['recipe'] not in RECIPES:
            raise ValueError('Candidate recipe changed')
        # Reapply the evidence constraints rather than trusting saved scores or
        # a caller who edited a snapshot and recalculated its hash.
        eligible = propose_pair(records[i], records[i+1], seconds=plan['requested']['seconds'],
            source_bpms=candidate['source_bpms'], target_bpm=candidate['target_bpm'],
            prediction=plan['requested']['predictions'][i] if plan['requested']['predictions'] is not None else None)
        if candidate['id'] not in {c['id'] for c in eligible['candidates']}:
            raise ValueError('Candidate no longer satisfies pinned musical constraints')
        left, right = plan['sources'][i:i+2]
        if (candidate['sources'] != [left['reference'], right['reference']]
                or candidate['source_bpms'] != [left['source_bpm'], right['source_bpm']]
                or any(abs(s['target_bpm']-candidate['target_bpm']) > 1e-8 for s in (left, right))
                or abs(join['entry_seconds']-right['start_seconds']) > 1e-7
                or abs(join['end_seconds']-(left['start_seconds']+left['duration_seconds'])) > 1e-7
                or abs(join['fade_start_seconds']-join['entry_seconds']-candidate['fade_start_local_seconds']) > 1e-7
                or abs(join['end_seconds']-join['entry_seconds']-candidate['overlap_seconds']) > 1e-7
                or join['protected_interval'] != [plan['joins'][i-1]['end_seconds'] if i else 0., join['fade_start_seconds']]):
            raise ValueError('Join geometry changed')
        for side, source in enumerate((left, right)):
            cue = source['source_in']+(join['entry_seconds']-source['start_seconds'])*candidate['source_ratios'][side]
            if abs(cue-candidate['source_cues'][side]) > 1e-7:
                raise ValueError('Join source cue is discontinuous')
        if i and not compatible(plan['joins'][i-1]['candidate'], candidate):
            raise ValueError('Adjacent join source conflict')
    last = plan['sources'][-1]
    rows = source_evidence(records[-1])[0]['vocal_activity']
    if (abs(plan['duration_seconds']-last['start_seconds']-last['duration_seconds']) > 1e-7
            or interval_activity(rows, last['source_out']-TAIL_GUARD, last['source_out'])['status'] != 'quieter_candidate'):
        raise ValueError('Ending duration or quieter evidence changed')
    return plan
