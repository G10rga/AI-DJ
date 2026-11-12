"""Independently validate actual improved-pipeline audio in the pinned CPU runtime."""
import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from beat_this.inference import Audio2Beats

from backend.app.audio.beat_validation import audit_join, window_alignment, recheck_original_grid, contextual_bar_support
from backend.app.audio.mdx import sha256_file
from backend.app.audio.probe import run_audio
from backend.app.audio.timing_input import canonical_timing_input, CONTEXT_SECONDS, VERSION as INPUT_VERSION
from backend.app.audio.encoding_timing import verify_encoding

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
    if request.get('mixed_pcm') and sha256_file(request['mixed_pcm'])!=request['mixed_pcm_sha256']:
        raise ValueError('Pre-encode PCM changed')
    revisions=request.get('source_marker_revisions',[s['reference']['correction_revision'] for s in plan['sources']])
    if (len(revisions)!=len(plan['sources']) or any(type(r) is not int or r<0 or
            r!=s['reference']['correction_revision'] for r,s in zip(revisions,plan['sources']))):
        raise ValueError('Source timing correction revision changed')
    policy_path = Path(__file__).resolve().parents[1]/'backend/app/audio/timing_input.py'
    policy_hash = sha256_file(policy_path)
    if request.get('detector_policy_sha256') != policy_hash:
        raise ValueError('Beat detector input policy changed before validation')
    detector_inputs = []

    def detect_samples(samples, label):
        samples, metadata = canonical_timing_input(samples)
        detector_inputs.append({'label': label, **metadata})
        if samples is None:
            return {'beats': [], 'downbeats': []}
        with torch.inference_mode():
            beats, downs = tracker(samples, 44100)
        return {'beats': [float(t) for t in beats], 'downbeats': [float(t) for t in downs]}

    def detect(path, start, end, global_offset, label):
        with sf.SoundFile(path) as audio:
            if audio.samplerate != 44100 or audio.channels != 2:
                raise ValueError('Timing requires actual stereo 44100Hz preparation')
            first = max(0, round(start*audio.samplerate))
            last = min(len(audio), round(end*audio.samplerate))
            audio.seek(first)
            samples = audio.read(max(0, last-first), dtype='float32', always_2d=True)
        markers = detect_samples(samples, label)
        detector_inputs[-1].update(file_sha256=sha256_file(path), first_frame=first, last_frame=last,
                                   global_offset=global_offset)
        offset = global_offset+first/44100
        return {kind: [t+offset for t in values] for kind, values in markers.items()}

    def local_original(side, entry, end, join_index):
        source = plan['sources'][side]
        offset, ratio = source['start_seconds'], source['target_bpm']/source['source_bpm']
        with sf.SoundFile(request['prepared_paths'][side]) as audio:
            first = max(0, round((entry-offset-CONTEXT_SECONDS)*44100))/44100
            last = min(len(audio), round((end-offset+CONTEXT_SECONDS)*44100))/44100
        start = source['source_in']+first*ratio
        stop = source['source_in']+last*ratio
        path = args.result.parent/f'original-recheck-{join_index}-{side}.wav'
        run_audio([request['ffmpeg'], '-v', 'error', '-nostdin', '-ss', str(start), '-t', str(stop-start),
            '-i', request['original_paths'][side], '-ac', '2', '-ar', '44100', '-c:a', 'pcm_f32le', str(path)])
        samples, rate = sf.read(path, dtype='float32', always_2d=True)
        if rate != 44100 or abs(len(samples)/rate-(stop-start)) > .002:
            raise ValueError('Original timing recheck did not decode the complete requested passage')
        gain = request['preparation_gains'][side]
        if type(gain) not in (int, float) or not np.isfinite(gain) or not -120 <= gain <= 60:
            raise ValueError('Invalid original recheck preparation gain')
        variants = {}
        for variant, audio in (('raw', samples), ('prepared_gain', samples*10**(gain/20))):
            markers = detect_samples(audio, f'join-{join_index}-original-{side}-{variant}')
            variants[variant] = {kind: [offset+first+t/ratio for t in values]
                                 for kind, values in markers.items()}
        return variants, {'source_index': side, 'source_sha256': request['original_sha256'][side],
            'source_interval': [start, stop], 'output_interval': [offset+first, offset+last],
            'decoded_sha256': sha256_file(path), 'preparation_gain_db': gain}

    for path, digest in zip(request['prepared_paths'], request['prepared_sha256']):
        if sha256_file(path) != digest:
            raise ValueError('Prepared source changed before timing validation')
    if sha256_file(request['encoded_pcm']) != request['encoded_pcm_sha256']:
        raise ValueError('Encoded waveform changed before timing validation')
    if request.get('original_paths') is not None:
        if not (len(request['original_paths']) == len(request['original_sha256']) ==
                len(request['preparation_gains']) == len(plan['sources'])):
            raise ValueError('Incomplete original recheck inputs')
        for path, digest, source in zip(request['original_paths'], request['original_sha256'], plan['sources']):
            if digest != source['reference']['source_sha256'] or sha256_file(path) != digest:
                raise ValueError('Original changed before timing recheck')
    joins = []
    for i, join in enumerate(plan['joins']):
        entry, end = join['entry_seconds'], join['end_seconds']
        observed, expected = [], []
        for side in (i, i+1):
            source = plan['sources'][side]
            offset = source['start_seconds']
            observed.append(detect(request['prepared_paths'][side], entry-offset-CONTEXT_SECONDS,
                end-offset+CONTEXT_SECONDS, offset, f'join-{i}-prepared-{side}'))
            ratio = source['target_bpm']/source['source_bpm']
            expected.append({kind: [offset+(t-source['source_in'])/ratio for t in request['source_markers'][side][kind]]
                             for kind in ('beats', 'downbeats')})
        encoded = detect(request['encoded_pcm'], entry-CONTEXT_SECONDS, end+CONTEXT_SECONDS, 0., f'join-{i}-encoded')
        manual=join['candidate'].get('version')=='manual-handoff-1'
        if manual:
            if not request.get('original_paths'):raise ValueError('Manual placement requires actual original timing verification')
            cached=expected;originals={};audio_reports=[]
            for side in (0,1):
                variants,provenance=local_original(i+side,entry,end,i)
                originals[side]=variants;audio_reports.append(provenance)
            expected=[cached[side] if revisions[i+side]>0 else originals[side]['raw'] for side in (0,1)]
            audit=audit_join(*observed,expected,entry,end,encoded,manual=True)
            gained=audit_join(*observed,[originals[side]['prepared_gain'] for side in (0,1)],entry,end,encoded,manual=True)
            gained_checks=[]
            for check in gained['checks']:
                if check['comparison'].startswith('original_mapping_'):
                    gained_checks.append({**check,'comparison':check['comparison'].replace('original_mapping_','original_gain_mapping_')})
            original_support=[{'side':side,'variant':variant,
                **contextual_bar_support(markers['beats'],markers['downbeats'],entry+.5,end-.5)}
                for side,variants in originals.items() for variant,markers in variants.items()]
            audit['checks'].extend(gained_checks)
            audit['source_audio_verification']={'method':'fresh-original-manual-placement-1','originals':originals,
                'audio':audio_reports,'bar_support':original_support,
                'source_grid_authority':['human_corrected' if revisions[i+side]>0 else 'fresh_local_original' for side in (0,1)]}
            audit['cached_marker_diagnostics']=audit_join(*observed,cached,entry,end,encoded,manual=True)
            if any(c['status']!='aligned' for c in gained_checks) or any(s['status']!='regular' for s in original_support):
                audit['status']='needs_review'
        else:
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
        audit.update(join_index=i, solo_checks=solo, independently_detected=observed,encoded_detected=encoded)
        if manual and request.get('mixed_pcm'):
            waveform=verify_encoding(request['mixed_pcm'],request['encoded_pcm'],
                                    max(.5,entry-7),min(plan['duration_seconds']-.5,end+7))
            audit['encoding_waveform']=waveform
            if waveform['status']=='aligned':
                for check in audit['checks']:
                    if check['status']!='aligned' and check['comparison'].startswith('encoded_overlap_'):
                        check['resolved_by']='encoded-waveform-timebase-1'
                for check in solo:
                    if check['status']!='aligned':check['resolved_by']='encoded-waveform-timebase-1'
            audit['status']='validated' if (waveform['status']=='aligned'
                and all(c['status']=='aligned' or c.get('resolved_by') for c in audit['checks']+solo)
                and all(s['status']=='regular' for s in audit['bar_support'])
                and all(s['status']=='regular' for s in audit['source_audio_verification']['bar_support'])) else 'needs_review'
        failed = [check for check in audit['checks'] if check['status'] != 'aligned']
        if (not manual and request.get('original_paths') is not None and failed
                and all(c['status'] == 'mismatch' and c['comparison'] in
                        ('original_mapping_0', 'original_mapping_1') for c in failed)
                and all(c['status'] == 'aligned' for c in solo)
                and all(s['status'] == 'regular' for s in audit['bar_support'])):
            originals, audio_reports = {}, []
            for side in sorted({int(c['comparison'][-1]) for c in failed}):
                variants, provenance = local_original(i+side, entry, end, i)
                originals[side] = variants; audio_reports.append(provenance)
            audit = recheck_original_grid(audit, observed, expected, originals, entry, end)
            if 'original_context_recheck' in audit:
                audit['original_context_recheck']['audio'] = audio_reports
        joins.append(audit)
    for path, digest in zip(request.get('original_paths', []), request.get('original_sha256', [])):
        if sha256_file(path) != digest:
            raise ValueError('Original changed during timing recheck')
    report = {'version': 'improved-audio-timing-4', 'checkpoint_sha256': CHECKPOINT,
              'plan_id': plan['id'], 'worker_sha256': sha256_file(__file__),
              'detector_policy': INPUT_VERSION, 'detector_context_seconds': CONTEXT_SECONDS,
              'detector_policy_sha256': policy_hash, 'detector_inputs': detector_inputs,
              'original_sha256': request.get('original_sha256'),
              'source_marker_revisions': revisions,
              'prepared_sha256': request['prepared_sha256'], 'encoded_pcm_sha256': request['encoded_pcm_sha256'],
              'mixed_pcm_sha256':request.get('mixed_pcm_sha256'),
              'joins': joins, 'status': 'validated' if all(j['status'] == 'validated' for j in joins) else 'needs_review'}
    args.result.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    main()
