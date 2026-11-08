"""Run one pinned local UI job; the server manager owns its lease and status."""
import argparse,json,os,subprocess,traceback
from pathlib import Path
from uuid import uuid4
from backend.app.config import Settings,PROJECT_ROOT
from backend.app.workflow import Workflow
from backend.app.planning.decision_learning import dataset_from_snapshot,source_features
from scripts.setup_timeline import sha256


def cpu(settings,kind,request,destination,model=None):
    runtime=settings.data_root/('timeline/venv/Scripts/python.exe' if os.name=='nt' else 'timeline/venv/bin/python')
    if not runtime.is_file():raise ValueError('The local CPU training environment is unavailable')
    command=[str(runtime),'-m','scripts.decision_worker',kind,str(request),str(destination)]
    if model:command+=['--model',str(model)]
    subprocess.run(command,cwd=PROJECT_ROOT,check=True,timeout=1800)


def execute(store,job,owner,work):
    settings=store.settings;identity=job['id'];payload=job['payload']
    progress=lambda text,amount:store.progress(identity,owner,text,amount)
    if job['kind']=='train':
        progress('Reading included review snapshots',.05)
        dataset=dataset_from_snapshot(payload['snapshot'],store.reviews.references,
            lambda i,n:progress(f'Preparing audio context {i+1} of {n}',.05+.35*i/n))
        request=work/'dataset.json';request.write_text(json.dumps(dataset,allow_nan=False),encoding='utf-8')
        progress('Training cue and overlap model',.45)
        staged=work/'model';cpu(settings,'train',request,staged)
        manifest=json.loads((staged/'manifest.json').read_text(encoding='utf-8'))
        for name,digest in manifest['files'].items():
            if sha256(staged/name)!=digest:raise ValueError('Training artifact failed integrity validation')
        progress('Saving experimental model and evaluation',.95)
        name='decision-model-'+identity;destination=store.storage.root/'models'/name
        staged.rename(destination)
        model={'id':identity,'storage_name':name,'manifest_hash':sha256(destination/'manifest.json'),
               'review_fingerprint':payload['snapshot']['review_fingerprint'],'report':manifest['report'],
               'status':'experimental','active':False}
        return {'model':model}
    from backend.app.library import collect_entries,persist_plan
    from backend.app.planning.decision_plan import trial_plan
    from backend.app.rendering import render_set
    sources=payload['sources']
    for source in sources:
        if sha256(Path(source['path']))!=source['content_hash']:raise ValueError('Selected source changed: '+source['name'])
    entries=[]
    for i,source in enumerate(sources):
        progress(f'Analyzing song {i+1} of {len(sources)}: {source["name"]}',.05+.3*i/len(sources))
        entry=collect_entries([Path(source['path'])],settings,store.storage)[0]
        entry['entry_id']=f'ui-{identity}-{i}'
        entries.append(entry)
    predictions=None
    if not payload['baseline']:
        model,_=store.model(payload['model_id']);features=[]
        for source,entry in zip(sources,entries):
            duration=entry['analysis']['audio']['duration']
            features.append(source_features(store.reviews.references._features({**source,'duration_seconds':duration}),duration))
        pairs=[{'x':a+b,'durations':[entries[i]['analysis']['audio']['duration'],entries[i+1]['analysis']['audio']['duration']]}
               for i,(a,b) in enumerate(zip(features,features[1:]))]
        request=work/'prediction-request.json';request.write_text(json.dumps(pairs),encoding='utf-8')
        output=work/'predictions.json';progress('Predicting cue positions and overlap',.4)
        cpu(settings,'predict',request,output,model)
        predictions=json.loads(output.read_text(encoding='utf-8'))
    progress('Planning and validating source bounds',.45)
    plan,details=trial_plan(entries,uuid4().hex,payload['seconds'],predictions,payload.get('model_id'))
    details['workflow_job_id']=identity
    persist_plan(entries,plan,settings)
    progress('Rendering and independently checking audio; this can take several minutes',.5)
    rendered=render_set(entries,plan,details,settings,store.storage,publish_guard=lambda:store.live(identity,owner))
    if not rendered['published']:raise ValueError('Render finished without publishing a playable revision')
    progress('Finalizing playable test mix',.98)
    return {'mix_id':plan.mix_id,'revision':plan.revision,'duration_seconds':rendered['duration'],
            'model_id':payload.get('model_id'),'baseline':payload['baseline'],
            'audio_url':f'/api/v1/mixes/{plan.mix_id}/audio?revision={plan.revision}',
            'download_url':f'/api/v1/mixes/{plan.mix_id}/audio?revision={plan.revision}&download=true',
            'warnings':list(dict.fromkeys([w for choice in details['joins'] for w in choice['notes']]+
                [join['warning'] for join in rendered.get('joins',[]) if join.get('warning')])),
            'applied_transitions':[{'bars':j['bars'],'seconds':j['overlap']} for j in rendered['joins']],
            'planning':details}


def main():
    p=argparse.ArgumentParser();p.add_argument('identity');p.add_argument('owner');a=p.parse_args()
    store=Workflow(Settings.from_env());work=store.storage.root/'tmp'/('workflow-'+a.identity)
    try:
        job=store.job(a.identity,internal=True)
        if job['owner']!=a.owner or not store.live(a.identity,a.owner):raise ValueError('Job lease is no longer active')
        result=execute(store,job,a.owner,work)
    except Exception as exc:
        traceback.print_exc();result={'error':str(exc)}
    (work/'result.json').write_text(json.dumps(result,allow_nan=False),encoding='utf-8')
    if 'error' in result:raise SystemExit(1)

if __name__=='__main__':main()
