"""Prepare one fresh, independently checked stereo linear crossfade."""
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
from uuid import uuid4

import numpy as np
import soundfile as sf

from backend.app.auditions import loudness
from backend.app.audio.stretch import tempo_ratio
from backend.app.config import Settings
from backend.app.research.beat_alignment import detect_prepared_alignment,require_alignment
from backend.app.research.steady_bars import stable_spans
from scripts.setup_dj_benchmarks import digest


def main():
    root=Path('D:/AI-DJ-data/experiments/open-dj')
    analysis_path=root/'alignment/at-night-stupidisco-1/full-beats.json'
    analysis=json.loads(analysis_path.read_text(encoding='utf-8'))
    sources=analysis['sources']
    if len(sources)!=2:raise ValueError('Require both complete original analyses')
    anchors=[112.09294728988341,120.10336806261367]
    selected=[]
    for source,anchor in zip(sources,anchors):
        if digest(source['path'])!=source['sha256']:raise ValueError('Original changed')
        choices=stable_spans(source,anchor)
        if not choices:raise ValueError('No nearby supported eight-bar span')
        selected.append(choices[0])
    target=float(np.sqrt(np.prod([choice['source_bpm'] for choice in selected])))
    overlap=32*60/target
    entry,exit=30-overlap/2,30+overlap/2
    work=root/'alignment/at-night-stupidisco-1'/('attempt-'+uuid4().hex)
    work.mkdir()
    settings=Settings(data_root=Path('D:/AI-DJ-data'),
                      ffmpeg='D:/Tools/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe',
                      ffprobe='D:/Tools/ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe')
    preparations=[];windows=[];paths=[]
    for i,(source,choice) in enumerate(zip(sources,selected)):
        ratio=tempo_ratio(choice['source_bpm'],target)
        origin=choice['source_cue']-entry*ratio
        # Eight seconds of real context on each side of the listening crop.
        begin=origin-8*ratio;end=origin+68*ratio
        if begin<0 or end>source['duration_seconds']:raise ValueError('Insufficient real context')
        context=work/f'context-{i}.wav'
        # Keep overshoots intact until gain staging. PCM16 here would clip
        # stretched mastered originals before the later volume reduction.
        subprocess.run([settings.ffmpeg,'-v','error','-nostdin','-ss',str(begin),'-t',str(end-begin),
                        '-i',source['path'],'-map','0:a:0','-vn','-af',
                        f'rubberband=tempo={ratio:.10f}:pitch=1:channels=together,apad,atrim=duration=76,asetpts=PTS-STARTPTS',
                        '-ac','2','-ar','44100','-c:a','pcm_f32le',str(context)],
                       check=True,capture_output=True,timeout=180)
        data,rate=sf.read(context,dtype='float32',always_2d=True)
        data=data[8*rate:68*rate]
        if data.shape!=(60*44100,2):raise ValueError('Prepared length/channel mismatch')
        preparation_peak=float(np.max(abs(data)))
        if not np.isfinite(data).all():raise ValueError('Nonfinite preparation')
        path=work/f'source-{i}.wav'
        sf.write(path,data,44100,subtype='FLOAT')
        measured=loudness(path,settings)
        gain=min(-20-measured['integrated_lufs'],-3-measured['true_peak_dbfs'])
        data*=10**(gain/20)
        sf.write(path,data,44100,subtype='FLOAT')
        preparations.append({'source_path':source['path'],'source_sha256':source['sha256'],
                             'fit':choice,'tempo_ratio':ratio,'source_at_preview_zero':origin,
                             'source_context_start':begin,'source_context_end':end,'gain_db':gain,
                             'pre_gain_float_peak':preparation_peak,'preparation_format':'float32 stereo',
                             'prepared_sha256':digest(path)})
        windows.append(data);paths.append(path)
    print('Checking exact 60-second prepared stereo sources',flush=True)
    timing=detect_prepared_alignment(paths,entry,exit,Path('D:/AI-DJ-data/timeline/models'))
    timing_path=work/'timing-check.json'
    timing_path.write_text(json.dumps(timing,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({key:timing[key] for key in ('beats','downbeats','bar_support','publication_allowed')}),flush=True)
    require_alignment(timing)
    # Independent first/last parts of the overlap must agree too; whole-window
    # averages may hide a local phase slip.
    from backend.app.research.beat_alignment import marker_alignment
    checks=[]
    for start,end in [(entry+1,30),(30,exit-1)]:
        check=marker_alignment(timing['sources'][0]['beats'],timing['sources'][1]['beats'],start,end,.025)
        if check['status']!='aligned':raise ValueError('Local beat alignment failed')
        checks.append(check)
    progress=np.clip((np.arange(60*44100)/44100-entry)/overlap,0,1).astype(np.float32)
    data=windows[0]*(1-progress[:,None])+windows[1]*progress[:,None]
    raw=work/'linear.wav';sf.write(raw,data,44100,subtype='FLOAT')
    measured=loudness(raw,settings)
    gain=min(-20-measured['integrated_lufs'],-2.5-measured['true_peak_dbfs'])
    encoded=work/'corrected.mp3'
    subprocess.run([settings.ffmpeg,'-v','error','-nostdin','-y','-i',str(raw),
                    '-af',f'volume={gain:.10f}dB,afade=t=in:d=0.015,afade=t=out:st=59.985:d=0.015',
                    '-c:a','libmp3lame','-b:a','256k',str(encoded)],check=True,capture_output=True)
    final=loudness(encoded,settings)
    decoded=subprocess.check_output([settings.ffmpeg,'-v','error','-i',str(encoded),'-ar','44100','-ac','2','-f','f32le','-'])
    samples=np.frombuffer(decoded,dtype='<f4').reshape(-1,2)
    if samples.shape!=(60*44100,2) or not np.isfinite(samples).all() or abs(samples).max()>=1 or final['true_peak_dbfs']>-1:
        raise ValueError('Encoded audio validation failed')
    blocks=samples.reshape(600,4410,2)
    if np.any(np.sqrt(np.mean(blocks.astype(float)**2,axis=(1,2)))<1e-5):raise ValueError('Unexpected dropout')
    # Output beat continuity compared against each audible source in its solo.
    from beat_this.inference import Audio2Beats
    import torch
    tracker=Audio2Beats(checkpoint_path='D:/AI-DJ-data/timeline/models/final0.ckpt',device='cpu',dbn=False)
    with torch.inference_mode():out_beats,out_downs=tracker(samples,44100)
    final_checks=[]
    for index,start,end in [(0,4,entry-1),(1,exit+1,56)]:
        check=marker_alignment(timing['sources'][index]['beats'],out_beats,start,end,.025)
        if check['status']!='aligned':raise ValueError('Encoded solo beat timing changed')
        final_checks.append(check)
    destination=root/'auditions'/('corrected-at-night-stupidisco-'+work.name.removeprefix('attempt-'))
    destination.mkdir()
    report={'version':'corrected-linear-crossfade-1','created_at':datetime.now(timezone.utc).isoformat(),
            'analysis_sha256':digest(analysis_path),'script_sha256':digest(__file__),'work_directory':str(work),
            'target_bpm':target,'overlap_seconds':overlap,'cue_region_seconds':[entry,exit],
            'handoff_seconds':30,'preparations':preparations,'independent_timing':timing,
            'local_beat_checks':checks,'encoded_solo_checks':final_checks,
            'output_beat_markers':list(map(float,out_beats)),'output_downbeat_markers':list(map(float,out_downs)),
            'output':str(destination/'corrected.mp3'),'audio_sha256':digest(encoded),'duration_seconds':60,
            'channels':2,'loudness':final,'peak':float(abs(samples).max()),'post_mix_gain_db':gain,
            'technical_checks_passed':True,'listening_accepted':None,'promoted':False,
            'limitations':['Beat/downbeat evidence is model-predicted, not human truth.',
                           'Phrase and vocal compatibility still require listening.',
                           'New cues and full-context preparation; not an isolated test of one processing change.']}
    import shutil
    shutil.copyfile(encoded,destination/'corrected.mp3')
    (destination/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print('PUBLISHED '+str(destination),flush=True)


if __name__=='__main__':main()
