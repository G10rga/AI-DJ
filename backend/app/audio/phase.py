"""Measure periodic low-frequency attacks in rendered PCM, after stretching.

This measures pulse phase, not musical downbeats or phrase alignment.
"""
import wave
import numpy as np
from scipy.signal import butter, sosfiltfilt, find_peaks


def pulse_grid(path, start, seconds, period):
    with wave.open(str(path), 'rb') as audio:
        rate = audio.getframerate()
        audio.setpos(round(start * rate))
        samples = np.frombuffer(audio.readframes(round(seconds * rate)), dtype='<i2')
        samples = samples.reshape(-1, audio.getnchannels()).mean(axis=1) / 32768
    if len(samples) < rate * 2:
        raise ValueError('Insufficient audio to measure pulse alignment')
    filtered = sosfiltfilt(butter(3, [70, 130], btype='bandpass', fs=rate, output='sos'), samples)
    hop = max(1, round(rate * .002))
    envelope = np.sqrt(np.mean(filtered[:len(filtered)//hop*hop].reshape(-1, hop)**2, axis=1))
    attacks = np.maximum(0, envelope - np.roll(envelope, 5))
    attacks[:5] = 0
    # Do not discard kicks simply because a louder syncopation occurs nearby.
    peaks, properties = find_peaks(attacks, distance=round(.08 * rate/hop),
                                  prominence=float(np.max(attacks)) * .08)
    times = peaks * hop / rate
    weights = properties['prominences']
    keep = (times > .3) & (times < seconds - .03)
    times, weights = times[keep], weights[keep]
    if len(times) < 8 or float(np.sum(weights)) <= 1e-9:
        raise ValueError('No reliable low-frequency pulse train in overlap')
    # Fit a narrow cluster of individual attacks. A circular mean of all events
    # can lie between kick and bass attacks where no actual drum occurs.
    best = None
    for candidate_period in np.linspace(period * .99, period * 1.01, 401):
        phases = times % candidate_period
        distances = (phases[:, None] - phases[None, :] + candidate_period/2) % candidate_period - candidate_period/2
        scores = np.sum(np.exp(-.5 * (distances/.008)**2) * weights[:, None], axis=0)
        index = int(np.argmax(scores))
        if best is None or scores[index] > best[0]:
            best = (float(scores[index]), float(candidate_period), float(phases[index]))
    _, fitted, phase = best
    residual = (times - phase + fitted/2) % fitted - fitted/2
    inliers = abs(residual) < .022
    cycles = np.round((times[inliers] - phase) / fitted)
    if len(np.unique(cycles)) < 8:
        raise ValueError('Insufficient individual attacks support the pulse grid')
    fitted, phase = np.polyfit(cycles, times[inliers], 1, w=weights[inliers])
    residual = times[inliers] - (cycles * fitted + phase)
    coverage = float(len(np.unique(cycles)) / (seconds/fitted))
    p90 = float(np.percentile(abs(residual), 90))
    if coverage < .7 or p90 > .015 or abs(fitted/period - 1) > .01:
        raise ValueError('Individual drum attacks do not support a stable pulse grid; choose another region')
    return {'period_seconds': float(fitted), 'phase_seconds': float(phase % fitted),
            'attack_coverage': coverage, 'attack_error_p90_seconds': p90,
            'matched_attacks_seconds': times[inliers].tolist()}


def compare_grids(first, second, seconds):
    period = (first['period_seconds'] + second['period_seconds']) / 2
    offset = (first['phase_seconds'] - second['phase_seconds'] + period/2) % period - period/2
    drift = (second['period_seconds'] / first['period_seconds'] - 1) * seconds
    return {'incoming_delay_seconds': float(offset), 'drift_seconds': float(drift)}


def check_overlap_windows(first_path, second_path, transition, overlap, bpm, window=16.0):
    """Reject local phase slips that an early whole-grid fit would miss."""
    checks = []
    for offset in np.arange(0, overlap, window):
        span = min(window, overlap-float(offset))
        if span < 8 * 60/bpm:
            continue
        first = pulse_grid(first_path, transition+float(offset), span, 60/bpm)
        second = pulse_grid(second_path, float(offset), span, 60/bpm)
        comparison = compare_grids(first, second, span)
        if abs(comparison['incoming_delay_seconds']) > .015 or abs(comparison['drift_seconds']) > .025:
            raise ValueError(f'Beat mismatch in overlap window starting at {offset:.1f}s')
        checks.append({'overlap_offset_seconds': float(offset), 'window_seconds': span, **comparison})
    return checks
