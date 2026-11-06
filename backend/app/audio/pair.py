"""Two-track feasibility prototype; no automatic set ordering yet."""
from dataclasses import asdict
import math
from pathlib import Path
import json
from uuid import uuid4
from backend.app.config import Settings
from backend.app.storage import Storage
from .probe import AudioError, probe, run_audio
from .stretch import pcm_peak, pcm_rms, float_pcm_peak, float_pcm_levels, prepare_excerpt, tempo_ratio
from .phase import pulse_grid, compare_grids, check_overlap_windows
from .recipes import eq_swap_graph


def render_pair(paths: tuple[Path, Path], analyses: tuple[dict, dict], settings: Settings,
                storage: Storage, starts=(None, None), seconds=120.0, bars=8,
                bpms=(None, None), style="auto", target_bpm=None) -> dict:
    if not math.isfinite(seconds) or seconds <= 0 or bars not in {8, 32}:
        raise ValueError("Use positive excerpt seconds and 8 or 32 bars")
    if style not in {"auto", "smooth", "eq_swap", "lead_handoff", "boundary_fade"}:
        raise ValueError("Unknown prototype transition style")
    if target_bpm is not None and (not math.isfinite(target_bpm) or target_bpm <= 0):
        raise ValueError('Target BPM must be finite and positive')
    warnings = list(dict.fromkeys(w for a in analyses for w in a["warnings"]))
    tempos = [override if override is not None else a["bpm"] for override, a in zip(bpms, analyses)]
    if any(t is not None and (not math.isfinite(t) or t <= 0) for t in tempos):
        raise ValueError("Manual BPM values must be finite and positive")
    reliable = all(override is not None or a["beat_confidence"] >= 0.5 for override, a in zip(bpms, analyses))
    match = reliable and all(t is not None for t in tempos) and style != "boundary_fade"
    target = (float(target_bpm) if target_bpm is not None else math.sqrt(tempos[0] * tempos[1])) if match else None
    if match:
        try:
            for tempo in tempos:
                tempo_ratio(tempo, target)
        except ValueError:
            match = False
    if style in {"smooth", "eq_swap", "lead_handoff"} and not match:
        raise ValueError("Beatmatched blend is infeasible; supply reliable BPM or use boundary_fade")
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
        if style in {"smooth", "eq_swap", "lead_handoff"}:
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
        alignment = None
        windowed_alignment = []
        if match:
            # Matching BPM is insufficient: measure the actual stretched overlap.
            region = min(overlap, 30.0)
            first_grid = pulse_grid(prepared[0], cues[0]['output_seconds'] - overlap, region, 60 / target)
            for attempt in range(3):
                second_grid = pulse_grid(prepared[1], 0, region, 60 / target)
                comparison = compare_grids(first_grid, second_grid, overlap)
                alignment = {'outgoing_grid': first_grid, 'incoming_grid': second_grid, **comparison}
                if abs(comparison['drift_seconds']) > .025:
                    raise ValueError('Rendered beats drift by more than 25 ms; choose a steadier region or refine BPM')
                if abs(comparison['incoming_delay_seconds']) <= .012:
                    break
                if attempt == 2:
                    raise ValueError('Could not align rendered pulse phase within 12 ms')
                cue = cues[1]
                shift = -comparison['incoming_delay_seconds'] * cue['target_bpm'] / cue['source_bpm']
                if cue['source_in'] + shift < 0 or cue['source_out'] + shift > analyses[1]['audio']['duration']:
                    raise ValueError('Pulse correction exceeds source bounds; choose a later incoming cue')
                cue['source_in'] += shift
                cue['source_out'] += shift
                prepared[1].unlink()
                prepare_excerpt(paths[1], prepared[1], cue['source_in'], cue['source_out'], cue['source_bpm'], cue['target_bpm'], settings)
            gains[1] = min(1.0, .85 / max(pcm_peak(prepared[1]), 1e-8))
            if overlap > 30:
                windowed_alignment = check_overlap_windows(prepared[0], prepared[1],
                                                          cues[0]['output_seconds']-overlap, overlap, target)
        mixed = temporary / "mixed.mp3"
        graph = (f"[0:a]volume={gains[0]:.9f}[a];[1:a]volume={gains[1]:.9f}[b];"
                 f"[a][b]acrossfade=d={overlap:.9f}:c1=tri:c2=tri,"
                 f"afade=t=in:d=0.01,afade=t=out:st={max(0, expected - 0.01):.9f}:d=0.01[out]")
        selected_style = ('eq_swap' if style in {'eq_swap', 'auto'} else 'smooth') if match else 'boundary_fade'
        if match and style == 'lead_handoff':
            selected_style = 'lead_handoff'
        recipe = {'name': selected_style}
        if selected_style in {'eq_swap', 'lead_handoff'}:
            levels = [pcm_rms(prepared[0], cues[0]['output_seconds'] - overlap, overlap),
                      pcm_rms(prepared[1], 0, overlap)]
            matching_levels = list(levels)
            if selected_style == 'lead_handoff':
                # An outro can be deliberately sparse: do not attenuate the
                # incoming groove to the quietest part of that outro.
                solo = min(overlap, cues[0]['output_seconds'] - overlap)
                matching_levels[0] = max(levels[0], pcm_rms(prepared[0], 0, solo))
            reference = min(level * gain for level, gain in zip(matching_levels, gains))
            gains = [min(gain, reference / max(level, 1e-8)) for gain, level in zip(gains, matching_levels)]
            graph, recipe = eq_swap_graph(gains, cues[0]['output_seconds'], cues[1]['output_seconds'],
                                         overlap, target, alignment['outgoing_grid']['phase_seconds'],
                                         protect_lead=selected_style == 'lead_handoff')
            recipe['overlap_rms_before_gain'] = levels
            recipe['track_gains'] = gains
            recipe['level_matching_rms'] = matching_levels
        command = [settings.ffmpeg, '-v', 'error', '-nostdin', '-i', str(prepared[0]), '-i', str(prepared[1]),
                   '-filter_complex', graph, '-map', '[out]']
        if selected_style in {'eq_swap', 'lead_handoff'}:
            # Scan unclipped PCM and apply constant headroom instead of a
            # dynamic limiter. The recipe also resets the summed timeline
            # before the final fade; tail continuity has its own decode check.
            raw_mix = temporary / 'mixed.f32'
            run_audio(command + ['-f', 'f32le', str(raw_mix)])
            peak = float_pcm_peak(raw_mix)
            gain = min(1.0, .82 / max(peak, 1e-8))
            recipe['mixed_pcm_peak'] = peak
            recipe['post_mix_gain'] = gain
            run_audio([settings.ffmpeg, '-v', 'error', '-nostdin', '-f', 'f32le', '-ar', '44100', '-ac', '2',
                       '-i', str(raw_mix), '-af', f'volume={gain:.12f}',
                       '-c:a', 'libmp3lame', '-b:a', '192k', str(mixed)])
        else:
            run_audio(command + ['-c:a', 'libmp3lame', '-b:a', '192k', str(mixed)])
        info = probe(mixed, settings)
        if abs(info.duration - expected) > 0.15:
            raise AudioError(f"Rendered duration {info.duration:.3f}s differs from expected {expected:.3f}s")
        run_audio([settings.ffmpeg, "-v", "error", "-xerror", "-i", str(mixed), "-f", "null", "-"])
        tail_check = None
        tail_seconds = min(3.0, cues[1]['output_seconds'] - overlap - .2)
        if tail_seconds > .25:
            # Duration/decode checks alone accept a correctly sized silent tail.
            tail_pcm = temporary / 'tail-check.f32'
            run_audio([settings.ffmpeg, '-v', 'error', '-nostdin', '-ss', str(cues[0]['output_seconds'] + .1),
                       '-i', str(mixed), '-t', str(tail_seconds), '-ac', '2', '-ar', '44100', '-f', 'f32le', str(tail_pcm)])
            expected_rms = pcm_rms(prepared[1], overlap + .1, tail_seconds) * gains[1] * recipe.get('post_mix_gain', 1.0)
            _, actual_rms = float_pcm_levels(tail_pcm)
            if expected_rms > 1e-5 and actual_rms < expected_rms * .05:
                raise AudioError('Incoming audio disappears after the outgoing source ends; render rejected')
            tail_check = {'expected_rms': expected_rms, 'decoded_rms': actual_rms, 'seconds': tail_seconds}
        report = {"output": str(destination), "audio": asdict(info), "expected_seconds": expected,
                  "style": selected_style, "recipe": recipe, "bars": bars if match else 0,
                  "target_bpm": target, "overlap_seconds": overlap, "transition_at_seconds": cues[0]["output_seconds"] - overlap,
                  "pulse_alignment": alignment,
                  "windowed_pulse_alignment": windowed_alignment,
                  "incoming_tail_check": tail_check,
                  "tracks": [{"path": str(path), "content_hash": a["content_hash"], **cue} for path, a, cue in zip(paths, analyses, cues)],
                  "warnings": warnings}
        staged_report = temporary / "report.json"
        staged_report.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
        mixed.replace(destination)
        staged_report.replace(report_path)
    return {**report, "report": str(report_path)}
