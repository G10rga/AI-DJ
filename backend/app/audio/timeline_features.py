"""Bounded DSP evidence and conservative musical boundary proposals."""
import numpy as np
from scipy.signal import butter, sosfilt, find_peaks


def chunk_windows(duration, core=30., context=4.):
    for start in np.arange(0, duration, core):
        end = min(duration, float(start)+core)
        yield float(start), end, max(0., float(start)-context), min(duration, end+context)


def merge_markers(chunks, tolerance=.07):
    """Merge only duplicate seam detections; never invent a periodic beat grid."""
    result = []
    for value in sorted(float(x) for chunk in chunks for x in chunk):
        if not result or value-result[-1] > tolerance:
            result.append(round(value, 5))
    return result


def feature_bins(samples, rate, start):
    mono = samples.mean(axis=1) if samples.ndim == 2 else samples
    bass = sosfilt(butter(3, [30, 180], btype='bandpass', fs=rate, output='sos'), mono)
    rows = []
    for offset in range(0, len(mono), rate):
        part = mono[offset:offset+rate]
        if not len(part):
            continue
        hop = max(1, rate//50)
        envelope = np.array([np.sqrt(np.mean(part[j:j+hop]**2)) for j in range(0, len(part), hop)])
        rises = np.maximum(0, np.diff(envelope, prepend=envelope[0]))
        peaks, _ = find_peaks(rises, height=max(.005, float(np.median(rises)+2*np.std(rises))), distance=4)
        spectrum = np.abs(np.fft.rfft(part*np.hanning(len(part))))**2
        frequencies = np.fft.rfftfreq(len(part), 1/rate)
        selected = frequencies > 40
        pitches = np.rint(69+12*np.log2(frequencies[selected]/440)).astype(int) % 12
        chroma = np.bincount(pitches, weights=spectrum[selected], minlength=12)
        chroma /= max(float(chroma.sum()), 1e-12)
        rows.append({'start': start+offset/rate, 'end': start+(offset+len(part))/rate,
                     'rms': float(np.sqrt(np.mean(part**2))), 'peak': float(np.max(np.abs(part))),
                     'bass_rms': float(np.sqrt(np.mean(bass[offset:offset+len(part)]**2))),
                     'transient_peaks_per_second': len(peaks)/(len(part)/rate),
                     'chroma': chroma.tolist()})
    return rows


def section_candidates(embeddings, features, downbeats):
    if len(embeddings) < 3:
        return []
    vectors = np.array([row['vector'] for row in embeddings])
    unit = vectors/np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
    novelty = 1-np.sum(unit[1:]*unit[:-1], axis=1)
    median = float(np.median(novelty))
    threshold = max(.08, median+2*float(np.median(abs(novelty-median))))
    proposed = []
    last = -10.
    for i, score in enumerate(novelty, 1):
        if score < threshold:
            continue
        time = embeddings[i]['start']
        nearby = [t for t in downbeats if abs(t-time) <= 2]
        if nearby:
            time = min(nearby, key=lambda t: abs(t-time))
        if time-last < 8:
            continue
        before = [f['rms'] for f in features if time-5 <= f['start'] < time]
        after = [f['rms'] for f in features if time <= f['start'] < time+5]
        ratio = float(np.mean(after))/max(float(np.mean(before)), 1e-8) if before and after else None
        # Similarity to an earlier window is evidence of repetition, not a section name.
        repeat = float(np.max(unit[:max(1, i-2)]@unit[i])) if i > 2 else None
        proposed.append({'time': time, 'embedding_change': float(score), 'energy_ratio': ratio,
                         'earlier_similarity': repeat, 'label': 'section-change candidate', 'confidence': None,
                         'provenance': 'MERT cosine novelty; median/MAD threshold; nearest downbeat within 2s'})
        last = time
    return proposed
