"""Observed local tempo fits on source-wide markers, never a fabricated beat grid."""
import math
import numpy as np

VERSION = 'observed-local-bars-1'


def regular_bar_spans(source, anchor=None, *, bars=8, minimum_start=0.,
                      after_span_context=0., maximum_distance=20.):
    """Fit multiple observed beats; bar indices refer to the full marker sequence.

    Supply absolute source markers after chunk merging (and human corrections),
    rather than restarting bar numbers per inference chunk. Missing/irregular
    evidence produces no fit; these spans do not establish phrase completion.
    """
    if type(bars) is not int or bars < 1:
        raise ValueError('Invalid bar count')
    parameters = [source['duration_seconds'], minimum_start, after_span_context, maximum_distance]
    if anchor is not None:
        parameters.append(anchor)
    if not all(math.isfinite(v) for v in parameters) or source['duration_seconds'] <= 0:
        raise ValueError('Invalid span bounds')
    if min(minimum_start, after_span_context, maximum_distance) < 0:
        raise ValueError('Invalid span bounds')
    beats = np.asarray(source['beats'], dtype=float)
    downs = np.asarray(source['downbeats'], dtype=float)
    for values in (beats, downs):
        if (values.ndim != 1 or not np.isfinite(values).all() or np.any(np.diff(values) <= 0)
                or np.any(values < 0) or np.any(values >= source['duration_seconds'])):
            raise ValueError('Invalid source marker sequence')
    candidates = []
    for i in range(len(downs)-bars):
        selected = downs[i:i+bars+1]
        if selected[0] < minimum_start or selected[-1]+after_span_context > source['duration_seconds']:
            continue
        counts = [int(np.sum((beats >= left-.05) & (beats < right-.05)))
                  for left, right in zip(selected, selected[1:])]
        if counts != [4]*bars:
            continue
        first = int(np.argmin(abs(beats-selected[0])))
        observed = beats[first:first+bars*4+1]
        if len(observed) != bars*4+1 or np.any(abs(observed[::4]-selected) > .04):
            continue
        period, origin = np.polyfit(np.arange(len(observed)), observed, 1)
        residual = abs(observed-(origin+np.arange(len(observed))*period))
        # Retain the validated house range; half/double-tempo fits stay unknown.
        if not .4 < period < .6 or np.percentile(residual, 90) > .015 or residual.max() > .04:
            continue
        distance = float(abs(origin-anchor)) if anchor is not None else 0.
        if anchor is not None and distance > maximum_distance:
            continue
        candidates.append({'version': VERSION, 'bar_index': i, 'source_cue': float(origin),
                           'source_bpm': float(60/period), 'period_seconds': float(period),
                           'fit_p90_seconds': float(np.percentile(residual, 90)),
                           'fit_max_seconds': float(residual.max()),
                           'observed_beats': observed.tolist(), 'observed_downbeats': selected.tolist(),
                           'distance_from_old_cue_seconds': distance, 'bars': bars,
                           'phrase_status': 'candidate; completion unknown'})
    return sorted(candidates, key=lambda item: (item['distance_from_old_cue_seconds'], item['source_cue']))
