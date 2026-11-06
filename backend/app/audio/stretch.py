"""Pitch-preserving excerpt preparation and bounded, explicit tempo changes."""
import math
from pathlib import Path
import wave
import numpy as np
from backend.app.config import Settings
from .probe import AudioError, run_audio


def tempo_ratio(source_bpm: float, target_bpm: float, maximum: float = 0.06) -> float:
    if not all(math.isfinite(x) and x > 0 for x in (source_bpm, target_bpm)):
        raise ValueError("BPM must be finite and positive")
    ratio = target_bpm / source_bpm
    if abs(ratio - 1) > maximum + 1e-9:
        raise ValueError(f"Tempo change exceeds {maximum:.0%}; choose a boundary fade")
    return ratio


def prepare_excerpt(source: Path, output: Path, start: float, end: float,
                    source_bpm: float, target_bpm: float, settings: Settings):
    ratio = tempo_ratio(source_bpm, target_bpm)
    if not all(math.isfinite(x) for x in (start, end)) or not 0 <= start < end:
        raise ValueError("Invalid excerpt bounds")
    duration = (end - start) / ratio
    # apad/atrim compensate small native stretcher duration rounding, not missing source audio.
    filters = (f"rubberband=tempo={ratio:.10f}:pitch=1:channels=together,"
               f"apad,atrim=duration={duration:.9f},asetpts=PTS-STARTPTS")
    run_audio([settings.ffmpeg, "-v", "error", "-nostdin", "-ss", str(start), "-t", str(end - start),
               "-i", str(source), "-map", "0:a:0", "-vn", "-af", filters,
               "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", str(output)])


def pcm_peak(path: Path) -> float:
    peak = 0.0
    with wave.open(str(path), "rb") as audio:
        if audio.getsampwidth() != 2:
            raise AudioError("Expected 16-bit PCM audio")
        while block := audio.readframes(65536):
            data = np.frombuffer(block, dtype="<i2").astype(np.float32) / 32768
            peak = max(peak, float(np.max(np.abs(data))))
    return peak
