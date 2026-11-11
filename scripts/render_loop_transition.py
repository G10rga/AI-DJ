"""One loop/filter/delay experiment on the corrected stereo song pair."""
from datetime import datetime,timezone
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

import numpy as np
import soundfile as sf

from backend.app.auditions import loudness
from backend.app.config import Settings
from backend.app.research.beat_alignment import detect_prepared_alignment,require_alignment,marker_alignment
from backend.app.research.loop_effects import splice_loop,apply_effects,VERSION
from scripts.setup_dj_benchmarks import digest

ROOT=Path('D:/AI-DJ-data/experiments/open-dj')
BASELINE=ROOT/'auditions/corrected-at-night-stupidisco-f0096cf999294ce7b45e2b70dfba792b'


def encode_checked(raw,destination,target,settings):
    measured=loudness(raw,settings);gain=target-measured['integrated_lufs']
    subprocess.run([settings.ffmpeg,'-v','error','-nostdin','-y','-i',str(raw),'-af',
                    f'volume={gain:.10f}dB,afade=t=in:d=0.015,afade=t=out:st=59.985:d=0.015',
                    '-c:a','libmp3lame','-b:a','256k',str(destination)],check=True,capture_output=True)
    final=loudness(destination,settings)
    raw_bytes=subprocess.check_output([settings.ffmpeg,'-v','error','-i',str(destination),'-ar','44100',
                                      '-ac','2','-f','f32le','-'])
    data=np.frombuffer(raw_bytes,dtype='<f4').reshape(-1,2)
    if data.shape!=(60*44100,2) or not np.isfinite(data).all() or abs(data).max()>=1 or final['true_peak_dbfs']>-1:
        raise ValueError('Encoded audio shape/finite/peak check failed')
    if abs(final['integrated_lufs']-target)>.3:raise ValueError('Loudness matching failed')
    if np.any(np.sqrt(np.mean(data.reshape(600,4410,2).astype(float)**2,axis=(1,2)))<1e-5):
        raise ValueError('Unexpected audio dropout')
    return data,{'sha256':digest(destination),'duration_seconds':60,'channels':2,'loudness':final,
                  'gain_db':gain,'sample_peak':float(abs(data).max()),'target_lufs':target}


def main():
    status_path=ROOT/'alignment/loop-filter-delay-1/recipe-status.json'
    if status_path.exists():
        status=json.loads(status_path.read_text(encoding='utf-8'))
        if status.get('status')!='available':
            raise ValueError('Owner rejected this loop recipe: vocal cutoff and abrupt incoming entry. A phrase-aware redesign is required before rendering.')
    if importlib.metadata.version('pedalboard')!='0.9.26':raise ValueError('Require pinned Pedalboard 0.9.26')
    baseline=json.loads((BASELINE/'report.json').read_text(encoding='utf-8'))
    if digest(BASELINE/'corrected.mp3')!=baseline['audio_sha256']:raise ValueError('Baseline changed')
    paths=[Path(baseline['work_directory'])/f'source-{i}.wav' for i in range(2)]
    for path,preparation in zip(paths,baseline['preparations']):
        if digest(path)!=preparation['prepared_sha256'] or digest(preparation['source_path'])!=preparation['source_sha256']:
            raise ValueError('Prepared/original source changed')
    work=ROOT/'alignment/loop-filter-delay-1'/('attempt-'+uuid4().hex);work.mkdir()
    settings=Settings(data_root=Path('D:/AI-DJ-data'),
        ffmpeg='D:/Tools/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe',
        ffprobe='D:/Tools/ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe')
    sources=[sf.read(path,dtype='float32',always_2d=True)[0] for path in paths]
    rate=44100;bar=240/baseline['target_bpm'];start=baseline['cue_region_seconds'][0];release=30.
    screening_path=ROOT/'alignment/loop-filter-delay-1/vocal-screening.json'
    screening=json.loads(screening_path.read_text(encoding='utf-8'))
    if screening['source_sha256']!=digest(paths[0]):raise ValueError('Vocal screen belongs to different audio')
    if screening['model']['sha256']!='317554b07fe1ea5279a77f2b1520a41ea4b93432560c4ffd08792c30fddf9adc':
        raise ValueError('Unknown screening model')
    vocals,vocal_rate=sf.read(screening['vocals'],dtype='float32',always_2d=True)
    if vocal_rate!=rate or vocals.shape!=sources[0].shape:raise ValueError('Vocal screening shape changed')
    candidates=[]
    for k in range(8):
        begin,end=round((start+k*bar)*rate),round((start+(k+1)*bar)*rate)
        vocal_rms=float(np.sqrt(np.mean(vocals[begin:end].astype(float)**2)))
        total_rms=float(np.sqrt(np.mean(sources[0][begin:end].astype(float)**2)))
        candidates.append({'bar':k,'start_seconds':start+k*bar,'vocal_rms':vocal_rms,
                           'total_rms':total_rms,'vocal_ratio':vocal_rms/max(total_rms,1e-8)})
    selected=min(candidates,key=lambda candidate:candidate['vocal_ratio'])
    if selected['vocal_ratio']>.2 or selected['total_rms']<.01:
        raise ValueError('No supported lower-vocal loop found; review source cues')
    looped,loop=splice_loop(sources[0],rate,selected['start_seconds'],start,release,bar)
    loop_path=work/'loop-preparation.wav';sf.write(loop_path,looped,rate,subtype='FLOAT')
    print('Verifying loop and incoming timing before effects',flush=True)
    timing=detect_prepared_alignment([loop_path,paths[1]],*baseline['cue_region_seconds'],Path('D:/AI-DJ-data/timeline/models'))
    (work/'timing-check.json').write_text(json.dumps(timing,indent=2),encoding='utf-8')
    require_alignment(timing)
    # Check the actual repeated body, not only the surrounding real context.
    repeated=marker_alignment(timing['sources'][0]['beats'],timing['sources'][1]['beats'],start+.25,release-.25,.025)
    repeated_bars=marker_alignment(timing['sources'][0]['downbeats'],timing['sources'][1]['downbeats'],start+.1,release+.1,.07)
    if repeated['status']!='aligned' or repeated_bars['status']!='aligned':
        raise ValueError('Actual loop body beat/bar alignment failed')
    output,stems,effects=apply_effects(looped,sources[1],rate,start,release,bar)
    raw=work/'loop-filter-delay.wav';sf.write(raw,output,rate,subtype='FLOAT')
    for name,data in stems.items():sf.write(work/(name+'.wav'),data,rate,subtype='FLOAT')
    # Processed output must contain a real decaying echo tail after release.
    tail=stems['echo'][round(release*rate):round((release+2*bar)*rate)]
    tail_rms=float(np.sqrt(np.mean(tail.astype(float)**2)))
    if tail_rms<1e-5:raise ValueError('Delay tail was lost')
    baseline_raw=BASELINE/'corrected.mp3'
    measures=[loudness(path,settings) for path in (raw,baseline_raw)]
    target=min(-20.,*(m['integrated_lufs']-2.5-m['true_peak_dbfs'] for m in measures))
    encoded=work/'loop-filter-delay.mp3';encoded_base=work/'crossfade.mp3'
    samples,encoded_report=encode_checked(raw,encoded,target,settings)
    _,baseline_report=encode_checked(baseline_raw,encoded_base,target,settings)
    print('Checking final encoded loop and release beats',flush=True)
    import torch
    from beat_this.inference import Audio2Beats
    tracker=Audio2Beats(checkpoint_path='D:/AI-DJ-data/timeline/models/final0.ckpt',device='cpu',dbn=False)
    with torch.inference_mode():beats,downs=tracker(samples,rate)
    final_checks=[]
    for label,markers,left,right in [('outgoing',baseline['independent_timing']['sources'][0]['beats'],4,start-1),
                                   ('loop/release',baseline['independent_timing']['sources'][1]['beats'],start+.5,release+2*bar),
                                   ('incoming',baseline['independent_timing']['sources'][1]['beats'],release+2*bar,56)]:
        check={'part':label,**marker_alignment(markers,beats,left,right,.025)}
        if check['status']!='aligned':raise ValueError('Encoded beat check failed: '+label+' '+str(check))
        final_checks.append(check)
    final_bars=marker_alignment(baseline['independent_timing']['sources'][1]['downbeats'],downs,start+.5,release+2*bar,.07)
    if final_bars['status']!='aligned':raise ValueError('Encoded bar alignment uncertain')
    # Snapshot all code/dependencies/artifacts; musical acceptance is never inferred.
    report={'version':VERSION,'created_at':datetime.now(timezone.utc).isoformat(),'work_directory':str(work),
        'baseline_report_sha256':digest(BASELINE/'report.json'),'baseline_audio_sha256':baseline['audio_sha256'],
        'prepared_source_hashes':[digest(path) for path in paths],'target_bpm':baseline['target_bpm'],
        'loop':loop,'selected_loop':selected,'vocal_screening_candidates':candidates,
        'vocal_screening_sha256':digest(screening_path),'vocal_screening_limit':'Model leakage possible; lower predicted vocal activity does not prove instrumental content.',
        'effects':effects,'timing':timing,'loop_beat_check':repeated,'loop_bar_check':repeated_bars,
        'encoded_beat_checks':final_checks,'encoded_bar_check':final_bars,'encoded_beats':list(map(float,beats)),
        'encoded_downbeats':list(map(float,downs)),'delay_tail_rms':tail_rms,
        'outputs':{'loop-filter-delay':encoded_report,'crossfade':baseline_report},
        'packages':{n:importlib.metadata.version(n) for n in ('pedalboard','numpy','soundfile','torch','beat-this')},
        'setup_sha256':digest(ROOT/'pedalboard-runtime/setup.json'),
        'implementation_sha256':digest(__file__),'effects_implementation_sha256':digest(Path(__file__).parents[1]/'backend/app/research/loop_effects.py'),
        'technical_checks_passed':True,'listening_accepted':None,'promoted':False}
    destination=ROOT/'auditions'/('loop-filter-delay-'+work.name.removeprefix('attempt-'));destination.mkdir()
    for path in (encoded,encoded_base):shutil.copyfile(path,destination/path.name)
    (destination/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    (destination/'README.md').write_text('# Loop/filter/delay preview\n\nAt Night → Stupidisco. 60s stereo.\n\nLoop starts ~22.38s, filter sweeps down, incoming releases at 30s, echo decays by ~33.81s.\n\n[New transition](loop-filter-delay.mp3) · [Matched crossfade](crossfade.mp3)\n\nTiming and audio checks passed; musical quality awaits owner listening. No defaults or votes changed.\n',encoding='utf-8')
    print('PUBLISHED '+str(destination),flush=True)


if __name__=='__main__':main()
