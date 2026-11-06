"""Source-bounded cue candidates supported by regional pulse/energy evidence."""
import math
import numpy as np
from backend.app.models import Excerpt


def support(analysis, start, end):
    if end <= start:
        return 1.0
    windows = analysis.get('rhythm', {}).get('windows', [])
    covered = sum(max(0, min(end, w['end'])-max(start, w['start'])) for w in windows)
    return float(min(1, covered/(end-start)))


def regional_energy(analysis, start, end):
    values = np.asarray(analysis.get('energy') or [0], dtype=float)
    step = float(analysis.get('energy_frame_seconds', analysis['audio']['duration']/len(values)))
    left = max(0, min(len(values)-1, int(start/max(step, 1e-8))))
    right = max(left+1, min(len(values), int(end/max(step, 1e-8))))
    return float(np.mean(values[left:right]))


def choose_excerpt(entry, target, requested_seconds, incoming, outgoing):
    analysis = entry['analysis']
    duration = float(analysis['audio']['duration'])
    rhythm = analysis.get('rhythm', {})
    bpm = float(rhythm['bpm']) if rhythm.get('bpm') else 120.0
    ratio = target/bpm
    available = duration/ratio
    minimum = min(available, max(min(requested_seconds*.5, available), incoming+outgoing+8*60/target))
    windows = rhythm.get('windows', [])
    starts = {0.0}
    for window in windows:
        candidate = float(window['start']+window['phase'])
        if (duration-candidate)/ratio >= minimum:
            starts.add(candidate)
    candidates = []
    for start in sorted(starts):
        maximum_end = min(duration, start+requested_seconds*ratio)
        ends = {maximum_end}
        ends.update(float(w['end']) for w in windows if start+minimum*ratio <= w['end'] <= maximum_end)
        for end in sorted(ends):
            # Bar-length geometry uses a pulse anchor; it is not a verified
            # downbeat or phrase label.
            bars = math.floor((end-start)*bpm/240)
            aligned_end = start+bars*240/bpm if bars else end
            if aligned_end <= start:
                continue
            output = (aligned_end-start)/ratio
            if output < minimum-2*60/target and available >= minimum:
                continue
            incoming_end = min(aligned_end, start+incoming*ratio)
            outgoing_start = max(start, aligned_end-outgoing*ratio)
            in_support = support(analysis, start, incoming_end) if incoming else 1.0
            out_support = support(analysis, outgoing_start, aligned_end) if outgoing else 1.0
            body = regional_energy(analysis, start, aligned_end)
            entry_energy = regional_energy(analysis, start, incoming_end) if incoming else body
            exit_energy = regional_energy(analysis, outgoing_start, aligned_end) if outgoing else body
            score = 3*(in_support+out_support)+.15*min(1, output/requested_seconds)
            if body > 1e-8:
                score -= .1*(abs(math.log2(max(entry_energy, 1e-8)/body))+abs(math.log2(max(exit_energy, 1e-8)/body)))
            excerpt = Excerpt(entry['entry_id'], float(start), float(aligned_end), duration, bpm, float(target))
            candidates.append((score, output, -start, excerpt, in_support, out_support, entry_energy, exit_energy))
    if not candidates:
        end = min(duration, requested_seconds*ratio)
        excerpt = Excerpt(entry['entry_id'], 0.0, float(end), duration, bpm, float(target))
        return excerpt, {'incoming_support': 0.0, 'outgoing_support': 0.0,
                         'entry_energy': regional_energy(analysis, 0, end), 'exit_energy': regional_energy(analysis, 0, end)}
    best = max(candidates, key=lambda item: item[:3])
    return best[3], {'incoming_support': best[4], 'outgoing_support': best[5],
                     'entry_energy': best[6], 'exit_energy': best[7]}
