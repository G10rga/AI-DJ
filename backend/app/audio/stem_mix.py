"""Rule-based mixing of separated voices and instrumentals; no learned curves."""
import numpy as np
import math
import soundfile as sf
from scipy.ndimage import binary_closing
from .recipes import eq_swap_graph


def vocal_regions(path):
    samples, rate = sf.read(path, dtype='float32', always_2d=True)
    hop = round(rate * .05)
    count = len(samples)//hop
    rms = np.sqrt(np.mean(samples[:count*hop].reshape(count, hop, -1)**2, axis=(1, 2)))
    threshold = max(.006, float(np.percentile(rms, 90)) * .14)
    active = binary_closing(rms > threshold, structure=np.ones(7), border_value=0)
    boundaries = np.diff(np.pad(active.astype(int), (1, 1)))
    starts, ends = np.flatnonzero(boundaries == 1), np.flatnonzero(boundaries == -1)
    return [(float(start*.05), float(end*.05)) for start, end in zip(starts, ends) if end-start >= 3], threshold


def vocal_schedule(outgoing, incoming, transition, overlap, bpm, fade_bars=4):
    beat = 60/bpm
    if fade_bars not in {2, 4, 8}:
        raise ValueError('Choose a two-, four-, or eight-bar vocal fade')
    fade_seconds = fade_bars * 4 * beat
    a_regions, a_threshold = vocal_regions(outgoing)
    b_regions, b_threshold = vocal_regions(incoming)
    # Leave room for the incoming phrase before the overlap ends, rather than
    # greedily holding A until the middle and missing B's next vocal entry.
    desired_end = transition + overlap * .375
    candidates = []
    for index, (_, end) in enumerate(a_regions):
        following = a_regions[index+1][0] if index+1 < len(a_regions) else transition+overlap
        gap = following-end
        if transition+4*beat < end < transition+overlap-3*beat and gap >= .35:
            fade_end = end+.03+min(.25, gap/2)
            candidates.append((abs(end-desired_end), max(0, fade_end-fade_seconds), fade_seconds))
    if candidates:
        _, a_start, a_duration = min(candidates)
        outgoing_reason = 'long vocal fade ending in a detected low-energy gap'
    else:
        a_start, a_duration = max(0, desired_end-fade_seconds), fade_seconds
        outgoing_reason = f'no suitable vocal gap detected; gradual {fade_bars}-bar vocal fade'
    earliest_b = a_start+a_duration-transition+beat
    incoming_candidates = []
    for index, (start, _) in enumerate(b_regions):
        preceding = b_regions[index-1][1] if index else 0.0
        gap = start-preceding
        # Begin quietly at the entry and build through the vocal phrase. The
        # previous sub-second gain restoration was effectively a vocal cut-in.
        if gap >= .35 and start >= earliest_b and start < overlap+8*beat:
            incoming_candidates.append((start, start, fade_seconds))
    if incoming_candidates:
        _, b_start, b_duration = min(incoming_candidates)
        incoming_reason = f'gradual {fade_bars}-bar fade from a detected vocal entry after a gap'
    else:
        b_start, b_duration = max(earliest_b, overlap*.75), fade_seconds
        incoming_reason = f'no suitable entry gap detected; gradual {fade_bars}-bar vocal fade'
    return {'outgoing_fade_start_seconds': a_start, 'outgoing_fade_duration_seconds': a_duration,
            'incoming_fade_start_local_seconds': b_start, 'incoming_fade_duration_seconds': b_duration,
            'incoming_fade_start_seconds': transition+b_start,
            'outgoing_reason': outgoing_reason, 'incoming_reason': incoming_reason,
            'fade_bars': fade_bars, 'outgoing_curve': 'qsin', 'incoming_curve': 'hsin',
            'vocal_eq': {'split_hz': 1800, 'mode': 'close_outgoing_highs_and_open_incoming_highs'},
            'activity_thresholds_rms': [a_threshold, b_threshold],
            'outgoing_vocal_regions_seconds': a_regions, 'incoming_vocal_regions_local_seconds': b_regions,
            'semantic_phrase_detection': False}


def stem_pair_graph(gains, first_seconds, second_seconds, overlap, bpm, phase, schedule, blend_profile='standard'):
    if blend_profile not in {'standard', 'long_groove', 'controlled'}:
        raise ValueError('Unknown instrumental blend profile')
    graph, recipe = eq_swap_graph(gains, first_seconds, second_seconds, overlap, bpm, phase,
                                  long_blend=blend_profile == 'long_groove', controlled_blend=blend_profile == 'controlled')
    graph = graph.replace('[out]', '[bed]')
    transition = first_seconds-overlap
    expected = first_seconds+second_seconds-overlap
    a_start, a_duration = schedule['outgoing_fade_start_seconds'], schedule['outgoing_fade_duration_seconds']
    b_start, b_duration = schedule['incoming_fade_start_local_seconds'], schedule['incoming_fade_duration_seconds']
    if not all(math.isfinite(x) for x in (a_start, a_duration, b_start, b_duration)) or min(a_start, b_start) < 0 or min(a_duration, b_duration) <= 0 or a_start+a_duration > transition+b_start or a_start+a_duration > first_seconds or b_start+b_duration > second_seconds:
        raise ValueError('Vocal handoff must have finite positive fades without simultaneous voices')
    # Apply the same crossover phase response to voices and instrumentals, so
    # unchanged stems reconstruct consistently outside the handoff.
    for index in (2, 3):
        graph += f';[{index}:a]volume={gains[index-2]:.9f},acrossover=split=180 1800:order=4th[v{index}l][v{index}m][v{index}h]'
        high = f'v{index}h'
        if schedule.get('vocal_eq'):
            direction, start, duration = ('out', a_start, a_duration) if index == 2 else ('in', b_start, b_duration)
            graph += f';[{high}]afade=t={direction}:st={start:.9f}:d={duration:.9f}:curve=hsin[v{index}heq]'
            high = f'v{index}heq'
        graph += f';[v{index}l][v{index}m][{high}]amix=inputs=3:normalize=0,asetpts=N/SR/TB[voice{index}]'
    outgoing_curve = schedule.get('outgoing_curve', 'hsin')
    incoming_curve = schedule.get('incoming_curve', 'hsin')
    if outgoing_curve not in {'hsin', 'qsin'} or incoming_curve not in {'hsin', 'qsin'}:
        raise ValueError('Unsupported vocal fade curve')
    graph += (f';[voice2]afade=t=out:st={a_start:.9f}:d={a_duration:.9f}:curve={outgoing_curve}[voiceA];'
              f'[voice3]afade=t=in:st={b_start:.9f}:d={b_duration:.9f}:curve={incoming_curve},'
              f'adelay={round(transition*44100)}S:all=1[voiceB];'
              f'[bed][voiceA][voiceB]amix=inputs=3:normalize=0:duration=longest,asetpts=N/SR/TB,'
              f'afade=t=in:d=0.01,afade=t=out:st={expected-.01:.9f}:d=0.01,atrim=duration={expected:.9f}[out]')
    recipe.update(name='vocal_stem_handoff', vocal_schedule=schedule, model_based_separation=True)
    return graph, recipe
