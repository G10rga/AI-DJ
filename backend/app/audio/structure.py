"""Conservative phrase candidates, not a downbeat detector."""
import numpy as np


def phrase_candidates(beats: np.ndarray, energy: np.ndarray, frame_seconds: float) -> list[dict]:
    candidates = []
    for index in range(0, len(beats), 32):
        time = float(beats[index])
        frame = min(len(energy) - 1, max(0, int(time / frame_seconds)))
        before = float(np.mean(energy[max(0, frame - 16):frame + 1]))
        after = float(np.mean(energy[frame:min(len(energy), frame + 17)]))
        contrast = abs(after - before) / max(before, after, 1e-8)
        candidates.append({"seconds": round(time, 4), "beat_index": index,
                           "confidence": round(min(0.4, 0.15 + contrast * 0.25), 3)})
    return candidates
