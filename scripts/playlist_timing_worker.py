"""Independent audio observations compared against the planned VARIABLE time map."""
import argparse
import json
from pathlib import Path
import numpy as np
import soundfile as sf
import torch
from beat_this.inference import Audio2Beats
from backend.app.audio.timing_input import canonical_timing_input
from backend.app.playlist.validation import compare_markers
from backend.app.audio.probe import run_audio
from scripts.setup_timeline import sha256


def main():
    p = argparse.ArgumentParser(); p.add_argument('request', type=Path); p.add_argument('output', type=Path)
    args = p.parse_args(); request = json.loads(args.request.read_text(encoding='utf-8'))
    checkpoint = Path(request['models'])/'final0.ckpt'
    if sha256(checkpoint) != '8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331':
        raise ValueError('Independent detector checkpoint changed')
    torch.set_num_threads(4)
    tracker = Audio2Beats(checkpoint_path=str(checkpoint), device='cpu', dbn=False)
    plan = request['plan']; audits = []
    def detect(path, start, end):
        with sf.SoundFile(path) as f:
            f.seek(round(start*44100)); samples = f.read(round((end-start)*44100), dtype='float32', always_2d=True)
        samples, meta = canonical_timing_input(samples)
        if samples is None: return {'beats': [], 'downbeats': []}
        with torch.inference_mode(): beats, downs = tracker(samples, 44100)
        return {'beats': (np.array(beats)+start).tolist(), 'downbeats': (np.array(downs)+start).tolist()}
    for j, join in enumerate(plan['joins']):
        checks = []
        for side, index in (('a', j), ('b', j+1)):
            track = plan['tracks'][index]; mapping = np.array(track['map'])
            prepared = Path(request['prepared'][index])
            if sha256(prepared) != request['prepared_hashes'][index]: raise ValueError('Prepared audio changed')
            if sha256(Path(request['sources'][index]['path'])) != request['sources'][index]['content_hash']:
                raise ValueError('Original audio changed')
            lo = max(0, join['start']-track['start']-24)
            hi = min(track['duration'], join['start']+join['duration']-track['start']+24)
            observed = detect(prepared, lo, hi)
            source_lo, source_hi = np.interp([lo, hi], mapping[:, 1], mapping[:, 0])
            original = args.output.parent/f'original-{j}-{side}.wav'
            run_audio([request['ffmpeg'], '-v', 'error', '-nostdin', '-y', '-ss', str(source_lo),
                '-t', str(source_hi-source_lo), '-i', request['sources'][index]['path'], '-ac', '2', '-ar', '44100',
                '-c:a', 'pcm_f32le', str(original)])
            original_markers = detect(original, 0, source_hi-source_lo)
            for kind, stride in (('beats', 1), ('downbeats', 4)):
                expected = np.array(join['output_beats'][::stride])+join['start']-track['start']
                # Source detector results are transformed by the complete piecewise map.
                mapped = np.interp(np.array(original_markers[kind])+source_lo, mapping[:, 0], mapping[:, 1])
                for label, markers in (('original', mapped), ('prepared', observed[kind])):
                    audit = compare_markers(expected, markers, downbeats=kind=='downbeats',
                                            human_phase=track.get('grid_confirmed', False),
                                            half_bars=np.array(join['output_beats'][2::4])+join['start']-track['start'])
                    checks.append({'side': side, 'stage': label, 'kind': kind, **audit})
        corroborated = any(
            left['side'] == right['side'] and left['kind'] == right['kind'] and
            left['stage'] != right['stage'] and left['reason'] == right['reason'] and
            left['status'] == right['status'] == 'mismatch'
            for left in checks for right in checks
        )
        audits.append({'join': j, 'candidate_id': join['id'], 'checks': checks,
                       'status': 'aligned' if all(c['status'] == 'aligned' for c in checks)
                       else 'mismatch' if corroborated else 'uncertain'})
    result = {'version': 'playlist-variable-map-timing-1', 'plan_id': plan['id'],
              'prepared_hashes': request['prepared_hashes'], 'joins': audits,
              'status': 'aligned' if all(a['status'] == 'aligned' for a in audits)
              else 'mismatch' if any(a['status'] == 'mismatch' for a in audits) else 'uncertain'}
    args.output.write_text(json.dumps(result, allow_nan=False))


if __name__ == '__main__': main()
