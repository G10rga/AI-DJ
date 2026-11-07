"""Shared bounded-memory stem renderer; no fixed catalog or playlist length."""
import json
import subprocess
from pathlib import Path
from dataclasses import replace
import numpy as np
from backend.app.audio.phase import pulse_grid, compare_grids, check_overlap_windows
from backend.app.audio.probe import run_audio, probe
from backend.app.audio.stretch import prepare_excerpt, float_pcm_peak
from backend.app.audio.stem_mix import vocal_schedule
from backend.app.audio.mdx import sha256_file
from backend.app.models import Transition
from backend.app.config import PROJECT_ROOT
from backend.app.db import Database

RENDERER_VERSION = 'stem-set-2'


def separate_local(path, pointer, settings, storage):
    base = storage.root/'separation'
    candidates = [base/'gpu-venv/Scripts/python.exe', base/'venv/Scripts/python.exe', base/'venv/bin/python']
    worker = next((p for p in candidates if p.exists()), None)
    if worker is None:
        raise ValueError('Set up the optional separator environment before rendering stems')
    subprocess.run([str(worker), '-m', 'scripts.separate_vocals', str(path),
                    '--model-dir', str(base/'models'), '--cache-root', str(base/'stems'),
                    '--result-file', str(pointer)], check=True, timeout=1800, cwd=PROJECT_ROOT)
    return json.loads(pointer.read_text(encoding='utf-8'))


def render_set(entries, plan, details, settings, storage, *, separate=separate_local):
    plan.validate()
    if plan.sample_rate != 44100:
        raise ValueError('Stem set rendering currently supports 44100 Hz plans')
    lookup = {entry['entry_id']: entry for entry in entries}
    if len(lookup) != len(entries) or set(lookup) != {e.track_id for e in plan.excerpts}:
        raise ValueError('Every input entry must be rendered exactly once')
    ordered = [lookup[e.track_id] for e in plan.excerpts]
    for entry in ordered:
        if sha256_file(Path(entry['path'])) != entry['analysis']['content_hash']:
            raise ValueError('Source changed since analysis: '+entry['path'])
    s = settings
    storage.initialize()
    storage.require_space(int(sum(e.output_duration for e in plan.excerpts)*44100*2*4*12), s.min_free_bytes)
    database = Database(storage.root/'app.sqlite3')
    database.initialize()
    provenance = {'renderer': RENDERER_VERSION, 'planning': details,
                  'sources': [{'entry_id': e['entry_id'], 'path': e['path'], 'content_hash': e['analysis']['content_hash']} for e in entries]}
    attempt = database.begin_render(plan, provenance)
    name = 'set-'+attempt
    work = storage.root/'tmp'/name
    try:
        work.mkdir()
        state = _render(ordered, plan, details, s, storage, name, work, separate)
        state['attempt_id'] = attempt
        state['published'] = database.finish_render(attempt, Path(state['output']).name, state)
        return state
    except BaseException as exc:
        database.fail_render(attempt, exc)
        raise


def _render(ordered, plan, details, s, storage, name, work, separate):
    settings = s
    state = {'schema_version': 2, 'renderer_version': RENDERER_VERSION,
             'plan': json.loads(plan.to_json()), 'planning': details, 'tracks': [], 'joins': []}
    applied = list(plan.excerpts)
    delays = [0.0] * len(ordered)
    (work/'plan.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
    prepared=[]; lengths=[]
    for i,(entry,cue) in enumerate(zip(ordered,plan.excerpts)):
        print(f'Preparing {i+1}/{len(ordered)}: {Path(entry["path"]).name}',flush=True)
        out=work/f'source-{i}.wav'
        prepare_excerpt(Path(entry['path']),out,cue.source_in,cue.source_out,cue.source_bpm,cue.target_bpm,s)
        prepared.append(out);lengths.append(probe(out,s).duration)
    overlaps=[]
    for i,t in enumerate(plan.transitions):
        accepted=None
        context_joins = details.get('contextual', {}).get('joins', [])
        selected = context_joins[i].get('selected') if i < len(context_joins) else None
        if t.style == 'phrase_cut' and not selected:
            raise ValueError('Phrase cuts require validated contextual boundary evidence')
        if selected:
            if t.style == 'phrase_cut':
                accepted = {'bars': 0, 'overlap': t.overlap_seconds, 'phase': 0, 'style': 'phrase_cut',
                            'context_candidate_id': selected['candidate_id']}
            else:
                checks = check_overlap_windows(prepared[i], prepared[i+1], lengths[i]-t.overlap_seconds,
                                               t.overlap_seconds, plan.excerpts[i].target_bpm)
                if not checks:
                    raise ValueError('Selected contextual transition has no independent pulse checks')
                grid = pulse_grid(prepared[i], lengths[i]-t.overlap_seconds, min(30,t.overlap_seconds), 60/plan.excerpts[i].target_bpm)
                accepted = {'bars': t.bars, 'overlap': t.overlap_seconds, 'phase': grid['phase_seconds'],
                            'checks': checks, 'style': t.style, 'context_candidate_id': selected['candidate_id']}
        if t.style == 'boundary_fade':
            accepted = {'bars': 0, 'overlap': t.overlap_seconds, 'phase': 0,
                        'warning': 'Planned boundary fade; beatmatching is not claimed.'}
        for bars in ([] if accepted else [32,8] if t.bars==32 else [t.bars]):
            overlap=bars*240/plan.excerpts[i].target_bpm
            if overlap <= 0 or overlap+(overlaps[i-1] if i else 0)>=lengths[i] or overlap>=lengths[i+1]:continue
            try:
                candidate_path = prepared[i+1]
                candidate_cue = applied[i+1]
                candidate_delay = delays[i+1]
                ga=pulse_grid(prepared[i],lengths[i]-overlap,min(30,overlap),60/plan.excerpts[i].target_bpm)
                gb=pulse_grid(prepared[i+1],0,min(30,overlap),60/plan.excerpts[i+1].target_bpm)
                difference=compare_grids(ga,gb,overlap)
                if abs(difference['drift_seconds'])>.025:continue
                delay=difference['incoming_delay_seconds']
                if abs(delay)>.012:
                    cue=applied[i+1]; shift=-delay*cue.target_bpm/cue.source_bpm
                    replacement=work/f'corrected-{i+1}-{bars}.wav'
                    if cue.source_in+shift<0 or cue.source_out+shift>cue.source_duration:
                        delay=difference['incoming_delay_seconds']%(60/cue.target_bpm)
                        run_audio([s.ffmpeg,'-v','error','-nostdin','-i',str(prepared[i+1]),'-af',
                                   f'adelay={round(delay*44100)}S:all=1,atrim=duration={lengths[i+1]}','-c:a','pcm_s16le',str(replacement)])
                        candidate_delay += round(delay*44100)/44100
                    else:
                        prepare_excerpt(Path(ordered[i+1]['path']),replacement,cue.source_in+shift,cue.source_out+shift,cue.source_bpm,cue.target_bpm,s)
                        candidate_cue = replace(cue, source_in=cue.source_in+shift, source_out=cue.source_out+shift)
                        candidate_delay = 0.0
                    gb=pulse_grid(replacement,0,min(30,overlap),60/cue.target_bpm)
                    if abs(compare_grids(ga,gb,overlap)['incoming_delay_seconds'])>.015:continue
                    candidate_path=replacement
                checks=check_overlap_windows(prepared[i],candidate_path,lengths[i]-overlap,overlap,plan.excerpts[i].target_bpm)
                prepared[i+1] = candidate_path
                applied[i+1] = candidate_cue
                delays[i+1] = candidate_delay
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
                    cue=applied[i+1];shift=-delta['incoming_delay_seconds']*cue.target_bpm/cue.source_bpm
                    if cue.source_in+shift<0 or cue.source_out+shift>cue.source_duration:continue
                    fixed=work/f'retry-{i+1}-{round(float(cut)*44100)}.wav'
                    prepare_excerpt(Path(ordered[i+1]['path']),fixed,cue.source_in+shift,cue.source_out+shift,cue.source_bpm,cue.target_bpm,s)
                    gb=pulse_grid(fixed,0,ov,beat)
                    if abs(compare_grids(ga,gb,ov)['incoming_delay_seconds'])>.015:continue
                    checks=check_overlap_windows(prepared[i],fixed,new_length-ov,ov,plan.excerpts[i].target_bpm)
                    trimmed=work/f'trimmed-{i}.wav'
                    run_audio([s.ffmpeg,'-v','error','-nostdin','-i',str(prepared[i]),'-t',str(new_length),'-c:a','pcm_s16le',str(trimmed)])
                    prepared[i]=trimmed;prepared[i+1]=fixed;lengths[i]=probe(trimmed,s).duration
                    applied[i] = replace(applied[i], source_out=applied[i].source_out-float(cut)*applied[i].target_bpm/applied[i].source_bpm)
                    applied[i+1] = replace(cue, source_in=cue.source_in+shift, source_out=cue.source_out+shift)
                    delays[i+1] = 0.0
                    accepted={'bars':8,'overlap':ov,'phase':ga['phase_seconds'],'checks':checks,'outgoing_trim_seconds':float(cut)};break
                except ValueError:continue
        if accepted is None:
            accepted={'bars':0,'overlap':min(.25, lengths[i]/4, lengths[i+1]/4),'phase':0,'warning':'No reliable pulse alignment; boundary handoff, no claimed beatmatch.'}
        overlaps.append(accepted['overlap']);state['joins'].append(accepted)
        print(f'Join {i+1}: {accepted["bars"]} bars',flush=True)
    actual = replace(plan, excerpts=tuple(applied), transitions=tuple(
        Transition(join.get('style', 'smooth' if join['bars']==32 else 'controlled' if join['bars']==16 else 'eq_cut' if join['bars'] else 'boundary_fade'),
                   join['overlap'], join['bars'], (join['warning'],) if 'warning' in join else ())
        for join in state['joins']))
    actual.validate()
    state['applied_plan'] = json.loads(actual.to_json())
    state['pcm_delays_seconds'] = delays
    stems=[]
    for i,path in enumerate(prepared):
        pointer=work/f'stems-{i}.json'
        print(f'Separating {i+1}/{len(ordered)}: {Path(ordered[i]["path"]).name}',flush=True)
        result = separate(path, pointer, settings, storage)
        stems.append(result)
    instrument_pcm = []
    if any(join['bars'] for join in state['joins']):
        for i, stem in enumerate(stems):
            pcm = work/f'instrument-pulse-{i}.wav'
            run_audio([s.ffmpeg, '-v', 'error', '-nostdin', '-i', stem['instrumental'], '-c:a', 'pcm_s16le', str(pcm)])
            instrument_pcm.append(pcm)
    for i, join in enumerate(state['joins']):
        if join['bars']:
            join['instrumental_checks'] = check_overlap_windows(
                instrument_pcm[i], instrument_pcm[i+1],
                lengths[i]-overlaps[i], overlaps[i], plan.excerpts[i].target_bpm)
    starts=[0.0]
    for i in range(len(plan.transitions)):starts.append(starts[-1]+lengths[i]-overlaps[i])
    total=starts[-1]+lengths[-1]; frames=round(total*44100)
    raw=work/'master.f32'; master=np.memmap(raw,dtype='<f4',mode='w+',shape=(frames,2));master[:]=0
    schedules=[]
    for i in range(len(plan.transitions)):
        ov=overlaps[i]
        if not state['joins'][i]['bars']:
            schedules.append(None)
            continue
        if 'context_candidate_id' in state['joins'][i]:
            beat = 60/plan.excerpts[i].target_bpm
            fade = min({32:8, 16:4, 8:2}[state['joins'][i]['bars']]*4*beat, ov/3)
            seam = lengths[i]-ov/2
            schedules.append({'outgoing_fade_start_seconds': seam-beat-fade,
                              'outgoing_fade_duration_seconds': fade,
                              'incoming_fade_start_local_seconds': ov/2+beat,
                              'incoming_fade_duration_seconds': fade})
            continue
        schedules.append(vocal_schedule(stems[i]['vocals'],stems[i+1]['vocals'],lengths[i]-ov,ov,
                                       plan.excerpts[i].target_bpm,fade_bars=8 if state['joins'][i]['bars']==32 else 4))
    for i in range(len(ordered)):
        graph='[0:a]acrossover=split=180 1800:order=4th[l][m][h];[1:a]acrossover=split=180 1800:order=4th[vl][vm][vh];'
        labels=[]
        for band in ['l','m','h','vl','vm','vh']:
            filters=[]
            for incoming in [True,False]:
                j=i-1 if incoming else i
                if j<0 or j>=len(plan.transitions):continue
                ov=overlaps[j]; beat=60/plan.excerpts[i].target_bpm
                if not state['joins'][j]['bars']:
                    begin = 0 if incoming else lengths[i]-ov
                    width = ov
                elif band.startswith('v'):
                    sch=schedules[j]
                    begin=sch['incoming_fade_start_local_seconds'] if incoming else sch['outgoing_fade_start_seconds']
                    width=sch['incoming_fade_duration_seconds'] if incoming else sch['outgoing_fade_duration_seconds']
                    # Stay inside the excerpt and keep adjacent vocal windows apart.
                    width=min(width,max(.1,lengths[i]-begin-.01))
                else:
                    swap=ov/2; long=state['joins'][j]['bars']==32; controlled=state['joins'][j]['bars']==16
                    width=(4 if long else 2 if controlled else .5)*beat if band=='l' else min((64 if long else 16 if controlled else 8)*beat,ov/2) if band=='m' else ov
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
        state['tracks'].append({'entry_id':ordered[i]['entry_id'],'name':Path(ordered[i]['path']).name,'start_seconds':starts[i],'duration':lengths[i]})
        print(f'Mixed {i+1}/{len(ordered)}',flush=True)
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
    if abs(check.stat().st_size/(44100*2*4)-total)>.1:raise ValueError('Decoded duration mismatch')
    energy=[]
    with check.open('rb') as stream:
        while block:=stream.read(44100*2*4*2):
            values=np.frombuffer(block,dtype='<f4')
            energy.append(float(np.sqrt(np.mean(values**2))))
    if any(value<1e-4 for value in energy[1:-1]):raise ValueError('Unexpected silent window in set')
    info=probe(output,s)
    if abs(info.duration-total)>.15:raise ValueError('Duration mismatch')
    if info.channels != 2 or info.sample_rate != 44100:raise ValueError('Output format mismatch')
    state.update(attempt_id=name.removeprefix('set-'),output=str(output),duration=info.duration,encoded_peak=encoded_peak,master_gain=gain,vocal_schedules=schedules,energy_rms_2s=energy,stems=stems,scratch_dir=str(work))
    report=output.with_suffix('.json');report.write_text(json.dumps(state,indent=2),encoding='utf-8')
    tracklist=output.with_suffix('.txt');tracklist.write_text('\n'.join(f'{int(t["start_seconds"])//60:02d}:{int(t["start_seconds"])%60:02d} {t["name"]}' for t in state['tracks']),encoding='utf-8')
    return state
