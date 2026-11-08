"""Bounded spectral matching. Scores describe similarity, not calibrated confidence."""
from pathlib import Path
import tempfile
import numpy as np
from scipy import signal
from scipy.io import wavfile
from .probe import run_audio

VERSION = 'reference-spectral-1'
STEP = .25
RATE = 8000
CHUNK = 40.


def spectral_features(path, duration, settings, work):
    """Decode at most 41 seconds at once; retain only 4 Hz spectral bands."""
    rows = []
    edges = np.geomspace(60, 3600, 33)
    frequencies = np.fft.rfftfreq(2048, 1/RATE)
    bands = [(frequencies >= a) & (frequencies < b) for a, b in zip(edges, edges[1:])]
    with tempfile.TemporaryDirectory(dir=work, prefix='reference-') as directory:
        pcm = Path(directory)/'chunk.wav'
        for start in np.arange(0, duration, CHUNK):
            run_audio([settings.ffmpeg, '-v', 'error', '-nostdin', '-y', '-ss', str(start),
                       '-i', str(path), '-t', str(min(CHUNK+.256, duration-start)),
                       '-ac', '1', '-ar', str(RATE), '-c:a', 'pcm_f32le', str(pcm)])
            rate, audio = wavfile.read(pcm)
            if rate != RATE or not np.isfinite(audio).all():
                raise ValueError('Invalid decoded reference audio')
            frames = max(0, min(int(CHUNK/STEP), (len(audio)-2048)//int(RATE*STEP)+1))
            for i in range(frames):
                window = audio[i*2000:i*2000+2048] * np.hanning(2048)
                power = abs(np.fft.rfft(window))**2
                rows.append([np.log(max(float(power[band].mean()), 1e-10)) for band in bands])
    if len(rows) < 8:
        raise ValueError('Reference matching requires at least two seconds of audio')
    return np.asarray(rows, dtype=np.float32)


def correlation(recording, template):
    """Per-band, time-centered normalized correlation at all valid offsets."""
    n = len(template)
    if n > len(recording):
        return np.empty(0)
    centered = template-template.mean(axis=0)
    norm = float(np.sum(centered**2))
    if norm < 1e-6:
        return np.zeros(len(recording)-n+1)
    dots = signal.fftconvolve(recording, centered[::-1], mode='valid', axes=0).sum(axis=1)
    sums = np.vstack((np.zeros((1, recording.shape[1])), np.cumsum(recording, axis=0, dtype=np.float64)))
    squares = np.concatenate(([0.], np.cumsum(np.sum(recording.astype(np.float64)**2, axis=1))))
    variance = squares[n:]-squares[:-n]-np.sum((sums[n:]-sums[:-n])**2, axis=1)/n
    scores = dots/np.sqrt(np.maximum(variance*norm, 1e-12))
    return np.where(variance > 1e-6, np.clip(scores, -1, 1), 0.)


def suggest_matches(recording, source, *, window_seconds=16., scales=None, max_windows=12):
    """Propose affine anchors: mix_seconds = offset + scale * source_seconds.

    Multiple independent windows support a hypothesis. Silent/static windows
    cannot establish a match. Abrupt edits, pitch shifts and variable tempo can
    remain unresolved; never extrapolate these anchors into audible boundaries.
    """
    if scales is None:
        scales = np.arange(.92, 1.081, .01)
    window = min(round(window_seconds/STEP), len(source))
    if window < 16:
        return []
    starts = np.unique(np.linspace(0, len(source)-window, min(max_windows, 1+(len(source)-window)//16)).astype(int))
    anchors = []
    for start in starts:
        template = source[start:start+window]
        for scale in scales:
            size = max(4, round(window*scale))
            warped = np.stack([np.interp(np.arange(size)/scale, np.arange(window), template[:, b])
                               for b in range(template.shape[1])], axis=1)
            scores = correlation(recording, warped)
            for _ in range(2):
                if not len(scores):
                    break
                index = int(np.argmax(scores))
                score = float(scores[index])
                if score < .45:
                    break
                anchors.append({'source_seconds': float(start*STEP), 'mix_seconds': index*STEP,
                                'window_seconds': window*STEP, 'scale': float(scale),
                                'similarity': score, 'offset_seconds': index*STEP-start*STEP*scale})
                scores[max(0, index-32):index+33] = -1
    hypotheses = []
    while anchors and len(hypotheses) < 3:
        groups = []
        for seed in anchors:
            group = [a for a in anchors if abs(a['offset_seconds']-seed['offset_seconds']) <= 2
                     and abs(a['scale']-seed['scale']) <= .021]
            distinct = {}
            for anchor in group:
                key = anchor['source_seconds']
                if key not in distinct or anchor['similarity'] > distinct[key]['similarity']:
                    distinct[key] = anchor
            group = list(distinct.values())
            groups.append((len(group), float(np.mean([a['similarity'] for a in group])), group))
        _, _, group = max(groups, key=lambda g: (g[0], g[1]))
        strongest = max(group, key=lambda a: a['similarity'])
        hypotheses.append({'offset_seconds': strongest['offset_seconds'], 'scale': strongest['scale'],
                           'supporting_windows': len(group), 'similarity': float(np.mean([a['similarity'] for a in group])),
                           'status': 'needs_review', 'anchors': sorted(group, key=lambda a: a['source_seconds'])})
        anchors = [a for a in anchors if abs(a['offset_seconds']-strongest['offset_seconds']) > 4]
    return hypotheses


def ordered_suggestions(tracks):
    """Choose a monotonic *proposal* sequence, allowing unresolved entries.

    The same source may occur twice. Its two occurrences must have distinct,
    increasing recording anchors. Never force a match merely to fill the list.
    """
    states = [(0., -1., [])]
    for track in tracks:
        options = []
        for alternative in track['alternatives']:
            for index, hypothesis in enumerate(alternative['hypotheses']):
                if (hypothesis['supporting_windows'] < hypothesis.get('minimum_supporting_windows', 2)
                        or hypothesis['similarity'] < .5):
                    continue
                center = float(np.median([a['mix_seconds']+a['window_seconds']*a['scale']/2
                                          for a in hypothesis['anchors']]))
                options.append((center, 1+hypothesis['similarity']+.1*min(5, hypothesis['supporting_windows']),
                                {'source_hash': alternative['source_hash'], 'hypothesis_index': index,
                                 'anchor_mix_seconds': center, 'status': 'needs_review'}))
        following = [(score, last, path+[None]) for score, last, path in states]
        for center, weight, choice in options:
            compatible = [s for s in states if center > s[1]+2]
            if compatible:
                score, _, path = max(compatible, key=lambda s: s[0])
                following.append((score+weight, center, path+[choice]))
        # One best state per ending anchor; skipping preserves that anchor.
        unique = {}
        for state in following:
            if state[1] not in unique or state[0] > unique[state[1]][0]:
                unique[state[1]] = state
        states = list(unique.values())
    return max(states, key=lambda s: s[0])[2]
