"""Cached, low-rate DSP analysis, one track at a time."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from uuid import uuid4
import librosa
import numpy as np
from backend.app.config import Settings
from backend.app.storage import Storage
from .probe import AudioError, probe, run_audio
from .structure import phrase_candidates

VERSION = "pair-analysis-3"
SAMPLE_RATE = 11025
HOP = 256
MAX_SECONDS = 1200
CONFIG = f"{VERSION}:{librosa.__version__}:{SAMPLE_RATE}:{HOP}:{MAX_SECONDS}"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def analyze(path: Path, settings: Settings, storage: Storage) -> dict:
    path = Path(path).resolve(strict=True)
    info = probe(path, settings)
    if info.duration > MAX_SECONDS:
        raise AudioError(f"Prototype analysis supports tracks up to {MAX_SECONDS // 60} minutes; shorten this input")
    digest = file_hash(path)
    cache_key = hashlib.sha256(f"{digest}:{CONFIG}".encode()).hexdigest()
    cache = storage.path("analysis", cache_key + ".json")
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    storage.require_space(int(info.duration * SAMPLE_RATE * 4), settings.min_free_bytes)
    with storage.temporary_directory() as temporary:
        decoded = temporary / "mono.f32"
        run_audio([settings.ffmpeg, "-v", "error", "-nostdin", "-i", str(path), "-map", "0:a:0",
                   "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", str(decoded)])
        samples = np.fromfile(decoded, dtype="<f4")
    if len(samples) < SAMPLE_RATE * 2 or not np.all(np.isfinite(samples)):
        raise AudioError("Audio is too short (minimum 2 seconds) or has invalid samples")
    energy = librosa.feature.rms(y=samples, frame_length=1024, hop_length=HOP)[0]
    onset = librosa.onset.onset_strength(y=samples, sr=SAMPLE_RATE, hop_length=HOP, n_fft=1024)
    warnings = ["Phrase candidates are heuristic; downbeats and musical phrases need listening verification."]
    bpm = None
    beats = np.array([], dtype=float)
    confidence = 0.0
    alternatives = []
    if float(np.max(energy)) > 1e-5 and float(np.max(onset)) > 1e-5:
        tempo, frames = librosa.beat.beat_track(onset_envelope=onset, sr=SAMPLE_RATE,
                                               hop_length=HOP, start_bpm=125, trim=True)
        estimate = float(np.asarray(tempo).reshape(-1)[0])
        if np.isfinite(estimate) and estimate > 0 and len(frames) >= 4:
            # Retain the detected grid; never double its BPM without changing its beat positions.
            beats = librosa.frames_to_time(frames, sr=SAMPLE_RATE, hop_length=HOP)
            # The tracker tempo is quantized to a frame lag. Fit all beat times to
            # avoid turning e.g. a stable 120 BPM grid into a 117.45 BPM stretch.
            interval_fit = float(np.polyfit(np.arange(len(beats)), beats, 1)[0])
            bpm = 60 / interval_fit if interval_fit > 0 else estimate
            intervals = np.diff(beats)
            regularity = max(0.0, 1 - float(np.std(intervals) / max(np.mean(intervals), 1e-8)) * 4)
            prominence = float(np.mean(onset[frames]) / max(float(np.max(onset)), 1e-8))
            confidence = float(np.clip(regularity * prominence, 0, 1))
            alternatives = [round(bpm / 2, 3), round(bpm, 3), round(bpm * 2, 3)]
    if confidence < 0.5:
        warnings.append("Beat estimate is uncertain; automatic tempo matching should be reviewed.")
    if bpm is None:
        warnings.append("No stable beat grid detected; use a short boundary fade or supply BPM manually.")
    profile = np.zeros(12)
    mfcc_mean, mfcc_std = np.zeros(13), np.zeros(13)
    spectral_summary = [0.0, 0.0, 0.0]
    if float(np.max(energy)) > 1e-5:
        spectrum = np.abs(librosa.stft(samples, n_fft=2048, hop_length=HOP))
        chroma = librosa.feature.chroma_stft(S=spectrum**2, sr=SAMPLE_RATE, n_fft=2048, hop_length=HOP)
        profile = np.mean(chroma, axis=1)
        mel = librosa.feature.melspectrogram(S=spectrum**2, sr=SAMPLE_RATE, n_fft=2048, n_mels=64)
        mfcc = librosa.feature.mfcc(S=librosa.power_to_db(mel), n_mfcc=13)
        mfcc_mean, mfcc_std = np.mean(mfcc, axis=1), np.std(mfcc, axis=1)
        centroid = librosa.feature.spectral_centroid(S=spectrum, sr=SAMPLE_RATE)[0]
        flatness = librosa.feature.spectral_flatness(S=spectrum)[0]
        spectral_summary = [float(np.mean(centroid)), float(np.std(centroid)), float(np.mean(flatness))]
    profile /= max(float(np.sum(profile)), 1e-8)
    # Chroma is retained for future pair scoring; no unsupported key label is asserted.
    result = {"version": VERSION, "config": CONFIG, "content_hash": digest, "audio": asdict(info),
              "bpm": bpm, "tempo_alternatives": alternatives, "beat_confidence": round(confidence, 4),
              "beats_seconds": np.round(beats, 4).tolist(), "chroma": profile.tolist(),
              "mfcc_mean": mfcc_mean.tolist(), "mfcc_std": mfcc_std.tolist(),
              "spectral_summary": spectral_summary,
              "energy": energy[::8].tolist(), "energy_frame_seconds": HOP * 8 / SAMPLE_RATE,
              "phrase_candidates": phrase_candidates(beats, energy, HOP / SAMPLE_RATE), "warnings": warnings}
    temporary_cache = cache.with_name(cache.stem + "." + uuid4().hex + ".tmp")
    try:
        temporary_cache.write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
        temporary_cache.replace(cache)
    finally:
        temporary_cache.unlink(missing_ok=True)
    return result
