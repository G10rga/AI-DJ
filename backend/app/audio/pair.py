"""Two-track feasibility prototype; no automatic set ordering yet."""
from dataclasses import asdict
import math
from pathlib import Path
import json
from uuid import uuid4
from backend.app.config import Settings
from backend.app.storage import Storage
from .probe import AudioError, probe, run_audio
from .stretch import pcm_peak, prepare_excerpt, tempo_ratio


def render_pair(paths: tuple[Path, Path], analyses: tuple[dict, dict], settings: Settings,
                storage: Storage, starts=(None, None), seconds=120.0, bars=8,
                bpms=(None, None), style="auto") -> dict:
    if not math.isfinite(seconds) or seconds <= 0 or bars not in {8, 32}:
        raise ValueError("Use positive excerpt seconds and 8 or 32 bars")
    if style not in {"auto", "smooth", "boundary_fade"}:
        raise ValueError("Unknown prototype transition style")
    warnings = list(dict.fromkeys(w for a in analyses for w in a["warnings"]))
    tempos = [override if override is not None else a["bpm"] for override, a in zip(bpms, analyses)]
    if any(t is not None and (not math.isfinite(t) or t <= 0) for t in tempos):
        raise ValueError("Manual BPM values must be finite and positive")
    reliable = all(override is not None or a["beat_confidence"] >= 0.5 for override, a in zip(bpms, analyses))
    match = reliable and all(t is not None for t in tempos) and style != "boundary_fade"
    target = math.sqrt(tempos[0] * tempos[1]) if match else None
    if match:
        try:
            for tempo in tempos:
                tempo_ratio(tempo, target)
        except ValueError:
            match = False
    if style == "smooth" and not match:
        raise ValueError("Smooth beatmatched blend is infeasible; supply reliable BPM or use boundary_fade")
    if not match:
        target = None
        warnings.append("Using an unstretched short boundary fade; beats may not align.")
    cues = []
    for index, analysis in enumerate(analyses):
        candidates = analysis["phrase_candidates"]
        start = starts[index]
        if start is None:
            start = candidates[0]["seconds"] if candidates else 0.0
        duration = analysis["audio"]["duration"]
        if not math.isfinite(start) or not 0 <= start < duration:
            raise ValueError("Mix-in point is outside the source audio")
        source_bpm = tempos[index] or 120.0  # Fallback ratio stays 1; this is not a tempo estimate.
        target_bpm = target if match else source_bpm
        ratio = target_bpm / source_bpm
        end = min(duration, start + seconds * ratio)
        cues.append({"source_in": start, "source_out": end, "source_bpm": source_bpm,
                     "target_bpm": target_bpm, "output_seconds": (end - start) / ratio})
    overlap = bars * 4 * 60 / target if match else min(0.25, *(c["output_seconds"] / 4 for c in cues))
    if overlap >= min(c["output_seconds"] for c in cues):
        if style == "smooth":
            raise ValueError("Excerpts are too short for this overlap; reduce bars or increase seconds")
        match = False
        target = None
        warnings.append("Excerpts are too short for the requested bars; using a boundary fade.")
        # Reset geometry along with tempo when reverting to unstretched audio.
        for cue, analysis in zip(cues, analyses):
            cue["target_bpm"] = cue["source_bpm"]
            cue["source_out"] = min(analysis["audio"]["duration"], cue["source_in"] + seconds)
            cue["output_seconds"] = cue["source_out"] - cue["source_in"]
        overlap = min(0.25, *(c["output_seconds"] / 4 for c in cues))
    expected = sum(c["output_seconds"] for c in cues) - overlap
    storage.require_space(int(sum(c["output_seconds"] for c in cues) * 44100 * 4 * 3), settings.min_free_bytes)
    name = "pair-" + uuid4().hex
    destination = storage.path("renders", name + ".mp3")
    report_path = storage.path("renders", name + ".json")
    with storage.temporary_directory() as temporary:
        prepared = []
        gains = []
        for index, (path, cue) in enumerate(zip(paths, cues)):
            output = temporary / f"track-{index}.wav"
            prepare_excerpt(path, output, cue["source_in"], cue["source_out"], cue["source_bpm"], cue["target_bpm"], settings)
            peak = pcm_peak(output)
            gains.append(min(1.0, 0.85 / max(peak, 1e-8)))
            prepared.append(output)
        mixed = temporary / "mixed.mp3"
        graph = (f"[0:a]volume={gains[0]:.9f}[a];[1:a]volume={gains[1]:.9f}[b];"
                 f"[a][b]acrossfade=d={overlap:.9f}:c1=tri:c2=tri,"
                 f"afade=t=in:d=0.01,afade=t=out:st={max(0, expected - 0.01):.9f}:d=0.01[out]")
        run_audio([settings.ffmpeg, "-v", "error", "-nostdin", "-i", str(prepared[0]), "-i", str(prepared[1]),
                   "-filter_complex", graph, "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "192k", str(mixed)])
        info = probe(mixed, settings)
        if abs(info.duration - expected) > 0.15:
            raise AudioError(f"Rendered duration {info.duration:.3f}s differs from expected {expected:.3f}s")
        run_audio([settings.ffmpeg, "-v", "error", "-xerror", "-i", str(mixed), "-f", "null", "-"])
        report = {"output": str(destination), "audio": asdict(info), "expected_seconds": expected,
                  "style": "smooth" if match else "boundary_fade", "bars": bars if match else 0,
                  "target_bpm": target, "overlap_seconds": overlap, "transition_at_seconds": cues[0]["output_seconds"] - overlap,
                  "tracks": [{"path": str(path), "content_hash": a["content_hash"], **cue} for path, a, cue in zip(paths, analyses, cues)],
                  "warnings": warnings}
        staged_report = temporary / "report.json"
        staged_report.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
        mixed.replace(destination)
        staged_report.replace(report_path)
    return {**report, "report": str(report_path)}
