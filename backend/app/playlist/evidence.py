"""Cache beat-synchronous measurements against exact source and grid revisions."""
import json
import subprocess

import numpy as np
from scipy.signal import butter, sosfilt

from .planner import digest, evidence, key_name, corrected_grid

VERSION = 'playlist-beat-features-3'
RATE = 12000


def cached_evidence(source, record, correction, settings):
    key = digest({'version': VERSION, 'hash': source['content_hash'], 'timeline': record['timeline_id'],
                  'revision': record['revision'], 'correction': correction, 'decoder': settings.ffmpeg})
    directory = settings.data_root/'cache/playlist-evidence'
    directory.mkdir(parents=True, exist_ok=True)
    target = directory/(key+'.json')
    if target.is_file():
        return json.loads(target.read_text(encoding='utf-8'))
    result = evidence(record, correction)
    pcm = subprocess.run([settings.ffmpeg, '-v', 'error', '-nostdin', '-i', source['path'],
                          '-ac', '1', '-ar', str(RATE), '-f', 'f32le', '-'],
                         capture_output=True, check=True, timeout=180).stdout
    samples = np.frombuffer(pcm, dtype='<f4')
    bass = sosfilt(butter(2, [30, 180], fs=RATE, btype='bandpass', output='sos'), samples)
    rows, previous_spectrum = [], None
    beats, _ = corrected_grid(record['effective'], correction)
    for start, end in zip(beats, beats[1:]):
        left, right = max(0, round(start*RATE)), min(len(samples), round(end*RATE))
        if right-left < 128:
            continue
        block = samples[left:right]
        power = abs(np.fft.rfft(block*np.hanning(len(block)), n=8192))**2
        freqs = np.fft.rfftfreq(8192, 1/RATE)
        good = (freqs >= 45) & (freqs <= 3500)
        pitches = np.rint(69+12*np.log2(freqs[good]/440)).astype(int)%12
        chroma = np.bincount(pitches, power[good], minlength=12)
        chroma /= max(chroma.sum(), 1e-12)
        spectrum = np.array([np.sum(power[(freqs>=lo) & (freqs<hi)])
                             for lo, hi in zip((0, 80, 180, 380, 800, 1600, 3200), (80, 180, 380, 800, 1600, 3200, 6001))])
        spectrum /= max(spectrum.sum(), 1e-12)
        change = .5*float(np.sum(abs(spectrum-previous_spectrum))) if previous_spectrum is not None else 0.
        previous_spectrum = spectrum
        rms = float(np.sqrt(np.mean(block**2)))
        rows.append({'start':float(start), 'end':float(end), 'rms':rms,
                     'loudness_dbfs':float(20*np.log10(max(rms, 1e-9))),
                     'bass_rms':float(np.sqrt(np.mean(bass[left:right]**2))),
                     'chroma':chroma.tolist(), 'spectral_change':change})
    result.update(id=key, features=rows, key=key_name(rows))
    result['reference']['feature_version'] = VERSION
    # Keep learned embedding boundary proposals and add corroborating acoustic changes.
    if rows:
        threshold = max(.25, float(np.percentile([r['spectral_change'] for r in rows], 92)))
        for marker in result['downbeats']:
            nearest = min(rows, key=lambda r: abs(r['start']-marker))
            if nearest['spectral_change'] >= threshold:
                result['sections'].append({'time':marker, 'evidence':'beat-synchronous spectral change'})
    staged = target.with_suffix('.tmp')
    staged.write_text(json.dumps(result, allow_nan=False), encoding='utf-8')
    staged.replace(target)
    return result
