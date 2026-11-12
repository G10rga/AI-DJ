"""Independently validate actual improved-pipeline audio in the pinned CPU runtime."""
import argparse
import json
from pathlib import Path

import soundfile as sf
import torch
from beat_this.inference import Audio2Beats

from backend.app.audio.beat_validation import audit_join, window_alignment
from backend.app.audio.mdx import sha256_file

CHECKPOINT = '8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request', type=Path); parser.add_argument('result', type=Path)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding='utf-8'))
    checkpoint = Path(request['models'])/'final0.ckpt'
    if sha256_file(checkpoint) != CHECKPOINT:
        raise ValueError('Pinned independent beat model changed')
    torch.set_num_threads(4)
    tracker = Audio2Beats(checkpoint_path=str(checkpoint), device='cpu', dbn=False)
    plan = request['plan']

    def detect(path, start, end, global_offset):
        with sf.SoundFile(path) as audio:
            if audio.samplerate != 44100 or audio.channels != 2:
                raise ValueError('Timing requires actual stereo 44100Hz preparation')
            first = max(0, round(start*audio.samplerate))
            last = min(len(audio), round(end*audio.samplerate))
            audio.seek(first)
            samples = audio.read(max(0, last-first), dtype='float32', always_2d=True)
        with torch.inference_mode():
            beats, downs = tracker(samples, 44100)
        offset = global_offset+first/44100
        return {'beats': [float(t)+offset for t in beats], 'downbeats': [float(t)+offset for t in downs]}

    for path, digest in zip(request['prepared_paths'], request['prepared_sha256']):
        if sha256_file(path) != digest:
            raise ValueError('Prepared source changed before timing validation')
    if sha256_file(request['encoded_pcm']) != request['encoded_pcm_sha256']:
        raise ValueError('Encoded waveform changed before timing validation')
    joins = []
    for i, join in enumerate(plan['joins']):
        entry, end = join['entry_seconds'], join['end_seconds']
        observed, expected = [], []
        for side in (i, i+1):
            source = plan['sources'][side]
            offset = source['start_seconds']
            observed.append(detect(request['prepared_paths'][side], entry-offset-8, end-offset+8, offset))
            ratio = source['target_bpm']/source['source_bpm']
            expected.append({kind: [offset+(t-source['source_in'])/ratio for t in request['source_markers'][side][kind]]
                             for kind in ('beats', 'downbeats')})
        encoded = detect(request['encoded_pcm'], entry-8, end+8, 0.)
        audit = audit_join(*observed, expected, entry, end, encoded)
        # Check the audible solo neighborhood on either side as well.
        solo = []
        for side, left, right in ((0, max(plan['sources'][i]['start_seconds']+1, entry-7), entry-.5),
                                  (1, end+.5, min(plan['duration_seconds']-1, end+7))):
            if right-left < 2:
                continue
            solo.append({'side': side, **window_alignment(observed[side]['beats'], encoded['beats'], left, right, .025)})
        if any(item['status'] != 'aligned' for item in solo):
            audit['status'] = 'needs_review'
        audit.update(join_index=i, solo_checks=solo, independently_detected=observed)
        joins.append(audit)
    report = {'version': 'improved-audio-timing-1', 'checkpoint_sha256': CHECKPOINT,
              'plan_id': plan['id'], 'worker_sha256': sha256_file(__file__),
              'prepared_sha256': request['prepared_sha256'], 'encoded_pcm_sha256': request['encoded_pcm_sha256'],
              'joins': joins, 'status': 'validated' if all(j['status'] == 'validated' for j in joins) else 'needs_review'}
    args.result.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    main()
