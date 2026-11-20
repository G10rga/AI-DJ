"""Compare independently observed markers with a planned, nonuniform clock."""
import numpy as np


def compare_markers(expected, observed, tolerance=.035, *, downbeats=False, human_phase=False, half_bars=None):
    expected = np.asarray(expected, dtype=float)
    observed = np.asarray(observed, dtype=float)
    if len(expected) < 2 or len(observed) < 2:
        return {'status': 'uncertain', 'reason': 'Too few independent markers'}
    # Cue boundaries can remove a detector event. Interior events must be present.
    scoped = observed[(observed >= expected[0]-tolerance) & (observed <= expected[-1]+tolerance)]
    interior = expected[1:-1]
    target = interior if len(interior) >= 2 else expected
    distances = abs(target[:, None]-observed[None, :])
    offsets = observed[distances.argmin(axis=1)]-target
    coverage = float(np.mean(abs(offsets) <= tolerance))
    extra_times = scoped[np.min(abs(scoped[:, None]-expected[None, :]), axis=1) > tolerance]
    extras = len(extra_times)
    if len(target) == 3 and len(interior) == 1 and abs(offsets[1]) <= tolerance:
        coverage = max(coverage, min(1., np.count_nonzero(abs(offsets)<=tolerance)/2))
    offset = float(np.median(offsets))
    period = float(np.median(np.diff(expected)))
    stable_offset = (len(offsets)>=3 and abs(offset)>tolerance and
                     float(np.max(abs(offsets-offset)))<=max(tolerance, .06*period))
    nearby = observed[(observed >= expected[0]-period*.1) & (observed <= expected[-1]+period*.1)]
    measured_period = float(np.median(np.diff(nearby))) if len(nearby)>=4 else None
    octave_error = measured_period is not None and (1.8 < measured_period/period < 2.2 or .44 < measured_period/period < .56)
    if downbeats and extras and coverage >= .9:
        half_bars = (expected[1:] + expected[:-1])/2 if half_bars is None else np.asarray(half_bars)
        if np.all(np.min(abs(extra_times[:, None]-half_bars[None, :]), axis=1) <= tolerance):
            return {'status':'aligned' if human_phase else 'uncertain', 'matched_fraction':coverage,
                    'extra_markers':extras, 'median_offset_seconds':offset, 'tolerance_seconds':tolerance,
                    'reason':'Human bar phase confirmed; detector also reports half bars' if human_phase
                             else 'Detector reports both full and half bars; confirm bar phase'}
    status = 'aligned' if coverage >= .9 and not extras else 'mismatch' if stable_offset or octave_error else 'uncertain'
    return {'status':status, 'matched_fraction':coverage, 'extra_markers':extras,
            'median_offset_seconds':offset, 'tolerance_seconds':tolerance,
            'reason': 'Consistent phase shift' if stable_offset else 'Half or double time' if octave_error else
                      'Incomplete or inconsistent detector evidence' if status=='uncertain' else None}
