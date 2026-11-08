"""Source-bounded test plans from explicit reviewed-model predictions."""
from copy import deepcopy
from dataclasses import replace
import math
from backend.app.models import Excerpt, MixPlan, Transition
from .planner import tempo_runs
from .excerpts import choose_excerpt, support


def snap(analysis,seconds):
    rhythm=analysis.get('rhythm',{});bpm=rhythm.get('bpm') or 120
    candidates=[]
    for w in rhythm.get('windows',[]):
        if w['start']-8<=seconds<=w['end']+8:
            origin=w['start']+w['phase'];bar=240/bpm
            value=origin+round((seconds-origin)/bar)*bar
            if 0<=value<analysis['audio']['duration']:candidates.append(value)
    return min(candidates,key=lambda t:abs(t-seconds)) if candidates else seconds


def supported_cue(analysis,preferred,span,maximum_shift=32):
    """Use the prediction as a preference among nearby rhythm-supported cues."""
    duration=analysis['audio']['duration'];candidates=[]
    for window in analysis.get('rhythm',{}).get('windows',[]):
        origin=window['start']+window['phase'];bar=240/window['bpm']
        for step in range(math.ceil((window['start']-origin)/bar),math.floor((window['end']-origin)/bar)+1):
            cue=origin+step*bar
            if (0<=cue and cue+span<duration and abs(cue-preferred)<=maximum_shift
                    and support(analysis,cue,cue+span)>=.65):candidates.append(cue)
    if not candidates:raise ValueError('Model cue has no stable nearby rhythm region. Choose another pair or generate the baseline.')
    return min(candidates,key=lambda t:abs(t-preferred))


def trial_plan(entries,mix_id,seconds=72,predictions=None,model_id=None):
    if len(entries)<2:raise ValueError('A test mix needs at least two songs')
    if predictions is not None and len(predictions)!=len(entries)-1:raise ValueError('One prediction is needed per handoff')
    working=deepcopy(entries)
    # Use regional tempo evidence near the requested cue, not a distant breakdown.
    if predictions:
        for i,entry in enumerate(working):
            hint=predictions[i]['outgoing_source_in'] if i<len(predictions) else predictions[-1]['incoming_source_in']
            windows=entry['analysis'].get('rhythm',{}).get('windows',[])
            if windows:
                nearest=min(windows,key=lambda w:abs((w['start']+w['end'])/2-hint))
                entry['analysis']['rhythm']['bpm']=nearest['bpm']
    targets,_=tempo_runs(working)
    transitions=[];choices=[]
    for i,(a,b) in enumerate(zip(working,working[1:])):
        ra,rb=a['analysis']['rhythm'],b['analysis']['rhythm']
        matched=bool(ra.get('reliable') and rb.get('reliable') and abs(targets[i]-targets[i+1])<1e-6)
        warnings=[];prediction=predictions[i] if predictions is not None else None
        if prediction:
            recipe=prediction['recipe']
            if recipe=='cut':
                warnings.append('Predicted cut is ineligible without reviewed phrase evidence; an eight-bar blend is proposed instead.')
                bars=8
            elif recipe in ('groove_32','controlled_16','eq_8'):bars={'groove_32':32,'controlled_16':16,'eq_8':8}[recipe]
            else:bars=min((8,16,32),key=lambda n:abs(n*240/targets[i]-prediction['overlap_seconds']))
        else:bars=8
        if not matched:
            transition=Transition('boundary_fade',.25,0,('No shared reliable regional tempo; no claimed beatmatch.',))
            warnings.append(transition.warnings[0])
        else:transition=Transition({8:'eq_cut',16:'controlled',32:'smooth'}[bars],bars*240/targets[i],bars,tuple(warnings))
        transitions.append(transition)
        choices.append({'prediction':prediction,'proposed_style':transition.style,'proposed_bars':transition.bars,'notes':warnings})
    if predictions is None:
        excerpts=[]
        for i,entry in enumerate(working):
            excerpt,_=choose_excerpt(entry,targets[i],seconds,transitions[i-1].overlap_seconds if i else 0,
                                     transitions[i].overlap_seconds if i<len(transitions) else 0)
            excerpts.append(excerpt)
    else:
        starts=[None]*len(working);ends=[None]*len(working)
        for i,prediction in enumerate(predictions):
            a,b=working[i:i+2]
            da,db=a['analysis']['audio']['duration'],b['analysis']['audio']['duration']
            ba=a['analysis']['rhythm'].get('bpm') or 120.;bb=b['analysis']['rhythm'].get('bpm') or 120.
            ov=transitions[i].overlap_seconds
            if transitions[i].bars:
                cue_a=supported_cue(a['analysis'],float(prediction['outgoing_source_in']),ov*targets[i]/ba)
                cue_b=supported_cue(b['analysis'],float(prediction['incoming_source_in']),ov*targets[i+1]/bb)
            else:
                cue_a=snap(a['analysis'],float(prediction['outgoing_source_in']))
                cue_b=snap(b['analysis'],float(prediction['incoming_source_in']))
            cue_a=max(0,min(da-ov*targets[i]/ba-.02,cue_a))
            cue_b=max(0,min(db-ov*targets[i+1]/bb-.02,cue_b))
            ends[i]=cue_a+ov*targets[i]/ba
            starts[i+1]=cue_b
            choices[i]['applied_blend_cues']=[cue_a,cue_b]
            for label,requested,applied in (('Outgoing',prediction['outgoing_source_in'],cue_a),('Incoming',prediction['incoming_source_in'],cue_b)):
                if abs(requested-applied)>.05:
                    choices[i]['notes'].append(f'{label} cue moved from {requested:.2f}s to the nearest stable bar candidate at {applied:.2f}s before rendering.')
        first,last=working[0],working[-1]
        ba=first['analysis']['rhythm'].get('bpm') or 120.;bb=last['analysis']['rhythm'].get('bpm') or 120.
        starts[0]=max(0,ends[0]-(transitions[0].overlap_seconds+seconds/2)*targets[0]/ba)
        ends[-1]=min(last['analysis']['audio']['duration'],starts[-1]+(transitions[-1].overlap_seconds+seconds/2)*targets[len(working)-1]/bb)
        excerpts=[]
        for i,entry in enumerate(working):
            bpm=entry['analysis']['rhythm'].get('bpm') or 120.
            excerpt=Excerpt(entry['entry_id'],starts[i],ends[i],entry['analysis']['audio']['duration'],bpm,targets[i])
            if excerpt.source_out<=excerpt.source_in:
                raise ValueError('Model cue order does not fit '+entry['path'].split('\\')[-1]+'. Try another order or generate the baseline.')
            excerpts.append(excerpt)
        for i,t in enumerate(transitions):
            if t.bars and min(support(working[i]['analysis'],excerpts[i].source_out-t.overlap_seconds*targets[i]/excerpts[i].source_bpm,excerpts[i].source_out),
                              support(working[i+1]['analysis'],excerpts[i+1].source_in,excerpts[i+1].source_in+t.overlap_seconds*targets[i+1]/excerpts[i+1].source_bpm))<.5:
                raise ValueError('Model cue falls outside stable rhythm evidence. Choose another song pair or generate the baseline.')
    plan=MixPlan(mix_id,1,tuple(excerpts),tuple(transitions))
    try:plan.validate()
    except ValueError as exc:raise ValueError('Selected songs do not fit the model cues: '+str(exc)+'. Try another order or the baseline.') from exc
    return plan,{'method':'reviewed_cue_model' if predictions is not None else 'ordered_baseline',
                 'model_id':model_id,'strict_join_settings':predictions is not None,'joins':choices,
                 'limitations':['Cue/style imitation is experimental; rendered joins still require listening.']}
