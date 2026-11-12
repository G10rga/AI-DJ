"""Stable, gain-invariant analysis input; never changes rendered audio."""
import numpy as np

VERSION = 'context-normalized-timing-1'
CONTEXT_SECONDS = 24.
TARGET_MONO_RMS = .1
MONO_PEAK_CEILING = .98
SILENCE_RMS_FLOOR = 1e-6


def canonical_timing_input(samples):
    samples = np.asarray(samples)
    if (samples.ndim != 2 or samples.shape[1] != 2 or not len(samples) or np.iscomplexobj(samples)
            or not np.isfinite(samples).all()):
        raise ValueError('Beat analysis requires finite stereo samples')
    mono = samples.astype(np.float64).mean(axis=1)
    rms, peak = float(np.sqrt(np.mean(mono*mono))), float(np.max(np.abs(mono)))
    metadata = {'policy': VERSION, 'mono_rms_before': rms, 'mono_peak_before': peak,
                'frames': len(samples), 'target_mono_rms': TARGET_MONO_RMS,
                'mono_peak_ceiling': MONO_PEAK_CEILING}
    if rms <= SILENCE_RMS_FLOOR:
        return None, {**metadata, 'status': 'unknown', 'gain': None,
                      'reason': 'Insufficient audible mono evidence; silence was not amplified'}
    gain = min(TARGET_MONO_RMS/rms, MONO_PEAK_CEILING/peak)
    normalized = (samples*gain).astype(np.float32)
    if not np.isfinite(normalized).all():
        raise ValueError('Beat analysis normalization produced invalid samples')
    return normalized, {**metadata, 'status': 'observed', 'gain': gain}
