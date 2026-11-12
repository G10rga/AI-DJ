"""Durable, revisioned transition correction and publication boundaries."""
from copy import deepcopy
import json
import math
from pathlib import Path
from uuid import uuid4

from .audio.mdx import sha256_file
from .planning.vocal_preserving import PIPELINE
from .timelines import canonical

LEGACY = 'legacy-v1'


def pipeline(store, requested=None):
    if requested is None:
        with store.db.connection() as c:
            row = c.execute("SELECT value_json FROM app_settings WHERE key='default_pipeline'").fetchone()
        requested = json.loads(row[0])['pipeline'] if row else LEGACY
    if requested not in (LEGACY, PIPELINE):
        raise ValueError('Unsupported pipeline version')
    return requested


def capture(store, job, owner, records):
    context = {'sources':job['payload']['sources'], 'records':records,
               'seconds':job['payload'].get('seconds',72), 'pipeline':PIPELINE}
    with store.db.connection() as c:
        c.execute('BEGIN IMMEDIATE')
        if not store.live(job['id'],owner): raise ValueError('Job lease is no longer active')
        old = c.execute('SELECT snapshot_json FROM transition_contexts WHERE job_id=?',(job['id'],)).fetchone()
        if old and old[0] != canonical(context): raise ValueError('Pinned job evidence changed')
        c.execute('INSERT OR IGNORE INTO transition_contexts VALUES (?,?)',(job['id'],canonical(context)))
        c.execute('INSERT OR IGNORE INTO transition_reviews VALUES (?,0,?,CURRENT_TIMESTAMP)',
                  (job['id'],canonical(job['payload'].get('corrections') or {})))


def unconfirmed_marks(corrections, join_index=None):
    """Saved marks are not a listening confirmation or an automatic override."""
    items = []
    for key, row in corrections.items():
        if join_index is not None and int(key) != join_index:
            continue
        marked = any(row.get(name) is not None for name in
                     ('outgoing_line_end', 'outgoing_source_out', 'incoming_entry', 'incoming_at_outgoing', 'ending_source_out'))
        if marked and not row.get('vocal_confirmed'):
            items.append({'code': 'listening_confirmation_required', 'join_index': int(key),
                'source_index': None, 'details': {},
                'message': f'Transition {int(key)+1}: source marks are saved, but listening confirmation is unchecked. '
                    'Listen to the marked source sections, then check the listening confirmation and save before previewing.',
                'actions': ['Confirm the source boundaries after listening, then save and preview.']})
    return items


def state(store, identity):
    job = store.job(identity,internal=True)
    if job['payload'].get('pipeline') != PIPELINE: raise ValueError('This job uses the current pipeline')
    with store.db.connection() as c:
        context = c.execute('SELECT snapshot_json FROM transition_contexts WHERE job_id=?',(identity,)).fetchone()
        rows = c.execute('SELECT * FROM transition_reviews WHERE job_id=? ORDER BY revision',(identity,)).fetchall()
        children = c.execute("SELECT id FROM workflow_jobs WHERE json_extract(payload_json,'$.parent_job_id')=? ORDER BY rowid DESC",(identity,)).fetchall()
    if context is None: raise ValueError('Musical evidence is still being prepared; refresh shortly')
    context = json.loads(context[0]); current = rows[-1]
    sources = []
    for i,(source,record) in enumerate(zip(context['sources'],context['records'])):
        data = record['effective']
        sources.append({'index':i,'name':source['name'],'duration_seconds':data['duration_seconds'],
            'features':data.get('features',[]),'beats':data['beats']['times'],'downbeats':data['downbeats']['times'],
            'vocal_activity':data.get('vocal_activity',[]),'sections':data.get('sections',[]),
            'timeline_id':record['timeline_id'],'track_id':record['track_id'],'timeline_revision':record['revision'],
            'audio_url':f'/api/v1/learning/jobs/{identity}/transition-review/sources/{i}/audio'})
    children = [store.job(row[0]) for row in children]
    corrections = json.loads(current['snapshot_json'])
    original_items = (job.get('result') or {}).get('review_items', [])
    review_items = unconfirmed_marks(corrections)
    if not review_items:
        review_items = deepcopy(original_items)
        for child in reversed(children):
            if (child['payload'].get('review_revision') != current['revision']
                    or child['status'] not in ('succeeded', 'needs_review')):
                continue
            child_items = deepcopy((child.get('result') or {}).get('review_items', []))
            if child['kind'] == 'join_preview':
                index = child['payload']['join_index']
                for item in child_items:
                    item['join_index'] = index
                    if item.get('source_index') is not None:
                        item['source_index'] += index
                review_items = [item for item in review_items if item.get('join_index') != index]+child_items
            else:
                review_items = child_items
    return {'job_id':identity,'kind':job['kind'],'status':job['status'],'pipeline':PIPELINE,'revision':current['revision'],
        'corrections':corrections,'history':[{'revision':r['revision'],'created_at':r['created_at']} for r in rows],
        'sources':sources,'seconds':context['seconds'],'review_items':review_items,'original_review_items':original_items,
        'plan':(job.get('result') or {}).get('plan'),'children':children,
        'parent_job_id':job['payload'].get('parent_job_id')}


def validate_corrections(value, context):
    if not isinstance(value,dict): raise ValueError('Provide the transition corrections')
    allowed = {'outgoing_line_end','outgoing_source_out','incoming_entry','incoming_at_outgoing','vocal_confirmed','ending_source_out'}
    for key, row in value.items():
        if not key.isdecimal() or not 0 <= int(key) < len(context['sources'])-1 or not isinstance(row,dict) or set(row)-allowed:
            raise ValueError('Invalid transition correction')
        i = int(key)
        for name,side in (('outgoing_line_end',i),('outgoing_source_out',i),('incoming_entry',i+1),('incoming_at_outgoing',i),('ending_source_out',i+1)):
            t = row.get(name)
            duration=context['records'][side]['effective']['duration_seconds']
            if t is not None and (type(t) not in (int,float) or not math.isfinite(t) or not 0 <= t <= duration
                                  or (name!='outgoing_source_out' and t==duration)):
                raise ValueError('Correction must be finite seconds inside its original song')
        if type(row.get('vocal_confirmed',False)) is not bool: raise ValueError('Confirm the vocal boundaries explicitly')
        if row.get('vocal_confirmed') and (row.get('incoming_entry') is None or
                not any(row.get(k) is not None for k in ('outgoing_line_end','incoming_at_outgoing','outgoing_source_out'))):
            raise ValueError('Mark the incoming source start and an outgoing placement before confirming')
        if row.get('ending_source_out') is not None and i != len(context['sources'])-2:
            raise ValueError('Only the final song can have a corrected ending')


def save(store,identity,expected_revision,corrections):
    if type(expected_revision) is not int: raise ValueError('Provide the current review revision')
    with store.db.connection() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT snapshot_json FROM transition_contexts WHERE job_id=?',(identity,)).fetchone()
        current = c.execute('SELECT MAX(revision) FROM transition_reviews WHERE job_id=?',(identity,)).fetchone()[0]
        if not row: raise KeyError(identity)
        if current != expected_revision: raise ValueError('Review changed; reload before saving corrections')
        validate_corrections(corrections,json.loads(row[0]))
        c.execute('INSERT INTO transition_reviews VALUES (?,?,?,CURRENT_TIMESTAMP)',(identity,current+1,canonical(corrections)))
    return state(store,identity)


def placement(store,identity,expected_revision,corrections,join_index):
    """Read-only geometry estimate; never creates confirmation, plans or jobs."""
    from .timelines import TimelineStore
    from .planning.manual_handoff import estimate,manual_tempos
    with store.db.connection() as c:
        context=c.execute('SELECT snapshot_json FROM transition_contexts WHERE job_id=?',(identity,)).fetchone()
        revision=c.execute('SELECT MAX(revision) FROM transition_reviews WHERE job_id=?',(identity,)).fetchone()[0]
    if not context:raise KeyError(identity)
    if type(expected_revision) is not int or revision!=expected_revision:
        raise ValueError('Review changed; reload before estimating placement')
    context=json.loads(context[0]);validate_corrections(corrections,context)
    if type(join_index) is not int or not 0<=join_index<len(context['sources'])-1:
        raise ValueError('Choose a valid transition')
    records=[TimelineStore(store.storage.root).get(r['track_id'],r['timeline_id']) for r in context['records']]
    try:
        tempos,target=manual_tempos(records,corrections)
        result=estimate(*records[join_index:join_index+2],corrections.get(str(join_index),{}),
            seconds=context['seconds'],source_bpms=tempos[join_index:join_index+2],target_bpm=target)
    except ValueError as exc:
        return {'status':'needs_input','review_items':[{'code':'local_timing_unknown','message':str(exc)}],'revision':revision}
    return {**result,'revision':revision}


def enqueue(store,identity,expected_revision,*,join_index=None):
    parent = store.job(identity,internal=True)
    if parent['kind']=='join_preview': raise ValueError('Resume from the original generation review to preserve all songs')
    if parent['status'] in ('queued','running','cancelled'): raise ValueError('Wait for the review job to finish')
    from .timelines import TimelineStore
    timeline_store=TimelineStore(store.storage.root)
    with store.db.connection() as c:
        c.execute('BEGIN IMMEDIATE')
        context = c.execute('SELECT snapshot_json FROM transition_contexts WHERE job_id=?',(identity,)).fetchone()
        current = c.execute('SELECT revision,snapshot_json FROM transition_reviews WHERE job_id=? ORDER BY revision DESC LIMIT 1',(identity,)).fetchone()
        if not context or not current: raise KeyError(identity)
        if type(expected_revision) is not int or current['revision'] != expected_revision:
            raise ValueError('Review changed; reload before preview or resume')
        context = json.loads(context[0]); corrections = json.loads(current['snapshot_json'])
        confirmation_items = unconfirmed_marks(corrections, join_index)
        if confirmation_items:
            raise ValueError(confirmation_items[0]['message'])
        context['records']=[timeline_store.get(record['track_id'],record['timeline_id']) for record in context['records']]
        from .planning.manual_handoff import estimate,has_intent,manual_tempos
        selected=[join_index] if join_index is not None else list(range(len(context['sources'])-1))
        if any(corrections.get(str(i),{}).get('vocal_confirmed') and has_intent(corrections.get(str(i))) for i in selected):
            tempos,target=manual_tempos(context['records'],corrections)
            for i in selected:
                row=corrections.get(str(i),{})
                if not row.get('vocal_confirmed') or not has_intent(row):continue
                result=estimate(*context['records'][i:i+2],row,seconds=context['seconds'],
                                source_bpms=tempos[i:i+2],target_bpm=target)
                if result['status']!='estimated':raise ValueError(result['review_items'][0]['message'])
        payload = deepcopy(parent['payload'])
        payload.update(parent_job_id=identity,review_revision=expected_revision,corrections=corrections,
                       foundation_records=context['records'],baseline=True)
        if join_index is not None:
            if type(join_index) is not int or not 0 <= join_index < len(context['sources'])-1:
                raise ValueError('Choose a valid transition')
            payload.update(sources=context['sources'][join_index:join_index+2],
                foundation_records=context['records'][join_index:join_index+2],
                corrections={'0':corrections[str(join_index)]} if str(join_index) in corrections else {},join_index=join_index)
        kind = 'join_preview' if join_index is not None else parent['kind'] if parent['kind'] != 'join_preview' else 'test_mix'
        # Same transaction as revision check: a concurrent save cannot change the
        # snapshot between validation and enqueueing.
        key = __import__('hashlib').sha256((kind+canonical(payload)).encode()).hexdigest()
        existing = c.execute("SELECT id FROM workflow_jobs WHERE request_key=? AND status IN ('queued','running')",(key,)).fetchone()
        child = existing[0] if existing else uuid4().hex
        if not existing:
            c.execute('INSERT INTO workflow_jobs(id,kind,request_key,status,payload_json) VALUES (?,?,?,\'queued\',?)',
                      (child,kind,key,canonical(payload)))
    return store.job(child)


def source_audio(store,identity,index):
    with store.db.connection() as c:
        row=c.execute('SELECT snapshot_json FROM transition_contexts WHERE job_id=?',(identity,)).fetchone()
    if row is None: raise KeyError(identity)
    sources=json.loads(row[0])['sources']
    if not 0 <= index < len(sources): raise KeyError(index)
    source=sources[index]; path=Path(source['path']).resolve(strict=True)
    if sha256_file(path)!=source['content_hash']: raise ValueError('Original changed; re-import it before reviewing')
    return path


def media(store,identity,slot='mix'):
    with store.db.connection() as c:
        row=c.execute('''SELECT p.* FROM improved_plans p JOIN workflow_jobs j ON j.id=p.job_id
            WHERE p.job_id=? AND p.slot=? AND j.status='succeeded' ''',(identity,slot)).fetchone()
    if row is None: raise KeyError(identity)
    path=store.storage.path('renders',row['storage_name'])
    if not path.exists() or sha256_file(path)!=row['audio_hash']: raise ValueError('Saved audio changed or is unavailable')
    return path


def register_artifacts(store,c,job,result):
    from .models import ImprovedPlan
    reports=result.get('alternatives') or ([result] if result.get('output') else [])
    for i, report in enumerate(reports):
        path=Path(report['output']).resolve(strict=True)
        if path != store.storage.path('renders',path.name) or sha256_file(path)!=report['audio_sha256']:
            raise ValueError('Completed audio failed integrity validation')
        slot=('a' if i==0 else 'b') if result.get('alternatives') else 'mix'
        saved=ImprovedPlan.from_report(report)
        c.execute('INSERT INTO improved_plans VALUES (?,?,?,?,?,?)',
            (job['id'],slot,saved.to_json(),canonical(report),path.name,report['audio_sha256']))
        report['audio_url']=f'/api/v1/learning/jobs/{job["id"]}/audio/{slot}'
        report['download_url']=report['audio_url']+'?download=true'
        if result.get('alternatives'):
            candidate=report['plan']['joins'][0]['candidate']; join=report['plan']['joins'][0]
            report.update(storage_name=path.name,audio_hash=report['audio_sha256'],candidate_id=candidate['id'],
                recipe=candidate['recipe'],handoff_seconds=(join['entry_seconds']+join['end_seconds'])/2,overlap_seconds=candidate['overlap_seconds'])


def choose_default(store,identity,approved):
    job=store.job(identity,internal=True)
    if approved is not True or job['status']!='succeeded' or job['kind']!='test_mix' or job['payload'].get('pipeline')!=PIPELINE:
        raise ValueError('Listen to a completed improved mix and explicitly approve it before making this pipeline the default')
    media(store,identity)
    with store.db.connection() as c:
        c.execute("INSERT OR REPLACE INTO app_settings VALUES ('default_pipeline',?)",(canonical({'pipeline':PIPELINE,'approved_job_id':identity}),))
    return {'pipeline':PIPELINE,'approved_job_id':identity}


def listening_state(store,identity):
    with store.db.connection() as c:
        row=c.execute('SELECT * FROM improved_listening_reviews WHERE job_id=? ORDER BY revision DESC LIMIT 1',(identity,)).fetchone()
    return {'revision':row['revision'],'choice':row['choice'],'notes':row['notes']} if row else {'revision':0,'choice':None,'notes':''}


def listening_feedback(store,identity,choice,revision,notes):
    if choice not in ('a','b','tie','neither') or type(revision) is not int or not isinstance(notes,str) or len(notes)>1000:
        raise ValueError('Choose A, B, tie or neither and a valid listening note')
    with store.db.connection() as c:
        c.execute('BEGIN IMMEDIATE')
        current=c.execute('SELECT COALESCE(MAX(revision),0) FROM improved_listening_reviews WHERE job_id=?',(identity,)).fetchone()[0]
        if current!=revision: raise ValueError('Feedback changed; reload before saving')
        c.execute('INSERT INTO improved_listening_reviews VALUES (?,?,?,?,CURRENT_TIMESTAMP)',(identity,current+1,choice,notes))
    return {'review':listening_state(store,identity),'preference_learning_eligible':False}
