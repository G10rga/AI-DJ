"""Render isolated pretrained-vs-linear auditions, preserving owner state."""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import math
from pathlib import Path
import sqlite3
import subprocess
import time

import numpy as np
import soundfile as sf

from backend.app.auditions import loudness
from backend.app.config import Settings
from backend.app.research.djtransgan import load_model, VERSION
from backend.app.research.listening import test_mix_definition
from backend.app.research.beat_alignment import detect_prepared_alignment,require_alignment
from scripts.setup_dj_benchmarks import digest

SR = 44100
SECONDS = 60


def command(args):
    result = subprocess.run(args, capture_output=True, timeout=600)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace')[-1500:])
    return result.stdout


def decode(path, start, duration, ratio, settings):
    if not all(math.isfinite(x) for x in (start,duration,ratio)) or start < 0 or duration <= 0 or not .5 <= ratio <= 2:
        raise ValueError('Invalid source window or tempo ratio')
    raw = command([settings.ffmpeg, '-v', 'error', '-nostdin', '-ss', str(start),
                   '-t', str(duration*ratio), '-i', str(path), '-af', f'rubberband=tempo={ratio:.12f}',
                   '-ar', str(SR), '-ac', '1', '-f', 'f32le', '-'])
    data = np.frombuffer(raw, dtype='<f4').copy()
    if abs(len(data)/SR-duration) > .02 or not np.isfinite(data).all():
        raise ValueError('Prepared audio length or samples invalid')
    expected = round(duration*SR)
    return np.pad(data[:expected], (0,max(0,expected-len(data))))


def input_window(path, source_at_start, active_start, active_end, ratio, settings, work, index):
    data = np.zeros(SECONDS*SR, dtype=np.float32)
    part = decode(path, source_at_start, active_end-active_start, ratio, settings)
    data[round(active_start*SR):round(active_end*SR)] = part
    original = work/f'source-{index}.wav'
    sf.write(original, data, SR, subtype='FLOAT')
    measured = loudness(original, settings)
    # Constant gain only; no compressor, limiter or moving loudness normalization.
    gain = min(-20-measured['integrated_lufs'], -3-measured['true_peak_dbfs'])
    data *= 10**(gain/20)
    sf.write(original, data, SR, subtype='FLOAT')
    return data, {'source':str(path), 'source_sha256':digest(path), 'source_start_seconds':source_at_start,
                  'active_region_seconds':[active_start,active_end], 'tempo_ratio':ratio,
                  'preparation_gain_db':gain, 'prepared_sha256':digest(original)}


def definition(args, root):
    if args.test_job:
        return test_mix_definition(args.data_root,args.test_job)
    manifest = json.loads((root/'sources.json').read_text(encoding='utf-8'))
    if args.example:
        source = Path(manifest['sources']['djtransgan']['directory'])/'test'
        # Author's cue endpoints, with an explicit 16-second overlap. This is a
        # model smoke test, not a replication of their madmom preprocessing.
        return {'name':'published-example', 'overlap':16., 'sources':[
            {'path':str(source/'Breikthru ft Danny Devinci-Touch.mp3'), 'start':58., 'ratio':1.},
            {'path':str(source/'Jameson-Hangin.mp3'), 'start':6., 'ratio':1.}],
            'preparation':'Author example songs and cue endpoints (96/30s); explicit 16s overlap; no beat/BPM correction; not exact author pipeline'}
    with sqlite3.connect(f'file:{args.data_root.as_posix()}/app.sqlite3?mode=ro', uri=True) as db:
        row = db.execute("SELECT status,payload_json,result_json FROM workflow_jobs WHERE id=? AND kind='pair_audition'", (args.comparison_job,)).fetchone()
    if not row or row[0] != 'succeeded':
        raise ValueError('Choose a successfully published comparison job')
    payload, result = json.loads(row[1]), json.loads(row[2])
    audition = result['alternatives'][0]
    baseline = args.data_root/'renders'/audition['storage_name']
    if digest(baseline) != audition['audio_hash']:
        raise ValueError('Original baseline changed')
    report_path = baseline.with_suffix('.json')
    report = json.loads(report_path.read_text(encoding='utf-8'))
    cues = report['validation']['applied_plan']['excerpts']
    overlap = audition['overlap_seconds']
    if not 0 < overlap < SECONDS:
        raise ValueError('Model comparison requires an overlap below 60 seconds')
    center = audition['handoff_seconds']
    if center < 30 or center+30 > audition['duration_seconds']:
        raise ValueError('Baseline has insufficient surrounding audio')
    sources = []
    for i,(cue,source) in enumerate(zip(cues,payload['sources'])):
        if digest(source['path']) != source['content_hash']:
            raise ValueError('Original song changed')
        ratio = cue['target_bpm']/cue['source_bpm']
        outgoing_duration = (cues[0]['source_out']-cues[0]['source_in'])/(cues[0]['target_bpm']/cues[0]['source_bpm'])
        offset = center-30 if i==0 else 0
        # Incoming starts at the overlap entrance in the baseline timeline.
        start = cue['source_in']+offset*ratio
        if i==0 and abs(outgoing_duration-(center+overlap/2)) > .02:
            raise ValueError('Baseline handoff does not match its frozen source plan')
        sources.append({'path':source['path'], 'start':start, 'ratio':ratio})
    return {'name':'owner-pair-'+args.comparison_job, 'job_id':args.comparison_job,
            'sources':sources, 'overlap':overlap, 'handoff_in_original_seconds':center,
            'baseline':str(baseline), 'baseline_sha256':digest(baseline),
            'baseline_report_sha256':digest(report_path), 'candidate_id':audition['candidate_id'],
            'preparation':'Frozen existing comparison cues and tempo; mono downmix; constant per-source gain; no source separation in GAN or linear baseline'}


def match_outputs(paths, settings, work):
    measured = {name:loudness(path,settings) for name,path in paths.items()}
    target = min(-20., *(m['integrated_lufs']-2.5-m['true_peak_dbfs'] for m in measured.values()))
    outputs = {}
    for name,path in paths.items():
        output = work/(name+'.mp3')
        gain = target-measured[name]['integrated_lufs']
        command([settings.ffmpeg, '-v','error','-nostdin','-y','-i',str(path),'-af',f'volume={gain:.10f}dB',
                 '-c:a','libmp3lame','-b:a','256k',str(output)])
        final = loudness(output,settings)
        decoded = np.frombuffer(command([settings.ffmpeg,'-v','error','-i',str(output),'-ar',str(SR),
                                         '-ac','1','-f','f32le','-']),dtype='<f4')
        peak = float(np.max(np.abs(decoded)))
        if not np.isfinite(decoded).all() or peak>=1 or final['true_peak_dbfs'] > -1 or abs(final['integrated_lufs']-target)>.3 or abs(len(decoded)/SR-60)>.05:
            raise ValueError('Matched audio failed loudness, peak, duration or finite check')
        # Detect complete dropouts with 100ms blocks; report rather than judge taste.
        blocks = decoded[:len(decoded)//4410*4410].reshape(-1,4410)
        silent = np.sqrt(np.mean(blocks.astype(np.float64)**2,axis=1)) < 1e-5
        longest = run = 0
        for value in silent:
            run = run+1 if value else 0
            longest = max(longest,run)
        outputs[name] = {'path':str(output),'sha256':digest(output), 'duration_seconds':len(decoded)/SR,
                         'channels':1, 'loudness':final,'target_lufs':target,'gain_db':gain,
                         'decoded_peak':peak, 'longest_near_silent_run_seconds':longest*.1}
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('D:/AI-DJ-data/experiments/open-dj'))
    parser.add_argument('--data-root',type=Path,default=Path('D:/AI-DJ-data'))
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--example',action='store_true')
    group.add_argument('--comparison-job')
    group.add_argument('--test-job',help='Compare a successfully published two-song test mix')
    args = parser.parse_args()
    root = args.root.resolve()
    settings = Settings.from_env()
    spec = definition(args,root)
    work = root/'auditions'/spec['name']
    if (work/'listening-reviews').exists():
        raise ValueError('Reviewed audio is immutable; choose a new experimental revision')
    work.mkdir(parents=True,exist_ok=True)
    cue_start, cue_end = 30-spec['overlap']/2, 30+spec['overlap']/2
    print('Preparing '+spec['name'],flush=True)
    windows, preparations = [], []
    for i,source in enumerate(spec['sources']):
        window, prepared = input_window(Path(source['path']),source['start'],0 if i==0 else cue_start,
                                        cue_end if i==0 else 60,source['ratio'],settings,work,i)
        windows.append(window);preparations.append(prepared)
    timing = None
    if not args.example:
        print('Checking independent beats and bar starts before rendering',flush=True)
        timing=detect_prepared_alignment([work/f'source-{i}.wav' for i in range(2)],
                                         cue_start,cue_end,args.data_root/'timeline/models')
        (work/'timing-check.json').write_text(json.dumps(timing,indent=2,allow_nan=False),encoding='utf-8')
        require_alignment(timing)
    import torch
    print('Loading strict pretrained model',flush=True)
    model, provenance = load_model(root)
    started = time.monotonic()
    print('Running CPU inference',flush=True)
    tensors = [torch.from_numpy(window).reshape(1,1,-1) for window in windows]
    with torch.inference_mode():
        output, controls = model.infer(*tensors,cue_region=torch.tensor([cue_start/60,cue_end/60]))
    inference_seconds = time.monotonic()-started
    data = output.reshape(-1).cpu().numpy()
    if data.shape != windows[0].shape or not np.isfinite(data).all() or np.max(np.abs(data))<1e-5:
        raise ValueError('Invalid or silent pretrained output')
    # Save compact interpretable fader/band curves, omitting the huge STFT masks.
    compact = {side:{key: {'shape':list(value.shape),'values':value.cpu().tolist()}
                      for key,value in values.items() if key!='mask'} for side,values in controls.items()}
    (work/'controls.json').write_text(json.dumps(compact,allow_nan=False),encoding='utf-8')
    sf.write(work/'djtransgan-raw.wav',data,SR,subtype='FLOAT')
    progress = np.clip((np.arange(SECONDS*SR)/SR-cue_start)/spec['overlap'],0,1).astype(np.float32)
    linear = windows[0]*(1-progress)+windows[1]*progress
    sf.write(work/'linear-raw.wav',linear,SR,subtype='FLOAT')
    paths = {'djtransgan':work/'djtransgan-raw.wav','linear':work/'linear-raw.wav'}
    if spec.get('baseline'):
        existing = decode(Path(spec['baseline']),spec['handoff_in_original_seconds']-30,60,1,settings)
        sf.write(work/'existing-raw.wav',existing,SR,subtype='FLOAT')
        paths['existing-app'] = work/'existing-raw.wav'
    outputs = match_outputs(paths,settings,work)
    packages = {name:importlib.metadata.version(name) for name in
                ['torch','torchaudio','torchlibrosa','librosa','numpy','scipy','soundfile','numba']}
    report = {'benchmark':VERSION,'created_at':datetime.now(timezone.utc).isoformat(),
              'definition':spec,'preparation':preparations,'model':provenance,'runtime':packages,
              'inference_seconds':inference_seconds,'cue_region_seconds':[cue_start,cue_end],
              'outputs':outputs,'controls_sha256':digest(work/'controls.json'),
              'independent_timing':timing,
              'technical_checks_passed':True,'listening_accepted':None,'promoted':False,
              'limitations':['Mono checkpoint and auditions; no stereo extension claimed',
                             'Our preparation adapter, not an exact replication of author beat tracking',
                             'Linear comparator isolates learned controls; existing app comparator also differs in source separation',
                             'Technical checks cannot establish musical quality; owner listening still required'],
              'script_sha256':digest(__file__)}
    (work/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    lines = ['# Pretrained transition audition', '', spec['preparation'], '',
             f'60-second mono previews. Handoff at 30s; overlap {cue_start:g}–{cue_end:g}s.', '',
             '| Version | Loudness LUFS | True peak dBFS |', '|---|---:|---:|']
    lines += [f'| [{name}]({name}.mp3) | {row["loudness"]["integrated_lufs"]:.2f} | {row["loudness"]["true_peak_dbfs"]:.2f} |' for name,row in outputs.items()]
    lines += ['', f'CPU inference: {inference_seconds:.2f}s. Technical checks passed; listening acceptance pending.', '',
              *['- '+line for line in report['limitations']]]
    (work/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(work/'report.json'),'outputs':outputs,'inference_seconds':inference_seconds},indent=2),flush=True)


if __name__=='__main__':main()
