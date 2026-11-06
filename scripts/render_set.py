"""Bounded-memory local stem set render from an ML plan."""
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4
import numpy as np
import soundfile as sf
from backend.app.audio.analyze import analyze
from backend.app.audio.phase import pulse_grid, compare_grids, check_overlap_windows
from backend.app.audio.probe import run_audio, probe
from backend.app.audio.stretch import prepare_excerpt, float_pcm_peak
from backend.app.audio.stem_mix import vocal_schedule
from backend.app.planning.learning import fit_library
from backend.app.planning.planner import build_plan
from backend.app.planning.rhythm import analyze_rhythm
from backend.app.config import Settings
from backend.app.storage import Storage


def main():
    s=Settings.from_env(); storage=Storage(s.data_root);storage.initialize()
    names=['Aaron Hibell, Alex Wann - set me free (official visualizer).mp3','C Sauti.mp3',
           'D Famax (Original Mix).mp3','E Ma Tnsani (Yalla Habibi) (Lyrics).mp3','F Say What.mp3',
           'G The Rapture Pt.III.mp3','I Move (Lyrics).mp3','K Tayna - Si Ai (Marshmello & UKAY Remix).mp3',
           'M Jonas Blue, Malive - Edge Of Desire (Radio Edit).mp3',
           'Nitefreak & Emmanuel Jal - Gorah (Official Full Stream).mp3']
    entries=[]
    for i,name in enumerate(names):
        print(f'Analyzing {i+1}/10: {name}',flush=True)
        path=Path('D:/G1-Drive/Dj/AfroHouse')/name
        a=analyze(path,s,storage);a['rhythm']=analyze_rhythm(path,a,s,storage)
        entries.append({'entry_id':str(i),'path':str(path),'analysis':a})
    plan,details=build_plan(entries,uuid4().hex,requested_seconds=144)
    lookup={e['entry_id']:e for e in entries};ordered=[lookup[e.track_id] for e in plan.excerpts]
    name='set-10-'+uuid4().hex; work=storage.root/'tmp'/name;work.mkdir()
    state={'plan':json.loads(plan.to_json()),'planning':details,'tracks':[],'joins':[]}
    (work/'plan.json').write_text(json.dumps(state,indent=2))
    prepared=[]; lengths=[]
    for i,(entry,cue) in enumerate(zip(ordered,plan.excerpts)):
        print(f'Preparing {i+1}/10: {Path(entry["path"]).name}',flush=True)
        out=work/f'source-{i}.wav'
        prepare_excerpt(Path(entry['path']),out,cue.source_in,cue.source_out,cue.source_bpm,cue.target_bpm,s)
        prepared.append(out);lengths.append(probe(out,s).duration)
    overlaps=[];phases=[]
    for i,t in enumerate(plan.transitions):
        accepted=None
        for bars in ([32,8] if t.bars==32 else [8]):
            overlap=bars*240/plan.excerpts[i].target_bpm
            if overlap>=min(lengths[i],lengths[i+1])/1.1:continue
            try:
                ga=pulse_grid(prepared[i],lengths[i]-overlap,min(30,overlap),60/plan.excerpts[i].target_bpm)
                gb=pulse_grid(prepared[i+1],0,min(30,overlap),60/plan.excerpts[i+1].target_bpm)
                difference=compare_grids(ga,gb,overlap)
                if abs(difference['drift_seconds'])>.025:continue
                delay=difference['incoming_delay_seconds']
                if abs(delay)>.012:
                    cue=plan.excerpts[i+1]; shift=-delay*cue.target_bpm/cue.source_bpm
                    replacement=work/f'corrected-{i+1}.wav'
                    if cue.source_in+shift<0 or cue.source_out+shift>cue.source_duration:
                        delay=difference['incoming_delay_seconds']%(60/cue.target_bpm)
                        run_audio([s.ffmpeg,'-v','error','-nostdin','-i',str(prepared[i+1]),'-af',
                                   f'adelay={round(delay*44100)}S:all=1,atrim=duration={lengths[i+1]}','-c:a','pcm_s16le',str(replacement)])
                    else:
                        prepare_excerpt(Path(ordered[i+1]['path']),replacement,cue.source_in+shift,cue.source_out+shift,cue.source_bpm,cue.target_bpm,s)
                    gb=pulse_grid(replacement,0,min(30,overlap),60/cue.target_bpm)
                    if abs(compare_grids(ga,gb,overlap)['incoming_delay_seconds'])>.015:continue
                    prepared[i+1]=replacement
                checks=check_overlap_windows(prepared[i],prepared[i+1],lengths[i]-overlap,overlap,plan.excerpts[i].target_bpm) if overlap>30 else []
                accepted={'bars':bars,'overlap':overlap,'phase':ga['phase_seconds'],'checks':checks};break
            except ValueError:continue
        if accepted is None:
            beat=60/plan.excerpts[i].target_bpm;ov=32*beat
            for cut in np.arange(4*beat,32+beat,4*beat):
                new_length=lengths[i]-float(cut)
                if new_length<=ov+(overlaps[i-1] if i else 0)+4*beat:continue
                try:
                    ga=pulse_grid(prepared[i],new_length-ov,ov,beat)
                    gb=pulse_grid(prepared[i+1],0,ov,beat)
                    delta=compare_grids(ga,gb,ov)
                    if abs(delta['drift_seconds'])>.025:continue
                    cue=plan.excerpts[i+1];shift=-delta['incoming_delay_seconds']*cue.target_bpm/cue.source_bpm
                    if cue.source_in+shift<0 or cue.source_out+shift>cue.source_duration:continue
                    fixed=work/f'retry-{i+1}.wav'
                    prepare_excerpt(Path(ordered[i+1]['path']),fixed,cue.source_in+shift,cue.source_out+shift,cue.source_bpm,cue.target_bpm,s)
                    gb=pulse_grid(fixed,0,ov,beat)
                    if abs(compare_grids(ga,gb,ov)['incoming_delay_seconds'])>.015:continue
                    trimmed=work/f'trimmed-{i}.wav'
                    run_audio([s.ffmpeg,'-v','error','-nostdin','-i',str(prepared[i]),'-t',str(new_length),'-c:a','pcm_s16le',str(trimmed)])
                    prepared[i]=trimmed;prepared[i+1]=fixed;lengths[i]=probe(trimmed,s).duration
                    accepted={'bars':8,'overlap':ov,'phase':ga['phase_seconds'],'outgoing_trim_seconds':float(cut)};break
                except ValueError:continue
        if accepted is None:
            accepted={'bars':0,'overlap':1.0,'phase':0,'warning':'No reliable pulse alignment; unclaimed beatmatch, one-second handoff.'}
        overlaps.append(accepted['overlap']);phases.append(accepted['phase']);state['joins'].append(accepted)
        print(f'Join {i+1}: {accepted["bars"]} bars',flush=True)
    stems=[]
    for i,path in enumerate(prepared):
        pointer=work/f'stems-{i}.json'
        print(f'Separating {i+1}/10: {Path(ordered[i]["path"]).name}',flush=True)
        worker='D:/AI-DJ-data/separation/gpu-venv/Scripts/python.exe'
        if not Path(worker).exists():worker='D:/AI-DJ-data/separation/venv/Scripts/python.exe'
        subprocess.run([worker,'-m','scripts.separate_vocals',str(path),
                        '--model-dir','D:/AI-DJ-data/separation/models','--cache-root','D:/AI-DJ-data/separation/stems',
                        '--result-file',str(pointer)],check=True)
        stems.append(json.loads(pointer.read_text()))
    starts=[0.0]
    for i in range(9):starts.append(starts[-1]+lengths[i]-overlaps[i])
    total=starts[-1]+lengths[-1]; frames=round(total*44100)
    raw=work/'master.f32'; master=np.memmap(raw,dtype='<f4',mode='w+',shape=(frames,2));master[:]=0
    schedules=[]
    for i in range(9):
        ov=overlaps[i]
        schedules.append(vocal_schedule(stems[i]['vocals'],stems[i+1]['vocals'],lengths[i]-ov,ov,
                                       plan.excerpts[i].target_bpm,fade_bars=8 if state['joins'][i]['bars']==32 else 4))
    for i in range(10):
        graph='[0:a]acrossover=split=180 1800:order=4th[l][m][h];[1:a]acrossover=split=180 1800:order=4th[vl][vm][vh];'
        labels=[]
        for band in ['l','m','h','vl','vm','vh']:
            filters=[]
            for incoming in [True,False]:
                j=i-1 if incoming else i
                if j<0 or j>=9:continue
                ov=overlaps[j]; beat=60/plan.excerpts[i].target_bpm
                if band.startswith('v'):
                    sch=schedules[j]
                    begin=sch['incoming_fade_start_local_seconds'] if incoming else sch['outgoing_fade_start_seconds']
                    width=sch['incoming_fade_duration_seconds'] if incoming else sch['outgoing_fade_duration_seconds']
                    # Stay inside the excerpt and keep adjacent vocal windows apart.
                    width=min(width,max(.1,lengths[i]-begin-.01))
                else:
                    swap=ov/2; long=state['joins'][j]['bars']==32
                    width=(4 if long else .5)*beat if band=='l' else min(64*beat if long else 8*beat,ov/2) if band=='m' else ov
                    begin=(0 if incoming else lengths[i]-ov)+(swap-width/2 if band!='h' else 0)
                filters.append(f'afade=t={"in" if incoming else "out"}:st={max(0,begin):.9f}:d={width:.9f}:curve=hsin')
            label=band+'out';labels.append('['+label+']')
            graph+=f'[{band}]'+(','.join(filters) if filters else 'anull')+f'[{label}];'
        graph+=''.join(labels)+'amix=inputs=6:normalize=0,asetpts=N/SR/TB[out]'
        shaped=work/f'shaped-{i}.f32'
        run_audio([s.ffmpeg,'-v','error','-nostdin','-i',stems[i]['instrumental'],'-i',stems[i]['vocals'],
                   '-filter_complex',graph,'-map','[out]','-f','f32le',str(shaped)])
        block=np.memmap(shaped,dtype='<f4',mode='r').reshape(-1,2)
        offset=round(starts[i]*44100);count=min(len(block),frames-offset)
        for k in range(0,count,65536):master[offset+k:offset+min(count,k+65536)]+=block[k:min(count,k+65536)]
        del block
        state['tracks'].append({'name':Path(ordered[i]['path']).name,'start_seconds':starts[i],'duration':lengths[i]})
        print(f'Mixed {i+1}/10',flush=True)
    master.flush();del master
    peak=float_pcm_peak(raw);gain=min(1,.80/max(peak,1e-8))
    output=storage.path('renders',name+'.mp3')
    run_audio([s.ffmpeg,'-v','error','-nostdin','-f','f32le','-ar','44100','-ac','2','-i',str(raw),
               '-af',f'volume={gain:.12f},afade=t=in:d=1,afade=t=out:st={total-2:.6f}:d=2',
               '-c:a','libmp3lame','-b:a','256k',str(output)],timeout=1800)
    check=work/'decoded.f32'
    run_audio([s.ffmpeg,'-v','error','-xerror','-i',str(output),'-f','f32le',str(check)],timeout=1800)
    encoded_peak=float_pcm_peak(check)
    if encoded_peak>=1:raise ValueError('Output peak validation failed')
    energy=[]
    with check.open('rb') as stream:
        while block:=stream.read(44100*2*4*2):
            values=np.frombuffer(block,dtype='<f4')
            energy.append(float(np.sqrt(np.mean(values**2))))
    if any(value<1e-4 for value in energy[1:-1]):raise ValueError('Unexpected silent window in set')
    info=probe(output,s)
    if abs(info.duration-total)>.15:raise ValueError('Duration mismatch')
    state.update(output=str(output),duration=info.duration,encoded_peak=encoded_peak,master_gain=gain,vocal_schedules=schedules,energy_rms_2s=energy,stems=stems,scratch_dir=str(work))
    report=output.with_suffix('.json');report.write_text(json.dumps(state,indent=2))
    tracklist=output.with_suffix('.txt');tracklist.write_text('\n'.join(f'{int(t["start_seconds"])//60:02d}:{int(t["start_seconds"])%60:02d} {t["name"]}' for t in state['tracks']))
    print(f'Audio: {output}\nTracklist: {tracklist}\nReport: {report}',flush=True)


if __name__=='__main__':main()
