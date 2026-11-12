"""One continuous vocal-protecting handoff with a gradual instrumental intro."""
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

import numpy as np
import soundfile as sf
import torch
from beat_this.inference import Audio2Beats

from backend.app.auditions import loudness
from backend.app.audio.stretch import tempo_ratio
from backend.app.audio.float_prepare import prepare_float_excerpt, preparation_gain, apply_constant_gain
from backend.app.config import Settings
from backend.app.research.beat_alignment import detect_prepared_alignment,require_alignment,marker_alignment
from backend.app.research.steady_bars import stable_spans
from backend.app.research.vocal_handoff import envelopes,require_quiet,activity_rows,VERSION
from scripts.setup_dj_benchmarks import digest

ROOT=Path('D:/AI-DJ-data/experiments/open-dj')


def main():
    base=ROOT/'alignment/phrase-handoff-1'
    analysis_path=ROOT/'alignment/at-night-stupidisco-1/full-beats.json'
    analysis=json.loads(analysis_path.read_text(encoding='utf-8'))
    originals=analysis['sources']
    for source in originals:
        if digest(source['path'])!=source['sha256']:raise ValueError('Original changed')
    selections=[stable_spans(originals[0],136.18)[0],
                stable_spans(originals[1],3.92,minimum_start=0)[0]]
    target=float(np.sqrt(np.prod([item['source_bpm'] for item in selections])))
    ratios=[tempo_ratio(item['source_bpm'],target) for item in selections]
    overlap=32*60/target;entry,end=30-overlap/2,30+overlap/2;fade=30.
    out_fade_source=selections[0]['source_cue']+(fade-entry)*ratios[0]
    out_end_source=selections[0]['source_cue']+overlap*ratios[0]
    in_end_source=selections[1]['source_cue']+overlap*ratios[1]
    rows=[];screening=[]
    for name,offset in [('outgoing',54.),('incoming',0.)]:
        manifest_path=base/(name+'-vocals.json')
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        context_path=base/(name+'-context.wav')
        if digest(context_path)!=manifest['source_sha256'] or manifest['model']['sha256']!='317554b07fe1ea5279a77f2b1520a41ea4b93432560c4ffd08792c30fddf9adc':
            raise ValueError('Vocal screening provenance mismatch')
        vocal,rate=sf.read(manifest['vocals'],dtype='float32',always_2d=True)
        master,master_rate=sf.read(context_path,dtype='float32',always_2d=True)
        if rate!=master_rate:raise ValueError('Screening sample-rate mismatch')
        values=activity_rows(vocal,master,rate,offset)
        (base/(name+'-levels.json')).write_text(json.dumps(values),encoding='utf-8')
        rows.append(values)
        screening.append({'manifest_sha256':digest(manifest_path),'context_sha256':digest(context_path),
                           'vocal_stem_sha256':digest(manifest['vocals']),'source_time_offset_seconds':offset})
    out_rows,in_rows=rows
    # Require quiet throughout outgoing fade, including its leading tail guard;
    # and incoming throughout its complete audible overlap, not just one bar.
    outgoing_evidence=require_quiet(out_rows,out_fade_source-2.,out_end_source+.5)
    incoming_evidence=require_quiet(in_rows,selections[1]['source_cue'],in_end_source)
    active=[row for row in out_rows if row[0]<out_fade_source and row[3]>.15 and row[1]>.02]
    last_active_end=max(row[0]+.5 for row in active)
    if out_fade_source-last_active_end<2:raise ValueError('Outgoing vocal tail guard too short')
    work=base/('attempt-'+uuid4().hex);work.mkdir()
    settings=Settings(data_root=Path('D:/AI-DJ-data'),ffmpeg='D:/Tools/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe',
                      ffprobe='D:/Tools/ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe')
    paths=[];windows=[];preparations=[]
    for i,(source,choice,ratio) in enumerate(zip(originals,selections,ratios)):
        origin=choice['source_cue']-entry*ratio
        path=work/f'source-{i}.wav'
        preparation=prepare_float_excerpt(source['path'],path,origin,60,
            choice['source_bpm'],target,settings,inaudible_before=entry if i else 0.)
        level=loudness(path,settings)
        gain=preparation_gain(level['integrated_lufs'],level['true_peak_dbfs'])
        apply_constant_gain(path,gain)
        data,rate=sf.read(path,dtype='float32',always_2d=True)
        preparations.append({'source_path':source['path'],'source_sha256':source['sha256'],'fit':choice,
            'tempo_ratio':ratio,'source_at_preview_zero':origin,'preparation':preparation,
            'leading_context_padding_seconds':max(0.,8-origin/ratio),
            'source_continuity':'Single continuous decode/stretch; no jumps or loops',
            'gain_db':gain,'prepared_sha256':digest(path)})
        paths.append(path);windows.append(data)
    print('Checking continuous prepared source beats and bars',flush=True)
    timing=detect_prepared_alignment(paths,entry,end,Path('D:/AI-DJ-data/timeline/models'))
    (work/'timing-check.json').write_text(json.dumps(timing,indent=2),encoding='utf-8')
    print(json.dumps({key:timing[key] for key in ('beats','downbeats','bar_support','publication_allowed')}),flush=True)
    require_alignment(timing)
    outgoing,incoming=envelopes(len(windows[0]),44100,entry,fade,end)
    last_vocal_preview=entry+(last_active_end-selections[0]['source_cue'])/ratios[0]
    if not np.all(outgoing[:round(last_vocal_preview*44100)]==1):raise ValueError('Outgoing line was attenuated prematurely')
    data=windows[0]*outgoing[:,None]+windows[1]*incoming[:,None]
    raw=work/'handoff.wav';sf.write(raw,data,44100,subtype='FLOAT')
    measured=loudness(raw,settings);gain=min(-20-measured['integrated_lufs'],-2.5-measured['true_peak_dbfs'])
    encoded=work/'handoff.mp3'
    subprocess.run([settings.ffmpeg,'-v','error','-nostdin','-i',str(raw),'-af',
                    f'volume={gain:.10f}dB,afade=t=in:d=0.015,afade=t=out:st=59.985:d=0.015',
                    '-c:a','libmp3lame','-b:a','256k',str(encoded)],check=True,capture_output=True)
    final=loudness(encoded,settings)
    decoded=subprocess.check_output([settings.ffmpeg,'-v','error','-i',str(encoded),'-ar','44100','-ac','2','-f','f32le','-'])
    decoded=np.frombuffer(decoded,dtype='<f4').reshape(-1,2)
    if decoded.shape!=(60*44100,2) or not np.isfinite(decoded).all() or abs(decoded).max()>=1 or final['true_peak_dbfs']>-1:
        raise ValueError('Encoded format/peak validation failed')
    if np.any(np.sqrt(np.mean(decoded.reshape(600,4410,2).astype(float)**2,axis=(1,2)))<1e-5):raise ValueError('Audio dropout')
    print('Checking encoded timing through gradual handoff',flush=True)
    tracker=Audio2Beats(checkpoint_path='D:/AI-DJ-data/timeline/models/final0.ckpt',device='cpu',dbn=False)
    with torch.inference_mode():beats,downs=tracker(decoded,44100)
    beat_checks=[]
    for label,reference,left,right in [('outgoing',0,4,entry-1),('handoff',0,entry+.5,end-.5),('incoming',1,end+1,56)]:
        result={'part':label,**marker_alignment(timing['sources'][reference]['beats'],beats,left,right,.025)}
        if result['status']!='aligned':raise ValueError('Encoded timing failed: '+str(result))
        beat_checks.append(result)
    down_check=marker_alignment(timing['sources'][0]['downbeats'],downs,entry+.5,end-.5,.07)
    if down_check['status']!='aligned':raise ValueError('Encoded bar alignment uncertain')
    report={'version':VERSION,'created_at':datetime.now(timezone.utc).isoformat(),'work_directory':str(work),
        'analysis_sha256':digest(analysis_path),'script_sha256':digest(__file__),
        'planner_sha256':digest(Path(__file__).parents[1]/'backend/app/research/vocal_handoff.py'),
        'preparations':preparations,'target_bpm':target,'incoming_entry_seconds':entry,
        'outgoing_fade_start_seconds':fade,'transition_end_seconds':end,
        'incoming_gain_at_outgoing_fade':.25,'incoming_fade_seconds':overlap,
        'outgoing_vocal_evidence':outgoing_evidence,'incoming_intro_evidence':incoming_evidence,
        'screening_provenance':screening,
        'last_active_outgoing_source_end':last_active_end,'vocal_tail_guard_seconds':out_fade_source-last_active_end,
        'protected_outgoing_line_ends_preview_seconds':last_vocal_preview,
        'outgoing_fade_source_interval':[out_fade_source,out_end_source],
        'incoming_source_interval':[selections[1]['source_cue'],in_end_source],
        'vocal_evidence_hashes':{name:digest(base/name) for name in ('outgoing-levels.json','incoming-levels.json','outgoing-vocals.json','incoming-vocals.json')},
        'timing':timing,'encoded_beat_checks':beat_checks,'encoded_bar_check':down_check,
        'audio_sha256':digest(encoded),'duration_seconds':60,'channels':2,'loudness':final,'sample_peak':float(abs(decoded).max()),
        'technical_checks_passed':True,'listening_accepted':None,'promoted':False,
        'limitations':['Vocal evidence is estimated activity; no semantic phrase transcription or human boundary labels.',
                       'This uses a sustained quieter passage after the line and an instrumental-dominant intro; musical quality requires listening.']}
    destination=ROOT/'auditions'/('vocal-handoff-'+work.name.removeprefix('attempt-'));destination.mkdir()
    shutil.copyfile(encoded,destination/'handoff.mp3')
    (destination/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print('PUBLISHED '+str(destination),flush=True)


if __name__=='__main__':main()
