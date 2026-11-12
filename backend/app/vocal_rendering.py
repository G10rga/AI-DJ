"""One continuous float renderer and independent gate for improved Generate/Compare."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import numpy as np
import soundfile as sf

from .audio.float_prepare import prepare_float_excerpt, preparation_gain, apply_constant_gain
from .audio.mdx import sha256_file
from .audio.probe import run_audio, AudioError
from .audio.vocal_automation import relative_gain
from .config import PROJECT_ROOT
from .planning.vocal_preserving import validate_plan, review

RATE = 44100


def check_live(live):
    if not live():
        raise RuntimeError('Improved transition job was cancelled or its lease expired')


def independent_timing(prepared, decoded, plan, records, settings, work, original_paths=None, preparation_gains=None):
    runtime = settings.data_root/('timeline/venv/Scripts/python.exe' if os.name == 'nt' else 'timeline/venv/bin/python')
    if not runtime.exists():
        raise ValueError('Independent timing runtime is unavailable')
    request = {'models': str(settings.data_root/'timeline/models'), 'plan': plan,
        'prepared_paths': [str(path) for path in prepared], 'prepared_sha256': [sha256_file(path) for path in prepared],
        'encoded_pcm': str(decoded), 'encoded_pcm_sha256': sha256_file(decoded),
        'source_markers': [{kind: record['effective'][kind]['times'] for kind in ('beats', 'downbeats')} for record in records]}
    request['detector_policy_sha256'] = sha256_file(PROJECT_ROOT/'backend/app/audio/timing_input.py')
    request['source_marker_revisions']=[record['revision'] for record in records]
    if plan.get('version')=='vocal-preserving-planner-2' and (work/'mix.wav').exists():
        request.update(mixed_pcm=str(work/'mix.wav'),mixed_pcm_sha256=sha256_file(work/'mix.wav'))
    if original_paths is not None:
        request.update(original_paths=[str(path) for path in original_paths],
            original_sha256=[sha256_file(path) for path in original_paths],
            preparation_gains=preparation_gains, ffmpeg=settings.ffmpeg)
    request_path, result = work/'timing-request.json', work/'timing-result.json'
    request_path.write_text(json.dumps(request, allow_nan=False), encoding='utf-8')
    subprocess.run([str(runtime), '-m', 'scripts.transition_timing_worker', str(request_path), str(result)],
                   cwd=PROJECT_ROOT, check=True, timeout=1800)
    audit = json.loads(result.read_text(encoding='utf-8'))
    if (audit.get('prepared_sha256') != request['prepared_sha256']
            or audit.get('encoded_pcm_sha256') != request['encoded_pcm_sha256']
            or audit.get('plan_id') != plan['id']
            or audit.get('original_sha256') != request.get('original_sha256')
            or audit.get('detector_policy_sha256') != request['detector_policy_sha256']
            or audit.get('source_marker_revisions') != request['source_marker_revisions']
            or audit.get('mixed_pcm_sha256') != request.get('mixed_pcm_sha256')
            or audit.get('worker_sha256') != sha256_file(PROJECT_ROOT/'scripts/transition_timing_worker.py')):
        raise ValueError('Independent timing report is for different audio')
    return audit


def timing_failure_message(audit):
    for join in audit.get('joins', []):
        for side, support in enumerate(join.get('bar_support', [])):
            if support.get('status') != 'regular':
                return (f'The {"outgoing" if side == 0 else "incoming"} song has uncertain beat/bar evidence at this handoff. '
                    'Review its timing in the timeline editor or choose a steadier passage. No audio was published.')
        failures = [c for c in join.get('checks', []) if c.get('status') != 'aligned' and not c.get('resolved_by')]
        if any(c.get('comparison') == 'prepared_pair' for c in failures):
            return ('The songs could not be verified on the same beat/bar grid at this handoff. '
                'Review their timing in the timeline editor or choose a steadier passage. No audio was published.')
        if any(c.get('comparison', '').startswith(('original_mapping','original_gain_mapping')) for c in failures):
            return ('The original and stretched source timing could not be verified at this handoff. '
                'Review source timing in the timeline editor. No audio was published.')
        if failures or any(c.get('status') != 'aligned' for c in join.get('solo_checks', [])):
            return ('The encoded preview timing could not be verified against the prepared songs. '
                'The failed timing checks are retained in this attempt. No audio was published.')
    return 'Independent rhythm evidence is incomplete for this preview. No audio was published.'


def mix_float(prepared, plan, destination, *, live=lambda: True):
    """Prepared files are continuous; only their explicitly planned gains vary."""
    total = round(plan['duration_seconds']*RATE)
    with ExitStack() as stack:
        inputs = [stack.enter_context(sf.SoundFile(path)) for path in prepared]
        output = stack.enter_context(sf.SoundFile(destination, 'w', samplerate=RATE, channels=2, subtype='FLOAT'))
        for first in range(0, total, 65536):
            check_live(live)
            stop = min(total, first+65536)
            mixed = np.zeros((stop-first, 2), dtype=np.float32)
            for i, (audio, source) in enumerate(zip(inputs, plan['sources'])):
                start = round(source['start_seconds']*RATE)
                left, right = max(first, start), min(stop, start+len(audio))
                if left >= right:
                    continue
                audio.seek(left-start)
                block = audio.read(right-left, dtype='float32', always_2d=True)
                if len(block) != right-left or not np.isfinite(block).all():
                    raise AudioError('Invalid continuous source stream')
                gains = relative_gain(plan, i, np.arange(left, right)/RATE)
                mixed[left-first:right-first] += block*gains[:, None]
            if not np.isfinite(mixed).all():
                raise AudioError('Nonfinite float mix')
            output.write(mixed)


def render_plan(plan, records, paths, settings, storage, *, live=lambda: True,
                timing=independent_timing, target_lufs=-20.):
    from .auditions import loudness
    validate_plan(plan, records)
    if len(paths) != len(records):
        raise ValueError('One original per ordered entry is required')
    check_live(live)
    for path, source in zip(paths, plan['sources']):
        if sha256_file(path) != source['reference']['source_sha256']:
            raise ValueError('Original changed since planning')
    storage.initialize()
    storage.require_space(int(sum(s['duration_seconds'] for s in plan['sources'])*RATE*2*4*4), settings.min_free_bytes)
    with storage.temporary_directory() as directory:
        try:
            prepared, preparations = [], []
            for i, (source, path) in enumerate(zip(plan['sources'], paths)):
                check_live(live)
                output = directory/f'source-{i}.wav'
                report = prepare_float_excerpt(path, output, source['source_in'], source['duration_seconds'],
                    source['source_bpm'], source['target_bpm'], settings)
                measured = loudness(output, settings)
                gain = preparation_gain(measured['integrated_lufs'], measured['true_peak_dbfs'])
                apply_constant_gain(output, gain)
                report.update(gain_db=gain, prepared_sha256=sha256_file(output), measured_before_gain=measured)
                preparations.append(report); prepared.append(output)
            raw = directory/'mix.wav'
            mix_float(prepared, plan, raw, live=live)
            measured = loudness(raw, settings)
            gain = preparation_gain(measured['integrated_lufs'], measured['true_peak_dbfs'],
                                    target_lufs=target_lufs, ceiling_dbfs=-2.5)
            encoded = directory/'mix.mp3'
            duration = plan['duration_seconds']
            run_audio([settings.ffmpeg, '-v', 'error', '-nostdin', '-i', str(raw), '-af',
                f'volume={gain:.12f}dB,afade=t=in:d=0.015,afade=t=out:st={max(0.,duration-.015):.12f}:d=0.015',
                '-c:a', 'libmp3lame', '-b:a', '256k', str(encoded)])
            decoded = directory/'encoded.wav'
            run_audio([settings.ffmpeg, '-v', 'error', '-xerror', '-nostdin', '-i', str(encoded),
                       '-ac', '2', '-ar', str(RATE), '-c:a', 'pcm_f32le', str(decoded)])
            peak = 0.
            with sf.SoundFile(decoded) as audio:
                if audio.channels != 2 or audio.samplerate != RATE or abs(len(audio)-round(duration*RATE)) > 44:
                    raise AudioError('Encoded stereo/duration validation failed')
                for block in audio.blocks(blocksize=65536, dtype='float32', always_2d=True):
                    if not np.isfinite(block).all():
                        raise AudioError('Encoded samples are invalid')
                    peak = max(peak, float(np.abs(block).max()))
                for join in plan['joins']:
                    audio.seek(round((join['entry_seconds']+.5)*RATE))
                    count = round((join['end_seconds']-join['entry_seconds']-1)*RATE)
                    for offset in range(0, count, RATE//10):
                        block = audio.read(min(RATE//10, count-offset), dtype='float32', always_2d=True)
                        if not len(block) or np.sqrt(np.mean(block.astype(float)**2)) < 1e-5:
                            raise AudioError('Encoded overlap contains a dropout')
            final = loudness(encoded, settings)
            if peak >= 1 or final['true_peak_dbfs'] > -1:
                raise AudioError('Encoded peak validation failed')
            check_live(live)
            audit = timing(prepared, decoded, plan, records, settings, directory,
                           paths, [p['gain_db'] for p in preparations])
            if audit.get('status') != 'validated' or len(audit.get('joins', [])) != len(plan['joins']):
                return {'status': 'needs_review', 'review_items': [review('independent_timing_failed',
                    timing_failure_message(audit), details=audit)],
                    'plan': plan, 'timing': audit}
            for path, source in zip(paths, plan['sources']):
                if sha256_file(path) != source['reference']['source_sha256']:
                    raise ValueError('Original changed during rendering')
            check_live(live)
            destination = storage.path('renders', 'improved-'+uuid4().hex+'.mp3')
            report = {'version': 'vocal-preserving-render-1', 'pipeline': plan['pipeline'], 'status': 'validated',
                'plan': plan, 'requested': plan['requested'], 'preparations': preparations,
                'timing': audit, 'duration_seconds': duration, 'loudness': final,
                'target_lufs': target_lufs, 'post_mix_gain_db': gain, 'sample_peak': peak,
                'audio_sha256': sha256_file(encoded), 'output': str(destination), 'listening_accepted': None}
            modules = ['backend/app/planning/vocal_preserving.py', 'backend/app/vocal_rendering.py',
                'backend/app/audio/vocal_automation.py', 'backend/app/audio/beat_validation.py',
                'backend/app/audio/timing_input.py',
                'backend/app/planning/manual_handoff.py', 'backend/app/audio/encoding_timing.py',
                'scripts/transition_timing_worker.py']
            report['implementation_sha256'] = {name: sha256_file(PROJECT_ROOT/name) for name in modules}
            # Only validated audio crosses out of scratch space. Existing files
            # and previous playable revisions are never overwritten.
            encoded.replace(destination)
            destination.with_suffix('.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
            return report
        except (ValueError, AudioError, subprocess.SubprocessError) as exc:
            return {'status': 'needs_review', 'plan': plan, 'review_items': [review('audio_validation_failed',
                str(exc)+'. The selected recipe/cues were not replaced.')]}
