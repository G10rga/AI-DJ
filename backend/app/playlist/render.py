"""Offline keyframe warping, shared WASM automation, bounded-memory stereo mixing."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import numpy as np
import soundfile as sf
from .planner import digest, validate_plan
from ..config import PROJECT_ROOT
from ..audio.probe import run_audio
from ..audio.encoding_timing import verify_encoding
from scripts.setup_timeline import sha256

RATE = 44100
VERSION = 'playlist-render-3'


def rubberband(settings):
    override = os.environ.get('AI_DJ_RUBBERBAND')
    choices = [Path(override)] if override else []
    choices += list((settings.data_root/'tools/rubberband').glob('*/rubberband.exe'))
    binary = next((p for p in choices if p.is_file()), None)
    if binary is None:
        located = shutil.which('rubberband'); binary = Path(located) if located else None
    if binary is None: raise ValueError('Install Rubber Band 4 offline utility; see scripts/setup-playlist.ps1')
    return binary


def warp(source, track, settings, live=lambda: True):
    binary = rubberband(settings)
    key = digest({'source': source['content_hash'], 'map': track['map'], 'version': VERSION,
                  'rubberband': sha256(binary)})
    directory = settings.data_root/'cache/playlist-warps'/key
    directory.mkdir(parents=True, exist_ok=True)
    output = directory/'warped.wav'; manifest = directory/'manifest.json'
    if output.exists() and manifest.exists() and json.loads(manifest.read_text())['sha256'] == sha256(output): return output
    if not live(): raise ValueError('Cancelled or superseded')
    original = directory/'source.wav'
    run_audio([settings.ffmpeg, '-v', 'error', '-nostdin', '-y', '-ss', str(track['source_in']),
               '-t', str(track['source_out']-track['source_in']), '-i', source['path'],
               '-ac', '2', '-ar', str(RATE), '-c:a', 'pcm_f32le', str(original)])
    info = sf.info(original)
    expected_source = round((track['source_out']-track['source_in'])*RATE)
    if abs(info.frames-expected_source) > 2: raise ValueError('Source decode did not preserve requested bounds')
    anchors = [(round((s-track['source_in'])*RATE), round(o*RATE)) for s, o in track['map']]
    if any(a[0] >= b[0] or a[1] >= b[1] for a, b in zip(anchors, anchors[1:])):
        raise ValueError('Keyframe frame map must increase strictly')
    mapfile = directory/'map.txt'
    # R3 calculates its initial ratio from the first supplied point. The
    # origin and final duration are already implicit in the offline API.
    interior = anchors[1:-1]
    mapfile.write_text(''.join(f'{a} {b}\n' for a, b in interior), encoding='ascii')
    staged = directory/'warped-staged.wav'
    if all(a == b for a, b in anchors):
        original.replace(staged)
    else:
        command = [str(binary), '--fine', '--quiet', '--centre-focus', '--ignore-clipping', '--time',
                   str(anchors[-1][1]/info.frames)]
        if interior:
            command.extend(['--timemap', str(mapfile)])
        subprocess.run(command+[str(original), str(staged)], check=True, timeout=7200, stdout=subprocess.DEVNULL)
    info = sf.info(staged)
    if info.channels != 2 or info.samplerate != RATE or info.subtype != 'FLOAT' or abs(info.frames-anchors[-1][1]) > 2:
        raise ValueError('Rubber Band output duration does not match its keyframe map')
    if not live(): raise ValueError('Cancelled or superseded')
    staged.replace(output)
    manifest.write_text(json.dumps({'sha256': sha256(output), 'frames': info.frames, 'map': anchors, 'key': key}))
    original.unlink(missing_ok=True)
    return output


def segments(plan, index):
    track = plan['tracks'][index]; result = []
    if index:
        join = plan['joins'][index-1]
        result.append({'start': 0., 'end': join['duration'], 'curves': join['automation']['b']})
    if index < len(plan['joins']):
        join = plan['joins'][index]
        result.append({'start': join['start']-track['start'], 'end': track['duration'], 'curves': join['automation']['a']})
    return result


def apply_dsp(path, target, controls, work, settings):
    raw = work/'input.f32'; output = work/'output.f32'; config = work/'automation.json'
    run_audio([settings.ffmpeg, '-v', 'error', '-nostdin', '-y', '-i', str(path), '-f', 'f32le', str(raw)])
    config.write_text(json.dumps(controls))
    subprocess.run(['node', str(PROJECT_ROOT/'scripts/playlist_dsp.mjs'), str(raw), str(output), str(config)],
                   check=True, timeout=7200)
    run_audio([settings.ffmpeg, '-v', 'error', '-nostdin', '-y', '-f', 'f32le', '-ar', str(RATE), '-ac', '2',
               '-i', str(output), '-c:a', 'pcm_f32le', str(target)])


def timing(plan, paths, sources, settings, work):
    runtime = settings.data_root/('timeline/venv/Scripts/python.exe' if os.name == 'nt' else 'timeline/venv/bin/python')
    if not runtime.is_file(): raise ValueError('Independent timing runtime is unavailable')
    hashes = [sha256(p) for p in paths]
    timing_workers = ['scripts/playlist_timing_worker.py', 'backend/app/playlist/validation.py',
                      'backend/app/audio/timing_input.py']
    key = digest({'tracks': plan['tracks'], 'joins': [j['geometry_id'] for j in plan['joins']],
                  'prepared': hashes, 'sources': [s['content_hash'] for s in sources],
                  'audit_code': [sha256(PROJECT_ROOT/p) for p in timing_workers]})
    directory = settings.data_root/'cache/playlist-timing'
    directory.mkdir(parents=True, exist_ok=True)
    cached = directory/(key+'.json')
    if cached.is_file():
        result = json.loads(cached.read_text(encoding='utf-8'))
        result['plan_id'] = plan['id']
        for check, join in zip(result['joins'], plan['joins']):
            check['candidate_id'] = join['id']
        return result
    if not plan['joins']:
        return {'version': 'playlist-variable-map-timing-1', 'plan_id': plan['id'], 'prepared_hashes': hashes,
                'joins': [], 'status': 'aligned'}
    request = {'plan': plan, 'prepared': [str(p) for p in paths], 'prepared_hashes': hashes,
               'sources': sources, 'models': str(settings.data_root/'timeline/models'), 'ffmpeg': settings.ffmpeg}
    request_path = work/'timing-request.json'; result = work/'timing.json'
    request_path.write_text(json.dumps(request))
    subprocess.run([str(runtime), '-m', 'scripts.playlist_timing_worker', str(request_path), str(result)],
                   cwd=PROJECT_ROOT, check=True, timeout=7200)
    audit = json.loads(result.read_text())
    if audit['plan_id'] != plan['id'] or audit['prepared_hashes'] != request['prepared_hashes']:
        raise ValueError('Timing result does not match prepared audio')
    staged = cached.with_suffix('.tmp')
    staged.write_text(json.dumps(audit, allow_nan=False), encoding='utf-8')
    staged.replace(cached)
    return audit


def mix(plan, paths, settings, work, live=lambda: True):
    total = round(plan['duration']*RATE)
    disk = work/'mix.f32'; buffer = np.memmap(disk, mode='w+', dtype='float32', shape=(total, 2))
    buffer[:] = 0
    for i, (track, path) in enumerate(zip(plan['tracks'], paths)):
        if not live(): raise ValueError('Cancelled or superseded')
        processed = work/f'processed-{i}.wav'
        apply_dsp(path, processed, segments(plan, i), work, settings)
        offset = round(track['start']*RATE)
        with sf.SoundFile(processed) as source:
            for block in source.blocks(blocksize=65536, dtype='float32', always_2d=True):
                count = min(len(block), total-offset)
                if count <= 0: break
                if not np.isfinite(block).all(): raise ValueError('Nonfinite processed audio')
                buffer[offset:offset+count] += block[:count]; offset += count
        processed.unlink()
    output = work/'mix.wav'
    with sf.SoundFile(output, 'w', samplerate=RATE, channels=2, subtype='FLOAT') as f:
        for offset in range(0, total, 65536): f.write(buffer[offset:offset+65536])
    buffer.flush(); del buffer
    return output


def loudness(source, settings):
    args = [settings.ffmpeg, '-hide_banner', '-nostdin', '-i', str(source), '-af',
            'loudnorm=I=-14:TP=-1:LRA=11:print_format=json', '-f', 'null', '-']
    measured = subprocess.run(args, capture_output=True, text=True, check=True, timeout=7200).stderr
    return json.loads(measured[measured.rfind('{'):measured.rfind('}')+1])


def normalize(source, output, settings):
    stats = loudness(source, settings)
    if not all(np.isfinite(float(stats[k])) for k in ('input_i', 'input_tp', 'input_lra', 'input_thresh')):
        raise ValueError('Cannot normalize silent or invalid audio')
    config = ('loudnorm=I=-14:TP=-1.3:LRA=11:linear=true:' + ':'.join(
        f'{name}={stats[key]}' for name, key in [('measured_I', 'input_i'), ('measured_TP', 'input_tp'),
        ('measured_LRA', 'input_lra'), ('measured_thresh', 'input_thresh'), ('offset', 'target_offset')]))
    run_audio([settings.ffmpeg, '-v', 'error', '-nostdin', '-y', '-i', str(source), '-af', config,
               '-ar', str(RATE), '-c:a', 'pcm_f32le', str(output)])
    return stats


def artifacts(plan, paths, sources, settings, work, directory, export=False, live=lambda: True):
    directory.mkdir(parents=True, exist_ok=True)
    result = []; previews = []
    def add(path, name):
        result.append({'name': name, 'path': str(path.relative_to(settings.data_root)), 'sha256': sha256(path)})
    for i, join in enumerate(plan['joins']):
        start = max(0., join['start']-8); end = min(plan['duration'], join['start']+join['duration']+8)
        preview = {'index': i, 'start': start, 'duration': end-start, 'overlap_start': join['start']-start,
                   'overlap_end': join['start']+join['duration']-start, 'tracks': []}
        for side, index in (('a', i), ('b', i+1)):
            name = f'join-{i}-{side}.wav'
            track = plan['tracks'][index]
            cache = settings.data_root/'cache/playlist-previews'
            cache.mkdir(parents=True, exist_ok=True)
            preview_key = digest({'warp': paths[index].parent.name, 'offset': track['start']-start, 'length': end-start})
            path = cache/(preview_key+'.wav')
            # Excerpts share the same output clock; silence only outside a song's actual interval.
            if not path.is_file():
                count = round((end-start)*RATE); samples = np.zeros((count, 2), dtype='float32')
                left = max(start, track['start']); right = min(end, track['start']+track['duration'])
                with sf.SoundFile(paths[index]) as f:
                    f.seek(round((left-track['start'])*RATE)); block = f.read(round((right-left)*RATE), dtype='float32', always_2d=True)
                offset = round((left-start)*RATE); n = min(len(block), count-offset); samples[offset:offset+n] = block[:n]
                staged = path.with_suffix('.tmp.wav')
                sf.write(staged, samples, RATE, subtype='FLOAT')
                staged.replace(path)
            add(path, name)
            preview['tracks'].append({'name': name, 'segments': [{'start': s['start']+track['start']-start,
                'end': s['end']+track['start']-start, 'curves': s['curves']} for s in segments(plan, index)]})
        previews.append(preview)
    if not export:
        return {'artifacts': result, 'previews': previews, 'encoded_timing': []}
    mixed = mix(plan, paths, settings, work, live)
    normalized = directory/'mix.wav'; stats = normalize(mixed, normalized, settings)
    mp3 = directory/'mix.mp3'
    run_audio([settings.ffmpeg, '-v', 'error', '-nostdin', '-y', '-i', str(normalized), '-c:a', 'libmp3lame', '-b:a', '320k', str(mp3)])
    decoded = work/'encoded.wav'
    run_audio([settings.ffmpeg, '-v', 'error', '-nostdin', '-y', '-i', str(mp3), '-c:a', 'pcm_f32le', str(decoded)])
    if sf.info(decoded).frames != sf.info(normalized).frames:
        raise ValueError('Encoded MP3 does not preserve the complete set duration')
    levels = {format: loudness(path, settings) for format, path in (('wav', normalized), ('mp3', decoded))}
    if any(float(level['input_tp']) > -1 for level in levels.values()):
        raise ValueError('An encoded format exceeds the -1 dBTP ceiling')
    encoded_checks = [verify_encoding(normalized, decoded, j['start'], j['start']+j['duration']) for j in plan['joins']]
    if any(c['status'] != 'aligned' for c in encoded_checks): raise ValueError('Encoded audio timing failed')
    add(mp3, 'mix.mp3'); add(normalized, 'mix.wav')
    for scratch in ('input.f32', 'output.f32', 'mix.f32', 'mix.wav', 'encoded.wav'):
        (work/scratch).unlink(missing_ok=True)
    return {'artifacts': result, 'previews': previews, 'loudness_input': stats,
            'loudness_exports': levels, 'encoded_timing': encoded_checks}
