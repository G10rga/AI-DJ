"""Validate contextual proposals and render comparable local listening auditions."""
from copy import deepcopy
from dataclasses import replace, asdict
import json
import math
import subprocess
from pathlib import Path
from uuid import uuid4
import numpy as np
from backend.app.models import MixPlan
from backend.app.audio.mdx import sha256_file
from backend.app.audio.phase import pulse_grid, compare_grids, check_overlap_windows
from backend.app.audio.probe import probe, run_audio
from backend.app.audio.stretch import prepare_excerpt, pcm_rms, pcm_peak, float_pcm_levels, float_pcm_peak, tempo_ratio
from backend.app.audio.stem_mix import stem_pair_graph
from backend.app.rendering import separate_local
from backend.app.planning.candidate_store import CandidateStore

VERSION = 'contextual-audition-1'


def loudness(path, settings):
    command = [settings.ffmpeg, '-v', 'info', '-nostdin', '-i', str(path), '-af',
               'loudnorm=I=-20:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-']
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300)
    if result.returncode:
        raise RuntimeError('Unable to measure audition loudness: '+result.stderr[-500:])
    start, end = result.stderr.rfind('{'), result.stderr.rfind('}')
    data = json.loads(result.stderr[start:end+1])
    values = {'integrated_lufs': float(data['input_i']), 'true_peak_dbfs': float(data['input_tp'])}
    if not all(math.isfinite(x) for x in values.values()):
        raise ValueError('Audition loudness measurement is not finite')
    return values


def match_auditions(reports, settings, storage):
    """Write new matched artifacts; retain the original renders and their reports."""
    if not reports:
        return []
    measurements = [loudness(report['output'], settings) for report in reports]
    target = min(-20., *(m['integrated_lufs']-1.8-m['true_peak_dbfs'] for m in measurements))
    matched = []
    for report, measured in zip(reports, measurements):
        gain_db = target-measured['integrated_lufs']
        output = storage.path('renders', 'matched-audition-'+uuid4().hex+'.mp3')
        with storage.temporary_directory() as work:
            staged = work/'matched.mp3'
            run_audio([settings.ffmpeg, '-v', 'error', '-nostdin', '-i', report['output'],
                       '-af', f'volume={gain_db:.8f}dB', '-c:a', 'libmp3lame', '-b:a', '256k', str(staged)])
            final = loudness(staged, settings)
            decoded = work/'check.f32'
            run_audio([settings.ffmpeg, '-v', 'error', '-xerror', '-i', str(staged), '-f', 'f32le', str(decoded)])
            peak, rms = float_pcm_levels(decoded)
            if abs(final['integrated_lufs']-target) > .3 or final['true_peak_dbfs'] > -1 or peak >= 1:
                raise ValueError('Matched audition loudness or true-peak check failed')
            info = probe(staged, settings)
            if info.channels != 2 or abs(info.duration-report['duration']) > .1:
                raise ValueError('Matched audition format/duration changed')
            revised = {**report, 'output': str(output), 'matched_from': report['output'], 'encoded_peak': peak,
                       'encoded_rms': rms, 'loudness': {**final, 'target_lufs': target, 'gain_db': gain_db}}
            revised['audio_sha256'] = sha256_file(staged)
            staged.replace(output)
            output.with_suffix('.json').write_text(json.dumps(revised, indent=2, allow_nan=False), encoding='utf-8')
            matched.append(revised)
    return matched


def prepare(plan, paths, work, settings, suffix):
    outputs = []
    for i, (cue, path) in enumerate(zip(plan.excerpts, paths)):
        output = work/f'{suffix}-{i}.wav'
        prepare_excerpt(path, output, cue.source_in, cue.source_out, cue.source_bpm, cue.target_bpm, settings)
        if abs(probe(output, settings).duration-cue.output_duration) > .01:
            raise ValueError('Prepared source duration mismatch')
        outputs.append(output)
    return outputs


def validate_candidate(candidate, sources, settings, storage):
    """No recipe fallback; corrections are bounded and independently rechecked."""
    plan = MixPlan.from_json(json.dumps(candidate['plan']))
    paths = [Path(sources[ref['track_id']]).resolve(strict=True) for ref in candidate['sources']]
    for path, ref in zip(paths, candidate['sources']):
        if sha256_file(path) != ref['content_hash']:
            raise ValueError('Candidate source changed')
    transition = plan.transitions[0]
    if len(plan.excerpts) != 2 or len(candidate['sources']) != 2:
        raise ValueError('An audition candidate must contain exactly two tracks')
    storage.require_space(int(sum(c.output_duration for c in plan.excerpts)*44100*2*4*4), settings.min_free_bytes)
    overlap = transition.overlap_seconds
    bpm = plan.excerpts[0].target_bpm
    for cue in plan.excerpts:
        tempo_ratio(cue.source_bpm, cue.target_bpm)
    cut = transition.style == 'phrase_cut'
    with storage.temporary_directory() as work:
        if cut:
            # Short crossfade itself cannot establish pulse alignment. Inspect
            # eight-second neighborhoods around the actual annotated boundaries.
            validation_cues = tuple(replace(cue, source_in=anchor-4*cue.target_bpm/cue.source_bpm,
                                            source_out=anchor+4*cue.target_bpm/cue.source_bpm)
                                    for cue, anchor in zip(plan.excerpts, candidate['anchors_seconds']))
            test_plan = replace(plan, excerpts=validation_cues)
            for cue in validation_cues:
                cue.validate()
            prepared = prepare(test_plan, paths, work, settings, 'cut-context')
            start, span = 0., 8.
        else:
            prepared = prepare(plan, paths, work, settings, 'proposed')
            start, span = plan.excerpts[0].output_duration-overlap, overlap
        first = pulse_grid(prepared[0], start, min(30, span), 60/bpm)
        second = pulse_grid(prepared[1], 0, min(30, span), 60/bpm)
        comparison = compare_grids(first, second, span)
        if abs(comparison['drift_seconds']) > .025:
            raise ValueError('Candidate beats drift by more than 25ms')
        correction = -comparison['incoming_delay_seconds']*plan.excerpts[1].target_bpm/plan.excerpts[1].source_bpm
        if abs(correction) > min(.08, 60/plan.excerpts[1].source_bpm*.2):
            raise ValueError('Phase correction would leave the proposed boundary neighborhood')
        applied = plan
        if abs(comparison['incoming_delay_seconds']) > .008:
            cue = plan.excerpts[1]
            changed = replace(cue, source_in=cue.source_in+correction, source_out=cue.source_out+correction)
            changed.validate()
            applied = replace(plan, excerpts=(plan.excerpts[0], changed))
            correction_cue = replace(test_plan.excerpts[1], source_in=test_plan.excerpts[1].source_in+correction,
                                     source_out=test_plan.excerpts[1].source_out+correction) if cut else changed
            output = work/'phase-corrected.wav'
            prepare_excerpt(paths[1], output, correction_cue.source_in, correction_cue.source_out,
                            correction_cue.source_bpm, correction_cue.target_bpm, settings)
            prepared[1] = output
        else:
            correction = 0.
        checks = check_overlap_windows(prepared[0], prepared[1], start, span, bpm)
        if not checks:
            raise ValueError('Insufficient audio for an independent pulse check')
        applied.validate()
        levels = [pcm_rms(path, start if i == 0 else 0, span) for i, path in enumerate(prepared)]
        if min(levels) < .003 or levels[1] < levels[0]*.25:
            raise ValueError('Candidate would have a silent or collapsed incoming region')
    return {'version': VERSION, 'candidate_id': candidate['id'], 'status': 'validated',
            'applied_plan': json.loads(applied.to_json()), 'incoming_source_correction_seconds': correction,
            'pulse_checks': checks, 'source_levels_rms': levels,
            'handoff_seconds': candidate['handoff_seconds'], 'duration_seconds': candidate['duration_seconds']}


def blend_schedule(plan,candidate):
    overlap=plan.transitions[0].overlap_seconds;bpm=plan.excerpts[0].target_bpm
    start=plan.excerpts[0].output_duration-overlap;seam=candidate['handoff_seconds']
    fade=min(({32:8,16:4,8:2}[plan.transitions[0].bars])*240/bpm,overlap/3)
    beat=60/bpm
    return ({'outgoing_fade_start_seconds':seam-beat-fade,'outgoing_fade_duration_seconds':fade,
        'incoming_fade_start_local_seconds':seam+beat-start,'incoming_fade_duration_seconds':fade,
        'outgoing_curve':'qsin','incoming_curve':'hsin','vocal_eq':True,'semantic_phrase_detection':False},
        {'groove_32':'long_groove','controlled_16':'controlled','eq_8':'standard'}[candidate['recipe']])


def render_candidate(candidate, validation, sources, settings, storage, *, separate=separate_local):
    if validation['candidate_id'] != candidate['id'] or validation['status'] != 'validated':
        raise ValueError('A successful validation for this candidate is required')
    plan = MixPlan.from_json(json.dumps(validation['applied_plan']))
    paths = [Path(sources[r['track_id']]).resolve(strict=True) for r in candidate['sources']]
    for path, ref in zip(paths, candidate['sources']):
        if sha256_file(path) != ref['content_hash']:
            raise ValueError('Candidate source changed since validation')
    overlap = plan.transitions[0].overlap_seconds
    first, second = [c.output_duration for c in plan.excerpts]
    total = first+second-overlap
    start, seam, bpm = first-overlap, candidate['handoff_seconds'], plan.excerpts[0].target_bpm
    cut = candidate['recipe'] == 'phrase_cut'
    name = 'audition-'+uuid4().hex
    destination = storage.path('renders', name+'.mp3')
    storage.require_space(int((first+second)*44100*2*4*12), settings.min_free_bytes)
    with storage.temporary_directory() as work:
        prepared = prepare(plan, paths, work, settings, 'source')
        # Match levels from a solo region on each side, not a quiet source tail.
        reference_levels = [pcm_rms(path, max(0, cue.output_duration/2-4), min(8., cue.output_duration/2))
                            for path, cue in zip(prepared, plan.excerpts)]
        level = min(reference_levels)
        if level < .003:
            raise ValueError('Audition solo context is too quiet')
        gains = [min(1., level/max(rms, 1e-8), .85/max(pcm_peak(path), 1e-8))
                 for rms, path in zip(reference_levels, prepared)]
        stems = []
        if cut:
            inputs = prepared
            graph = (f'[0:a]volume={gains[0]:.9f}[a];[1:a]volume={gains[1]:.9f}[b];'
                     f'[a][b]acrossfade=d={overlap:.9f}:c1=hsin:c2=hsin,asetpts=N/SR/TB[out]')
            recipe = {'name': 'phrase_cut', 'click_free_seconds': overlap,
                      'boundary_evidence': candidate['evidence']['anchors']}
        else:
            for i, path in enumerate(prepared):
                stem = separate(path, work/f'stems-{i}.json', settings, storage)
                if abs(probe(Path(stem['instrumental']), settings).duration-plan.excerpts[i].output_duration) > .01:
                    raise ValueError('Separated instrumental duration mismatch')
                stems.append(stem)
            # pulse_grid reads PCM16; the actual separator writes float stems.
            instruments = []
            for i, stem in enumerate(stems):
                pcm = work/f'instrument-pulse-{i}.wav'
                run_audio([settings.ffmpeg, '-v', 'error', '-nostdin', '-i', stem['instrumental'], '-c:a', 'pcm_s16le', str(pcm)])
                instruments.append(pcm)
            instrumental_checks = check_overlap_windows(*instruments, start, overlap, bpm)
            schedule,mode=blend_schedule(plan,candidate)
            phase = pulse_grid(instruments[0], start, min(30, overlap), 60/bpm)['phase_seconds']
            graph, recipe = stem_pair_graph(gains, first, second, overlap, bpm, phase, schedule, mode)
            recipe['instrumental_checks'] = instrumental_checks
            inputs = [stems[0]['instrumental'], stems[1]['instrumental'], stems[0]['vocals'], stems[1]['vocals']]
        command = [settings.ffmpeg, '-v', 'error', '-nostdin']
        for path in inputs:
            command += ['-i', str(path)]
        raw = work/'mix.f32'
        run_audio(command+['-filter_complex', graph, '-map', '[out]', '-f', 'f32le', str(raw)])
        peak, rms = float_pcm_levels(raw)
        gain = min(.1/max(rms, 1e-8), .80/max(peak, 1e-8))
        encoded = work/'audition.mp3'
        run_audio([settings.ffmpeg, '-v', 'error', '-nostdin', '-f', 'f32le', '-ar', '44100', '-ac', '2', '-i', str(raw),
                   '-af', f'volume={gain:.12f},afade=t=in:d=0.01,afade=t=out:st={total-.01:.9f}:d=0.01',
                   '-c:a', 'libmp3lame', '-b:a', '256k', str(encoded)])
        info = probe(encoded, settings)
        decoded = work/'decoded.f32'
        run_audio([settings.ffmpeg, '-v', 'error', '-xerror', '-i', str(encoded), '-ar', '44100', '-ac', '2', '-f', 'f32le', str(decoded)])
        final_peak, final_rms = float_pcm_levels(decoded)
        if info.channels != 2 or abs(info.duration-total) > .15 or final_peak >= 1:
            raise ValueError('Audition format, duration or peak validation failed')
        samples = np.memmap(decoded, dtype='<f4', mode='r').reshape(-1, 2)
        energy = [float(np.sqrt(np.mean(samples[i:i+88200].astype(float)**2))) for i in range(0, len(samples), 88200)]
        del samples
        if any(value < 1e-4 for value in energy[1:-1]):
            raise ValueError('Unexpected silence in audition')
        report = {'version': VERSION, 'candidate_id': candidate['id'], 'output': str(destination), 'recipe': recipe,
                  'requested_candidate': candidate, 'validation': validation, 'duration': info.duration,
                  'handoff_seconds': seam, 'track_gains': gains, 'post_mix_gain': gain, 'encoded_peak': final_peak,
                  'encoded_rms': final_rms, 'target_rms': .1, 'headroom_limited': gain < .1/max(rms, 1e-8),
                  'energy_rms_2s': energy, 'stems': stems, 'listening_accepted': None}
        report.update(style='phrase_cut' if cut else 'vocal_stem_handoff', target_bpm=bpm,
                      overlap_seconds=overlap, transition_at_seconds=start,
                      tracks=[{**asdict(cue), 'path': str(path), 'content_hash': ref['content_hash'],
                               'output_seconds': cue.output_duration}
                              for cue, path, ref in zip(plan.excerpts, paths, candidate['sources'])])
        encoded.replace(destination)
        destination.with_suffix('.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report


def evaluate_pair(batch, sources, settings, storage, *, audition_count=2, separate=separate_local,
                  progress=None, live=None, rank=None):
    """Rank only waveform-valid proposals; preserve every rejection and snapshot."""
    if type(audition_count) is not int or not 0 <= audition_count <= 2 or len(batch['candidates']) > 12:
        raise ValueError('Use at most twelve proposals and zero to two auditions')
    store = CandidateStore(storage.root)
    valid, rejected = [], []
    for index,candidate in enumerate(batch['candidates']):
        if live and not live():raise ValueError('Comparison cancelled or worker lease lost')
        if progress:progress(f'Checking candidate {index+1} of {len(batch["candidates"])}',.18+.32*index/max(1,len(batch['candidates'])))
        store.register(candidate)
        try:
            validation = validate_candidate(candidate, sources, settings, storage)
        except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
            payload = {'reason': str(exc), 'stage': 'waveform'}
            store.event(candidate['id'], 'rejected', payload)
            rejected.append({'candidate_id': candidate['id'], **payload})
            continue
        store.event(candidate['id'], 'validated', validation)
        valid.append((candidate, validation))
    valid.sort(key=lambda pair: (-pair[0]['context_score'], pair[0]['id']))
    if rank:valid=rank(valid)
    reports, attempted = [], set()
    # Prefer distinct recipes; further cue alternatives remain available if one render fails.
    order = []
    for pair in valid:
        if pair[0]['recipe'] not in {p[0]['recipe'] for p in order}:
            order.append(pair)
    order += [pair for pair in valid if pair not in order]
    for candidate, validation in order:
        if live and not live():raise ValueError('Comparison cancelled or worker lease lost')
        if len(reports) >= audition_count:
            break
        if candidate['recipe'] in attempted and len({p[0]['recipe'] for p in valid}) >= audition_count:
            continue
        try:
            if progress:progress(f'Rendering alternative {len(reports)+1} of {audition_count}; separating vocals and checking audio',.52+.16*len(reports))
            report = render_candidate(candidate, validation, sources, settings, storage, separate=separate)
            store.event(candidate['id'], 'audition', report)
            reports.append(report)
            attempted.add(candidate['recipe'])
        except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
            payload = {'reason': str(exc), 'stage': 'render'}
            store.event(candidate['id'], 'rejected', payload)
            rejected.append({'candidate_id': candidate['id'], **payload})
    try:
        if live and not live():raise ValueError('Comparison cancelled or worker lease lost')
        if progress:progress('Matching playback loudness',.9)
        reports = match_auditions(reports, settings, storage)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        rejected.extend({'candidate_id': r['candidate_id'], 'stage': 'loudness', 'reason': str(exc),
                         'unmatched_output': r['output']} for r in reports)
        reports = []
    for report in reports:
        store.event(report['candidate_id'], 'audition', report)
    render_failures = {r['candidate_id'] for r in rejected if r['stage'] in {'render', 'loudness'}}
    return {'validations': [{'candidate': c, 'validation': v} for c, v in valid if c['id'] not in render_failures], 'auditions': reports,
            'rejections': batch['rejections']+rejected, 'score_method': 'deterministic context baseline; no owner labels'}
