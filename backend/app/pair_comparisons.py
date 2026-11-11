"""Contextual pair auditions and explicit owner listening feedback."""
from dataclasses import asdict
import json
from pathlib import Path
import numpy as np
from .models import MixPlan
from .timelines import TimelineStore
from .planning.preferences import PreferenceStore,features,VERSION as PREFERENCE_VERSION
from scripts.setup_timeline import sha256


def preferences(store):
    return PreferenceStore(store.storage.root/'feedback')


def preference_model(store):
    prefs=preferences(store);path=prefs.root/'ranker.json'
    if path.exists():
        model=json.loads(path.read_text(encoding='utf-8'))
        if model.get('version')==PREFERENCE_VERSION:return model
    return prefs.train()


def enqueue_pair(store,track_ids,use_preferences=False):
    if type(use_preferences) is not bool or not isinstance(track_ids,list) or len(track_ids)!=2 or any(not isinstance(i,str) for i in track_ids):
        raise ValueError('Choose outgoing and incoming songs')
    catalog={s['id']:s for s in store.catalog(internal=True)}
    if any(i not in catalog for i in track_ids):raise ValueError('A selected song is no longer in the library')
    sources=[catalog[i] for i in track_ids]
    if sources[0]['content_hash']==sources[1]['content_hash']:raise ValueError('Choose two different songs')
    timelines=TimelineStore(store.storage.root);records=[]
    for source in sources:
        try:records.append(timelines.for_content(source['content_hash']))
        except KeyError:records.append(None)
    model=preference_model(store) if use_preferences else None
    if model and not model.get('ready'):
        raise ValueError('Learned ranking needs six distinct comparisons across three song pairs. Generate contextual alternatives first.')
    rejected=set();prefs=preferences(store)
    with store.db.connection() as c:
        previous=c.execute("SELECT id,result_json FROM workflow_jobs WHERE kind='pair_audition' AND status='succeeded'").fetchall()
    for row in previous:
        result=json.loads(row['result_json'])
        if (result.get('source_hashes')==[s['content_hash'] for s in sources]
                and prefs.review_state(row['id'])['choice']=='neither'):
            rejected.update(a['candidate_id'] for a in result['alternatives'] if a.get('candidate_id'))
    return store.enqueue('pair_audition',{'sources':sources,'timelines':records,'preference_model':model,
                                        'rejected_candidate_ids':sorted(rejected)})


def candidate_features(candidate,validation):
    """The same deterministic recipe descriptor used to render the candidate."""
    from .auditions import blend_schedule
    from .audio.stem_mix import stem_pair_graph
    plan=MixPlan.from_json(json.dumps(validation['applied_plan']))
    cut=candidate['recipe']=='phrase_cut'
    if cut:recipe={}
    else:
        schedule,mode=blend_schedule(plan,candidate)
        _,recipe=stem_pair_graph([1.,1.],plan.excerpts[0].output_duration,plan.excerpts[1].output_duration,
                                plan.transitions[0].overlap_seconds,plan.excerpts[0].target_bpm,0.,schedule,mode)
    return features({'tracks':[{**asdict(cue),'content_hash':ref['content_hash']} for cue,ref in zip(plan.excerpts,candidate['sources'])],
        'overlap_seconds':plan.transitions[0].overlap_seconds,'target_bpm':plan.excerpts[0].target_bpm,
        'recipe':recipe,'stems':not cut,'requested_candidate':candidate})


def generate_pair(store,job,owner,progress):
    from .auditions import evaluate_pair
    from .planning.contextual import propose_pair
    from scripts.analyze_timeline import analyze_timeline
    sources=job['payload']['sources'];records=[];paths={}
    live=lambda:store.live(job['id'],owner)
    for i,source in enumerate(sources):
        if not live():raise ValueError('Comparison cancelled')
        path=Path(source['path'])
        if sha256(path)!=source['content_hash']:raise ValueError('Selected original changed')
        progress(f'Preparing musical timeline {i+1} of 2: {source["name"]}',.03+.06*i)
        record=job['payload']['timelines'][i]
        if record is None:
            analyze_timeline(path,store.settings,with_vocals=True)
            record=TimelineStore(store.storage.root).for_content(source['content_hash'])
        record={**record,'track_id':str(i)+'-'+record['track_id']}
        records.append(record);paths[record['track_id']]=path
    progress('Choosing phrase-aware cue and technique alternatives',.15)
    batch=propose_pair(*records,maximum=12)
    rejected=set(job['payload'].get('rejected_candidate_ids',[]))
    if rejected:
        batch['candidates']=[c for c in batch['candidates'] if c['id'] not in rejected]
        batch['rejections'] += [{'candidate_id':identity,'reason':'Owner explicitly rejected both alternatives in an earlier comparison'} for identity in sorted(rejected)]
    model=job['payload'].get('preference_model')
    def rank(valid):
        return sorted(valid,key=lambda p:(-float(np.dot(np.array(candidate_features(*p))/model['scale'],model['weights'])),p[0]['id']))
    result=evaluate_pair(batch,paths,store.settings,store.storage,audition_count=2,
                         progress=progress,live=live,rank=rank if model else None)
    if len(result['auditions'])!=2:
        reasons=list(dict.fromkeys(r['reason'] for r in result['rejections'] if r.get('reason')))
        raise ValueError('Could not produce two distinct, technically valid alternatives. '+ ' '.join(reasons[:4]))
    if not live():raise ValueError('Comparison cancelled before publication')
    prefs=preferences(store);alternatives=[]
    for report in result['auditions']:
        path=Path(report['output']);identity=prefs.register(path.with_suffix('.json'))
        candidate=report['requested_candidate']
        alternatives.append({'preference_id':identity,'candidate_id':candidate['id'],'storage_name':path.name,
            'audio_hash':sha256(path),'recipe':candidate['recipe'],'duration_seconds':report['duration'],
            'handoff_seconds':report['handoff_seconds'],'overlap_seconds':report['overlap_seconds'],
            'source_cues':[[cue['source_in'],cue['source_out']] for cue in report['tracks']],
            'loudness':report['loudness'],'evidence':candidate['evidence']})
    for source in sources:
        if sha256(Path(source['path']))!=source['content_hash']:raise ValueError('Source changed during audition rendering')
    return {'alternatives':alternatives,'song_names':[s['name'] for s in sources],
            'source_hashes':[s['content_hash'] for s in sources],
            'timeline_revisions':[{'id':r['timeline_id'],'revision':r['revision']} for r in records],
            'preference_model':model,'validated_candidates':len(result['validations']),
            'rejection_count':len(result['rejections']),'method':'learned_context_ranking' if model else 'contextual_baseline'}


def comparison_audio(store,identity,slot):
    job=store.job(identity)
    if job['kind']!='pair_audition' or job['status']!='succeeded' or slot not in ('a','b'):raise KeyError(identity)
    alternative=job['result']['alternatives'][0 if slot=='a' else 1]
    name=alternative['storage_name'];root=(store.storage.root/'renders').resolve();path=(root/name).resolve()
    if Path(name).name!=name or not path.is_relative_to(root) or not path.is_file():raise KeyError(identity)
    if sha256(path)!=alternative['audio_hash']:raise ValueError('Audition audio changed; generate another comparison')
    return path


def save_feedback(store,identity,choice,revision,notes):
    comparison_audio(store,identity,'a');comparison_audio(store,identity,'b')
    result=store.job(identity)['result'];a,b=result['alternatives']
    return preferences(store).review(identity,a['preference_id'],b['preference_id'],choice,revision,notes)
