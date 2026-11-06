"""Cached local pulse evidence, separate from musical downbeat detection."""
import hashlib
import json
import wave
from pathlib import Path
from uuid import uuid4
import numpy as np
from scipy.signal import butter, sosfiltfilt, correlate, find_peaks
from backend.app.audio.phase import pulse_grid
from backend.app.audio.probe import run_audio

VERSION = 'regional-rhythm-1'
WINDOW = 16.0


def tempo_candidates(path, start, seconds, global_bpm):
    with wave.open(str(path), 'rb') as audio:
        rate = audio.getframerate()
        audio.setpos(round(start*rate))
        samples = np.frombuffer(audio.readframes(round(seconds*rate)), dtype='<i2').astype(float)/32768
    filtered = sosfiltfilt(butter(3, [70, 130], fs=rate, btype='bandpass', output='sos'), samples)
    hop = round(rate*.002)
    envelope = np.sqrt(np.mean(filtered[:len(filtered)//hop*hop].reshape(-1, hop)**2, axis=1))
    onset = np.maximum(0, envelope-np.roll(envelope, 5))
    onset[:5] = 0
    ac = correlate(onset, onset, mode='full', method='fft')[len(onset)-1:]
    peaks, _ = find_peaks(ac)
    frame_rate = rate/hop
    peaks = [int(p) for p in peaks if frame_rate*60/145 <= p <= frame_rate*60/90]
    peaks.sort(key=lambda p: -ac[p])
    candidates = []
    for index in peaks:
        denominator = ac[index-1]-2*ac[index]+ac[index+1]
        refined = index + (.5*(ac[index-1]-ac[index+1])/denominator if abs(denominator) > 1e-12 else 0)
        bpm = 60*frame_rate/refined
        if all(abs(np.log(bpm/previous[0])) > .015 for previous in candidates):
            candidates.append((float(bpm), float(ac[index]/max(ac[0], 1e-12))))
        if len(candidates) == 3:
            break
    if global_bpm and np.isfinite(global_bpm) and 40 <= global_bpm <= 220:
        if all(abs(np.log(global_bpm/previous[0])) > .01 for previous in candidates):
            index = round(frame_rate*60/global_bpm)
            candidates.append((float(global_bpm), float(ac[index]/max(ac[0], 1e-12))))
    return candidates, float(np.sqrt(np.mean(samples**2)))


def analyze_rhythm(path, analysis, settings, storage):
    config = f'{VERSION}:{analysis.get("config", "")}:{analysis.get("bpm")}'
    key = hashlib.sha256(f'{config}:{analysis["content_hash"]}'.encode()).hexdigest()
    cache = storage.path('analysis', 'rhythm-'+key+'.json')
    if cache.exists():
        return json.loads(cache.read_text(encoding='utf-8'))
    duration = analysis['audio']['duration']
    windows = []
    with storage.temporary_directory() as temporary:
        pcm = temporary/'pulse.wav'
        run_audio([settings.ffmpeg, '-v', 'error', '-nostdin', '-i', str(path), '-ac', '1', '-ar', '44100',
                   '-c:a', 'pcm_s16le', str(pcm)])
        for start in np.arange(0, max(0, duration-7.9), WINDOW):
            span = min(WINDOW, duration-float(start))
            candidates, rms = tempo_candidates(pcm, float(start), span, analysis.get('bpm'))
            valid = []
            for bpm, strength in candidates:
                try:
                    grid = pulse_grid(pcm, float(start), span, 60/bpm)
                except ValueError:
                    continue
                score = grid['attack_coverage']-8*grid['attack_error_p90_seconds']+.2*strength
                valid.append((score, grid))
            if valid:
                _, grid = max(valid, key=lambda candidate: candidate[0])
                windows.append({'start': float(start), 'end': float(start)+span,
                                'bpm': 60/grid['period_seconds'], 'phase': grid['phase_seconds'],
                                'coverage': grid['attack_coverage'], 'error': grid['attack_error_p90_seconds'], 'rms': rms})
    if windows:
        # Prefer a tempo supported by several regions; retain other regional
        # estimates as evidence rather than silently altering their grids.
        winner = max(windows, key=lambda w: sum(x['coverage'] for x in windows if abs(np.log(x['bpm']/w['bpm'])) < .015))
        supported = [w for w in windows if abs(np.log(w['bpm']/winner['bpm'])) < .01]
        bpm = float(np.median([w['bpm'] for w in supported]))
        if abs(bpm-round(bpm)) < .04:
            bpm = float(round(bpm))
        confidence = float(np.mean([w['coverage'] for w in supported]))
        reliable = len(supported) >= 2 or (duration < 32 and len(supported) == 1)
    else:
        supported, bpm, confidence, reliable = [], None, 0.0, False
    result = {'version': VERSION, 'bpm': bpm, 'confidence': confidence, 'reliable': reliable,
              'windows': supported, 'all_windows': windows, 'duration': duration,
              'valid_fraction': len(supported)/max(1, int(np.ceil(duration/WINDOW))),
              'warnings': ['Local pulse evidence does not establish musical downbeats or vocal phrase boundaries.']}
    temporary = cache.with_name(cache.name+'.'+uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(result, allow_nan=False), encoding='utf-8')
    temporary.replace(cache)
    return result
