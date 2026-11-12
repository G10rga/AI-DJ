"""Adaptive protected handoffs for explicit source placement, not fixed templates."""
from copy import deepcopy
from functools import lru_cache
import json
import math
import numpy as np

from .vocal_preserving import digest, review, source_evidence, source_tempos, region_features, TAIL_GUARD
from ..audio.bar_evidence import regular_bar_spans
from ..audio.analysis_evidence import interval_activity
from ..audio.stretch import tempo_ratio
from ..timelines import canonical

VERSION = 'manual-handoff-1'
PLAN_VERSION = 'vocal-preserving-planner-2'
MIN_FADE_SECONDS = 2.


@lru_cache(maxsize=8)
def _cached_source(serialized):
    evidence,raw=source_evidence(json.loads(serialized))
    anchors=[]
    for bars in (4,2):
        anchors.extend({**span,'support_bars':bars} for span in regular_bar_spans(raw,bars=bars))
    return evidence,raw,anchors


def source_data(record):
    # Include actual effective values, not just IDs/revisions: tampering or a
    # changed analysis can never reuse a previous eligibility result.
    return _cached_source(canonical({k:record[k] for k in ('track_id','timeline_id','revision','effective')}))


def manual_tempos(records, corrections=None):
    tempos=[]
    for index,record in enumerate(records):
        data=source_data(record)
        spans=data[0]['regular_spans'] or data[2]
        if not spans:raise ValueError('Source timing needs analysis or correction')
        tempo=float(np.median([s['source_bpm'] for s in spans]))
        rows=corrections or {}
        outgoing=rows.get(str(index),{})
        incoming=rows.get(str(index-1),{})
        cue=outgoing.get('incoming_at_outgoing',incoming.get('incoming_entry'))
        if cue is not None:
            finish=max(cue+24.,outgoing.get('outgoing_line_end',cue)+10.)
            beats=np.asarray(data[1]['beats']);beats=beats[(beats>=cue)&(beats<=finish)]
            if len(beats)>=24:
                x=np.arange(len(beats));period,origin=np.polyfit(x,beats,1)
                # Every observed beat must support the same local clock.
                if .4<period<.6 and np.max(abs(beats-(origin+x*period)))<=.026:
                    tempo=60/float(period)
                else:
                    downs=np.asarray(data[1]['downbeats']);downs=downs[(downs>=cue)&(downs<=finish)]
                    if len(downs)>=6:
                        x=np.arange(len(downs));period,origin=np.polyfit(x,downs,1)
                        if 1.6<period<2.4 and np.max(abs(downs-(origin+x*period)))<=.06:
                            tempo=240/float(period)
        tempos.append(tempo)
    target=math.exp(sum(math.log(t) for t in tempos)/len(tempos))
    for tempo in tempos:tempo_ratio(tempo,target)
    return tempos,target


def has_intent(correction):
    return bool(correction and any(correction.get(k) is not None for k in
                ('incoming_at_outgoing', 'outgoing_source_out', 'outgoing_line_end')))


def placements(left, right, correction, *, seconds=72., source_bpms=None, target_bpm=None):
    records=[left,right];data=[source_data(r) for r in records]
    evidence,raw=zip(*[(d[0],d[1]) for d in data])
    if source_bpms is None:
        tempos,target=manual_tempos(records,{'0':correction})
        target=target_bpm or target
    else:
        tempos=list(source_bpms);target=target_bpm or math.sqrt(math.prod(tempos))
    if len(tempos)!=2:raise ValueError('Two source tempos are required')
    ratios=[tempo_ratio(t,target) for t in tempos]
    incoming=correction.get('incoming_entry')
    if incoming is None:
        return [],[review('incoming_source_required','Choose the starting point within the second song.',source=1)]
    fields=[('incoming_entry',1),('incoming_at_outgoing',0),('outgoing_source_out',0),('outgoing_line_end',0)]
    for name,side in fields:
        value=correction.get(name)
        if value is not None and (type(value) not in (int,float) or not math.isfinite(value)
                or not 0<=value<=raw[side]['duration_seconds'] or
                (name!='outgoing_source_out' and value==raw[side]['duration_seconds'])):
            raise ValueError('Place source marks inside their original song')
    bar=240/tempos[0];minimum=4*bar;fade_preference=4*bar
    line=correction.get('outgoing_line_end');explicit_end=correction.get('outgoing_source_out')
    desired=correction.get('incoming_at_outgoing')
    if desired is None:
        desired=max(0.,(line+TAIL_GUARD-fade_preference) if line is not None else
                    explicit_end-8*bar if explicit_end is not None else seconds-8*bar)
    if explicit_end is not None and explicit_end<=desired:
        return [],[review('placement_order','The first song must finish after the second song enters. Move the finish marker or clear it for an automatic ending.',source=0)]
    anchors=[d[2] for d in data]
    incoming_anchors=sorted(anchors[1],key=lambda a:abs(a['source_cue']-incoming))
    incoming_anchors=[a for a in incoming_anchors if abs(a['source_cue']-incoming)<=8.][:8]
    if not incoming_anchors or not anchors[0]:
        return [],[review('local_timing_unknown','Local beat evidence is missing near this placement. Correct source timing in the timeline editor; the entry and finish marks can stay saved.')]
    options=[]
    for b in incoming_anchors:
        phase=(b['source_cue']-incoming)/ratios[1]
        for a in anchors[0]:
            entry=a['source_cue']-phase*ratios[0]
            if entry<0 or abs(entry-desired)>bar+.05:
                continue
            end=explicit_end
            if line is not None:
                guard=line+TAIL_GUARD
                if end is None:
                    end=min(raw[0]['duration_seconds'],max(guard,entry+minimum-fade_preference)+fade_preference)
                fade=max(guard,entry+60/tempos[0],end-fade_preference)
            else:
                if end is None:
                    ends=[t+fade_preference for t in raw[0]['downbeats']
                          if t>=entry+60/tempos[0] and t+fade_preference<=raw[0]['duration_seconds']
                          and t+fade_preference-entry>=minimum
                          and interval_activity(evidence[0]['vocal_activity'],max(0.,t-TAIL_GUARD),t+fade_preference)['status']=='quieter_candidate']
                    end=min(ends) if ends else None
                if end is None:continue
                starts=[max(entry+60/tempos[0],end-fade_preference)]
                starts += [t for t in raw[0]['downbeats'] if starts[0]<=t<=end-MIN_FADE_SECONDS*ratios[0]]
                starts=[t for t in starts if interval_activity(evidence[0]['vocal_activity'],max(0.,t-TAIL_GUARD),end)['status']=='quieter_candidate']
                if not starts:continue
                fade=min(starts)
            if (end-entry<minimum-.05 or end-fade<MIN_FADE_SECONDS*ratios[0]
                    or end>raw[0]['duration_seconds'] or fade<=entry):
                continue
            overlap=(end-entry)/ratios[0]
            if incoming+overlap*ratios[1]>raw[1]['duration_seconds']-4*ratios[1]:
                continue
            features=[region_features(records[0]['effective'],entry,end),
                      region_features(records[1]['effective'],incoming,incoming+overlap*ratios[1])]
            if any(f is None or f['rms']<=1e-6 for f in features):continue
            options.append({'entry':entry,'incoming':incoming,'fade':fade,'end':end,'overlap':overlap,
                'tempos':tempos,'target':target,'ratios':ratios,'anchors':[a,b],'features':features,
                'distance':abs(entry-desired),'desired':desired})
    options.sort(key=lambda o:(o['distance'],-min(a['support_bars'] for a in o['anchors']),abs(o['overlap']-8*240/target)))
    if not options:
        if line is None:
            message='Mark where the last outgoing vocal line finishes so the app can protect it. Your entry and finish choices remain saved.'
            code='vocal_end_required'
        elif explicit_end is not None and explicit_end<line+TAIL_GUARD+MIN_FADE_SECONDS*ratios[0]:
            message=f'The first-song finish is too early for the vocal ending at {line:.3f}s and a gradual fade. Move only the finish marker later, or clear it for an automatic ending.'
            code='finish_before_vocal_tail'
        else:
            message='This placement needs at least four bars of overlap and enough audio in both songs. Move the finish later or clear it for an automatic ending.'
            code='placement_audio_bounds'
        return [],[review(code,message,source=0)]
    return options[:1],[]


def estimate(left,right,correction,**kwargs):
    options,items=placements(left,right,correction,**kwargs)
    if not options:return {'status':'needs_input','review_items':items}
    o=options[0]
    return {'status':'estimated','confirmation_required':not correction.get('vocal_confirmed'),
        'placement':{'requested_entry':correction.get('incoming_at_outgoing'),
            'outgoing_entry':o['entry'],'incoming_source_start':o['incoming'],
            'outgoing_fade_start':o['fade'],'outgoing_finish':o['end'],
            'overlap_seconds':o['overlap'],'entry_adjustment_seconds':o['entry']-o['desired']},
        'review_items':[]}


def propose(left,right,*,seconds=72.,maximum=12,source_bpms=None,target_bpm=None,prediction=None,correction=None):
    if not correction or not correction.get('vocal_confirmed'):
        return {'version':VERSION,'candidates':[],'review_items':[review('listening_confirmation_required','Confirm the source sections after listening before rendering this placement.')]}
    if prediction and prediction.get('recipe') not in (None,'protected_vocal','plain_crossfade'):
        return {'version':VERSION,'candidates':[],'review_items':[review('model_recipe_unsupported','The requested recipe is unavailable; no substitute was selected.')]}
    options,items=placements(left,right,correction,seconds=seconds,source_bpms=source_bpms,target_bpm=target_bpm)
    candidates=[];evidence=[source_data(r)[0] for r in (left,right)]
    for o in options:
        fades=(('protected_vocal',.25),('protected_vocal',.15))
        if correction.get('outgoing_line_end') is not None and o['entry']>=correction['outgoing_line_end']+TAIL_GUARD:
            fades+=(('plain_crossfade',0.),)
        for recipe,bed in fades:
            if prediction and prediction.get('recipe') not in (None,recipe):continue
            fade=o['fade'] if recipe=='protected_vocal' else o['entry']
            if recipe=='plain_crossfade' and o['end']-fade<MIN_FADE_SECONDS*o['ratios'][0]:continue
            activity=[]
            for side,(start,end) in enumerate(((max(0.,fade-TAIL_GUARD),o['end']),
                                               (o['incoming'],o['incoming']+o['overlap']*o['ratios'][1]))):
                a=interval_activity(evidence[side]['vocal_activity'],start,end)
                if side==1 or correction.get('outgoing_line_end') is not None:
                    a={**a,'estimated_status':a['status'],'status':'human_verified','human_correction':deepcopy(correction)}
                activity.append(a)
            energy=20*math.log10(o['features'][1]['rms']/o['features'][0]['rms'])
            ca,cb=[np.asarray(f['chroma']) for f in o['features']];den=float(np.linalg.norm(ca)*np.linalg.norm(cb))
            harmonic=float(1-np.dot(ca,cb)/den) if den>1e-8 else None
            c={'version':VERSION,'recipe':recipe,'bars':round(o['overlap']*o['target']/240,3),
                'overlap_seconds':o['overlap'],'fade_start_local_seconds':(fade-o['entry'])/o['ratios'][0],
                'incoming_gain_at_outgoing_fade':bed,'source_cues':[o['entry'],o['incoming']],
                'source_bpms':o['tempos'],'target_bpm':o['target'],'source_ratios':o['ratios'],
                'sources':[deepcopy(e['reference']) for e in evidence],
                'requested':{'seconds':seconds,'prediction':deepcopy(prediction),'correction':deepcopy(correction)},
                'applied':{'recipe':recipe,'source_cues':[o['entry'],o['incoming']],
                    'outgoing_fade_source':fade,'outgoing_source_out':o['end'],'overlap_seconds':o['overlap'],
                    'entry_adjustment_seconds':o['entry']-o['desired']},
                'evidence':{'outgoing_quiet_guard':activity[0],'incoming_full_overlap':activity[1],
                    'local_bar_anchors':deepcopy(o['anchors']),'full_interval_timing':'requires independent actual original/prepared/encoded validation',
                    'energy_change_db':energy,'harmonic_distance':harmonic,'vocal_safety_margin':.15},
                'rank':[0,.15,int(recipe=='protected_vocal'),bed,-o['distance']],
                'rank_method':'explicit placement, adaptive vocal hold, independently verified timing'}
            c['id']=digest(c);candidates.append(c)
    if not candidates and not items:items=[review('requested_recipe_conflict','The requested plain fade would conflict with the protected vocal; choose a protected handoff.')]
    return {'version':VERSION,'candidates':candidates[:maximum],'review_items':items,'eligible_count':len(candidates),'limit':maximum}
