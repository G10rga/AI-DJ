"""Distinct, coverage-aware musical evidence; low activity never proves a phrase ended."""
from copy import deepcopy
import hashlib
import json
import math

import numpy as np

from .bar_evidence import regular_bar_spans, VERSION as BAR_VERSION

VERSION = 'transition-evidence-1'
PROFILE = 'transition-foundation-1'
RATIO_LIMIT = .15
MASTER_FLOOR = 1e-6


def vocal_bins(vocals, master, rate, offset, start, end, *, chunk_index):
    """Use actual source/stem frames, retaining a partial tail's real coverage."""
    if (rate <= 0 or vocals.shape != master.shape or vocals.ndim != 2 or vocals.shape[1] != 2
            or not np.isfinite(vocals).all() or not np.isfinite(master).all()
            or not np.isfinite([offset, start, end]).all() or not 0 <= offset <= start < end):
        raise ValueError('Invalid vocal evidence samples or bounds')
    first = round((start-offset)*rate)
    stop = min(round((end-offset)*rate), len(master))
    rows = []
    for position in range(first, stop, max(1, round(.5*rate))):
        last = min(stop, position+round(.5*rate))
        v = vocals[position:last].astype(float)
        a = master[position:last].astype(float)
        vocal_rms = float(np.sqrt(np.mean(v*v)))
        master_rms = float(np.sqrt(np.mean(a*a)))
        ratio = vocal_rms/master_rms if master_rms > MASTER_FLOOR else None
        rows.append({'start': offset+position/rate, 'end': offset+last/rate,
                     'rms': vocal_rms, 'master_rms': master_rms, 'vocal_ratio': ratio,
                     'state': 'observed' if ratio is not None else 'unknown',
                     'active': ratio is None or ratio > RATIO_LIMIT, 'chunk_index': chunk_index})
    return rows


def validate_vocal_rows(rows):
    previous = 0.
    for row in rows:
        if not all(type(row.get(k)) in (int, float) and math.isfinite(row[k])
                   for k in ('start', 'end', 'rms', 'master_rms')):
            raise ValueError('Invalid relative vocal evidence')
        if not 0 <= row['start'] < row['end'] or row['start'] < previous-1e-6 or min(row['rms'], row['master_rms']) < 0:
            raise ValueError('Overlapping or invalid relative vocal evidence')
        previous = row['end']
        ratio = row.get('vocal_ratio')
        if row.get('state') == 'observed':
            if (type(ratio) not in (int, float) or not math.isfinite(ratio) or ratio < 0
                    or row['master_rms'] <= MASTER_FLOOR
                    or not math.isclose(ratio, row['rms']/row['master_rms'], rel_tol=1e-5, abs_tol=1e-8)):
                raise ValueError('Invalid observed vocal ratio')
        elif row.get('state') != 'unknown' or ratio is not None:
            raise ValueError('Unknown vocal evidence must remain explicitly unknown')
        if row.get('active') is not (ratio is None or ratio > RATIO_LIMIT):
            raise ValueError('Vocal activity flag conflicts with relative evidence')


def interval_activity(rows, start, end):
    """Return unknown for any gap/unobserved bin, even beside a quiet future bar."""
    if not np.isfinite([start, end]).all() or not 0 <= start < end:
        raise ValueError('Invalid vocal query interval')
    try:
        validate_vocal_rows(rows)
    except (ValueError, KeyError, TypeError):
        return {'status': 'unknown', 'reason': 'Missing or invalid relative vocal evidence'}
    selected = [row for row in rows if row['start'] < end and row['end'] > start]
    cursor = start
    ratios = []
    for row in selected:
        if row['start'] > cursor+1e-6 or row['state'] != 'observed':
            return {'status': 'unknown', 'reason': 'Vocal evidence is gapped or unknown', 'covered_until': cursor}
        cursor = max(cursor, row['end'])
        ratios.append(row['vocal_ratio'])
    if cursor < end-1e-6 or not ratios:
        return {'status': 'unknown', 'reason': 'Vocal evidence does not cover the complete interval', 'covered_until': cursor}
    return {'status': 'quieter_candidate' if max(ratios) <= RATIO_LIMIT else 'active',
            'interval_seconds': [start, end], 'max_vocal_ratio': max(ratios), 'bins': len(ratios),
            'phrase_completion': 'unknown', 'meaning': 'Estimated relative activity; MDX leakage possible'}


def quieter_passages(rows):
    validate_vocal_rows(rows)
    passages = []
    for row in rows:
        if row['state'] != 'observed' or row['vocal_ratio'] > RATIO_LIMIT:
            continue
        if passages and abs(passages[-1]['end']-row['start']) <= 1e-6:
            passages[-1]['end'] = row['end']
            passages[-1]['max_vocal_ratio'] = max(passages[-1]['max_vocal_ratio'], row['vocal_ratio'])
        else:
            passages.append({'start': row['start'], 'end': row['end'], 'status': 'candidate',
                             'max_vocal_ratio': row['vocal_ratio'], 'phrase_completion': 'unknown'})
    return passages


def build_evidence(timeline):
    """Derive on the full effective source timeline, including pinned corrections."""
    beats, downs = timeline['beats']['times'], timeline['downbeats']['times']
    source = {'beats': beats, 'downbeats': downs, 'duration_seconds': timeline['duration_seconds']}
    bars = []
    for index, (start, end) in enumerate(zip(downs, downs[1:])):
        count = sum(start-.05 <= t < end-.05 for t in beats)
        bars.append({'bar_index': index, 'start': start, 'end': end, 'beat_count': count,
                     'status': '4/4 candidate' if count == 4 else 'unknown'})
    relative = timeline.get('config', {}).get('analysis_profile') == PROFILE
    rows = deepcopy(timeline.get('vocal_activity', [])) if relative else []
    validate_vocal_rows(rows)
    structures = [{**deepcopy(section), 'status': 'candidate', 'phrase_completion': 'unknown'}
                  for section in timeline.get('sections', [])]
    return {'version': VERSION, 'bar_fit_version': BAR_VERSION,
            'beats': deepcopy(timeline['beats']), 'downbeats': deepcopy(timeline['downbeats']),
            'bars': bars, 'regular_spans': regular_bar_spans(source),
            'vocal_activity': rows, 'vocal_status': 'observed' if rows else 'unknown',
            'quieter_passages': quieter_passages(rows), 'structural_changes': structures,
            'phrase_boundaries': {'times': list(timeline['phrase_boundaries']['times']),
                                  'status': 'candidate', 'provenance': deepcopy(timeline['phrase_boundaries']['provenance']),
                                  'phrase_completion': 'unknown'},
            'coverage_intervals': [[r['start'], r['end']] for r in rows],
            'vocal_chunks': deepcopy(timeline.get('vocal_chunks', [])),
            'limitations': ['Activity/structure evidence does not establish semantic vocal completion.',
                           'Unobserved or gapped intervals remain unknown; timing seams require independent validation.']}


def foundation_evidence(record):
    from backend.app.timelines import validate_timeline, canonical
    timeline = validate_timeline(record['effective'])
    evidence = build_evidence(timeline)
    evidence['reference'] = {'source_sha256': timeline['content_hash'], 'timeline_id': record['timeline_id'],
        'track_id': record['track_id'], 'correction_revision': record['revision'],
        'effective_sha256': hashlib.sha256(canonical(timeline).encode()).hexdigest(),
        'model_config': deepcopy(timeline.get('config'))}
    return evidence
