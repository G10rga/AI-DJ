"""Persistent, owner-operated training/test jobs and immutable model records."""
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4
from .config import Settings
from .reference_review import ReferenceReviewStore
from .timelines import canonical
from scripts.setup_timeline import sha256


class Workflow:
    def __init__(self, settings: Settings):
        self.settings=settings
        self.reviews=ReferenceReviewStore(settings)
        self.db=self.reviews.database
        self.storage=self.reviews.references.storage

    def catalog(self, internal=False):
        with self.db.connection() as c:
            imports=c.execute('SELECT snapshot_json FROM reference_imports ORDER BY rowid').fetchall()
            tracks=c.execute('SELECT content_hash,original_name,metadata_json FROM tracks').fetchall()
        sources={}
        def add(source):
            identity=hashlib.sha256((source['content_hash']+':'+str(Path(source['path']).resolve())).encode()).hexdigest()[:24]
            sources[identity]={'id':identity,'name':source.get('name',Path(source['path']).name),**source}
        for row in imports:
            for track in json.loads(row[0])['tracks']:
                for source in track['sources']:add(source)
        for row in tracks:
            metadata=json.loads(row['metadata_json'])
            if metadata.get('external_path'):
                source={'path':metadata['external_path'],'content_hash':row['content_hash'],'name':row['original_name']}
                identity=hashlib.sha256((source['content_hash']+':'+str(Path(source['path']).resolve())).encode()).hexdigest()[:24]
                if identity not in sources:add(source)
        result=sorted(sources.values(),key=lambda r:(r['name'].casefold(),r['id']))
        return result if internal else [{k:v for k,v in r.items() if k!='path'} for r in result]

    def readiness(self, draft_id):
        exported=self.training_export(draft_id)
        batch=self.reviews.batch(draft_id)
        return {'draft_id':draft_id,'title':batch['title'],'counts':batch['counts'],
                'examples':len(exported['examples']),'style_examples':exported['style_examples'],
                'automatic_style_examples':sum('automatic_style' in e for e in exported['examples']),
                'can_train':len(exported['examples'])>=2,
                'review_fingerprint':hashlib.sha256(canonical(exported).encode()).hexdigest()}

    def enqueue_train(self,draft_id):
        exported=self.training_export(draft_id)
        if len(exported['examples'])<2:
            raise ValueError('Include at least two completed listening reviews before training')
        fingerprint=hashlib.sha256(canonical(exported).encode()).hexdigest()
        imported=self.reviews.references.get(exported['reference_id'])['import']
        for row in exported['examples']:
            row['sources']=[]
            for position,key in zip(row['source_positions'],('outgoing_hash','incoming_hash')):
                row['sources'].append(next(s for s in imported['tracks'][position]['sources']
                                           if s['content_hash']==row['decision'][key]))
        exported['review_fingerprint']=fingerprint
        return self.enqueue('train',{'draft_id':draft_id,'snapshot':exported})

    def analysis_state(self, draft_id):
        from .transition_analysis import VERSION
        batch=self.reviews.batch(draft_id)
        current={t['position']:t for t in batch['transitions']}
        with self.db.connection() as c:
            jobs=c.execute("SELECT id,status,stage,progress,error,result_json,payload_json FROM workflow_jobs WHERE kind='transition_analysis' ORDER BY rowid").fetchall()
        analyses={}; relevant=[]
        for job in jobs:
            payload=json.loads(job['payload_json'])
            if payload['draft_id']!=draft_id:continue
            job_result=json.loads(job['result_json']) if job['result_json'] else {}
            relevant.append({**{k:job[k] for k in ('id','status','stage','progress','error')},
                'summary':job_result.get('summary'),
                'outdated':job_result.get('algorithm_version') not in (None,VERSION)})
            if job['status']!='succeeded' or not job['result_json']:continue
            for result in json.loads(job['result_json']).get('analyses',[]):
                if result['algorithm_version']!=VERSION:continue
                row=current.get(result['position'])
                if not row:continue
                item={**result,'job_id':job['id']}
                item['stale']=(row['revision']!=result['review_revision'] or
                    hashlib.sha256(canonical(row['review']).encode()).hexdigest()!=result['decision_hash'])
                if item['stale'] and str(result['position']) in analyses and not analyses[str(result['position'])]['stale']:
                    continue
                analyses[str(result['position'])]=item
        return {'analyses':analyses,'jobs':list(reversed(relevant))[:10]}

    def training_export(self, draft_id):
        exported=self.reviews.export(draft_id)
        analyses=self.analysis_state(draft_id)['analyses']
        for example in exported['examples']:
            estimate=analyses.get(str(example['position']))
            if (example['decision'].get('recipe') is None and estimate and not estimate['stale']
                    and estimate.get('training_eligible') and estimate['confidence']=='high'):
                example['automatic_style']={k:estimate[k] for k in
                    ('recipe','confidence','algorithm_version','job_id','review_revision','source_hashes',
                     'recording_hash','decision_hash','label_origin','human_confirmed')}
        exported['style_examples']=sum(e['decision'].get('recipe') is not None or 'automatic_style' in e for e in exported['examples'])
        return exported

    def enqueue_analysis(self, draft_id, position=None, expected_revision=None):
        from .transition_analysis import VERSION
        batch=self.reviews.batch(draft_id)
        if position is not None and (type(position) is not int or not 0<=position<len(batch['transitions'])):
            raise ValueError('Choose a valid transition')
        if position is not None and type(expected_revision) is not int:
            raise ValueError('Specify the saved review revision')
        imported=self.reviews.references.get(batch['reference_id'])['import']
        examples=[]
        for row in batch['transitions']:
            if position is not None and row['position']!=position:continue
            if position is not None and row['revision']!=expected_revision:
                raise ValueError('This review changed; reload saved reviews before analyzing')
            review=row['review']
            complete=review and all(review.get(k) is not None for k in
                ('mix_start','mix_end','outgoing_source_in','outgoing_source_out','incoming_source_in','incoming_source_out','outgoing_hash','incoming_hash'))
            if not complete:
                if position is not None:raise ValueError('Save entry, exit and both original-song cue intervals before analyzing')
                continue
            if position is None and not (review.get('reviewed') and review.get('learn')):continue
            sources=[next(s for s in imported['tracks'][row['position']+i]['sources'] if s['content_hash']==review[key])
                     for i,key in enumerate(('outgoing_hash','incoming_hash'))]
            examples.append({'position':row['position'],'review_revision':row['revision'],'decision':review,'sources':sources})
        if not examples:raise ValueError('No completed included transitions are ready to analyze')
        return self.enqueue('transition_analysis',{'draft_id':draft_id,'snapshot':{
            'draft_id':draft_id,'reference_id':batch['reference_id'],'recording_hash':batch['recording_hash'],
            'algorithm_version':VERSION,'examples':examples}})

    def enqueue_test(self, model_id, track_ids, seconds=72, baseline=False, pipeline=None):
        from .transition_review import pipeline as select_pipeline
        pipeline=select_pipeline(self,pipeline)
        if pipeline=='improved-transitions-1' and not baseline:
            raise ValueError('Use Generate improved mix; existing cue models do not support this pipeline yet')
        if type(baseline) is not bool or type(seconds) not in (float,int) or not 30<=seconds<=240:
            raise ValueError('Choose a test length from 30 to 240 seconds per song')
        if not isinstance(track_ids,list) or not 2<=len(track_ids)<=50 or any(not isinstance(t,str) for t in track_ids):
            raise ValueError('Choose 2–50 registered songs for the test mix')
        catalog={r['id']:r for r in self.catalog(internal=True)}
        if any(t not in catalog for t in track_ids):raise ValueError('Selected song is no longer in the library')
        if not baseline:
            _,manifest=self.model(model_id)
            model_record=next(m for m in self.models() if m['id']==model_id)
            if self.readiness(model_record['draft_id'])['review_fingerprint']!=manifest['review_fingerprint']:
                raise ValueError('Reviews changed since this model was trained. Train a new version before generating a test mix.')
        return self.enqueue('test_mix',{'model_id':None if baseline else model_id,'baseline':baseline,
            'sources':[catalog[t] for t in track_ids],'seconds':float(seconds),'pipeline':pipeline})

    def enqueue(self,kind,payload,*,precondition=None):
        key=hashlib.sha256((kind+canonical(payload)).encode()).hexdigest()
        identity=uuid4().hex
        with self.db.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            if precondition is not None: precondition(c)
            existing=c.execute("SELECT id FROM workflow_jobs WHERE request_key=? AND status IN ('queued','running')",(key,)).fetchone()
            if existing:return self.job(existing[0])
            c.execute('INSERT INTO workflow_jobs(id,kind,request_key,status,payload_json) VALUES (?,?,?,?,?)',
                      (identity,kind,key,'queued',canonical(payload)))
        return self.job(identity)

    def job(self,identity,internal=False):
        with self.db.connection() as c:
            row=c.execute('SELECT * FROM workflow_jobs WHERE id=?',(identity,)).fetchone()
        if row is None:raise KeyError(identity)
        result=dict(row);payload=json.loads(result.pop('payload_json'))
        raw_result=result.pop('result_json')
        result['result']=json.loads(raw_result) if raw_result else None
        result['payload']=payload if internal else {'draft_id':payload.get('draft_id'),'model_id':payload.get('model_id'),
            'baseline':payload.get('baseline',False),'song_names':[s['name'] for s in payload.get('sources',[])],
            'pipeline':payload.get('pipeline','legacy-v1'),'parent_job_id':payload.get('parent_job_id'),
            'review_revision':payload.get('review_revision'),'join_index':payload.get('join_index'),
            'examples':len(payload.get('snapshot',{}).get('examples',[]))}
        if not internal:
            result.pop('owner');result.pop('request_key');result.pop('heartbeat')
        return result

    def jobs(self):
        with self.db.connection() as c:
            ids=[r[0] for r in c.execute("SELECT id FROM workflow_jobs WHERE kind!='playlist' ORDER BY rowid DESC LIMIT 30")]
        return [self.job(i) for i in ids]

    def models(self):
        with self.db.connection() as c:
            rows=c.execute('SELECT * FROM decision_models ORDER BY rowid DESC').fetchall()
        return [{'id':r['id'],'job_id':r['job_id'],'draft_id':r['draft_id'],
                 'created_at':r['created_at'],**json.loads(r['manifest_json'])} for r in rows]

    def model(self,identity):
        with self.db.connection() as c:
            row=c.execute('SELECT * FROM decision_models WHERE id=?',(identity,)).fetchone()
        if row is None:raise KeyError(identity)
        name=row['storage_name'];root=(self.storage.root/'models').resolve()
        path=(root/name).resolve()
        if Path(name).name!=name or not path.is_relative_to(root) or not path.is_dir():
            raise ValueError('Model files are unavailable; train a new version')
        manifest=json.loads(row['manifest_json'])
        if sha256(path/'manifest.json')!=manifest['manifest_hash']:
            raise ValueError('Model manifest changed; train a new version')
        return path,manifest

    def cancel(self,identity):
        with self.db.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT status FROM workflow_jobs WHERE id=?',(identity,)).fetchone()
            if row is None:raise KeyError(identity)
            if row[0] in ('queued','needs_review'):
                c.execute("UPDATE workflow_jobs SET status='cancelled',stage='Cancelled',finished_at=CURRENT_TIMESTAMP WHERE id=?",(identity,))
            elif row[0]=='running':c.execute('UPDATE workflow_jobs SET cancel_requested=1 WHERE id=?',(identity,))
        return self.job(identity)

    def retry(self,identity):
        job=self.job(identity,internal=True)
        if job['status'] not in ('failed','interrupted','cancelled'):raise ValueError('Only failed, interrupted or cancelled jobs can be retried')
        if job['payload'].get('parent_job_id'):
            with self.db.connection() as c:
                revision=c.execute('SELECT MAX(revision) FROM transition_reviews WHERE job_id=?',(job['payload']['parent_job_id'],)).fetchone()[0]
            if revision!=job['payload']['review_revision']:raise ValueError('Review changed; reload the original review and preview its current revision')
        return self.enqueue(job['kind'],job['payload'])

    def claim(self,owner,now=None):
        now=time.time() if now is None else now
        interrupted=[]
        with self.db.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            lease=c.execute("SELECT owner,expires FROM workflow_leases WHERE name='heavy-worker'").fetchone()
            if lease and lease['owner']!=owner and lease['expires']>now:return None
            stale=c.execute("SELECT id FROM workflow_jobs WHERE status='running' AND (heartbeat IS NULL OR heartbeat<?)",(now-30,)).fetchall()
            interrupted=[r[0] for r in stale]
            c.execute("UPDATE workflow_jobs SET status='interrupted',stage='Interrupted',error='The server stopped during this job. Retry to run it again.',finished_at=CURRENT_TIMESTAMP WHERE status='running' AND (heartbeat IS NULL OR heartbeat<?)",(now-30,))
            c.execute("INSERT OR REPLACE INTO workflow_leases VALUES ('heavy-worker',?,?)",(owner,now+30))
            row=c.execute("SELECT id FROM workflow_jobs WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
            if row:
                c.execute("UPDATE workflow_jobs SET status='running',owner=?,heartbeat=?,stage='Starting',progress=.01 WHERE id=? AND status='queued'",(owner,now,row[0]))
        for identity in interrupted:self.fail_render_attempts(identity,'Workflow interrupted')
        return self.job(row[0],internal=True) if row else None

    def heartbeat(self,identity,owner):
        now=time.time()
        with self.db.connection() as c:
            lease=c.execute("UPDATE workflow_leases SET expires=? WHERE name='heavy-worker' AND owner=?",(now+30,owner))
            if lease.rowcount!=1:raise RuntimeError('Worker lease lost')
            c.execute("UPDATE workflow_jobs SET heartbeat=? WHERE id=? AND owner=? AND status='running'",(now,identity,owner))

    def progress(self,identity,owner,stage,amount):
        with self.db.connection() as c:
            c.execute("UPDATE workflow_jobs SET stage=?,progress=? WHERE id=? AND owner=? AND status='running'",
                      (str(stage)[:200],max(0,min(.99,float(amount))),identity,owner))

    def live(self,identity,owner):
        with self.db.connection() as c:
            row=c.execute("SELECT j.status,j.cancel_requested,l.owner,l.expires FROM workflow_jobs j LEFT JOIN workflow_leases l ON l.name='heavy-worker' WHERE j.id=?",(identity,)).fetchone()
        return bool(row and row['status']=='running' and not row['cancel_requested'] and row['owner']==owner and row['expires']>time.time())

    def finish(self,identity,owner,status,result=None,error=None):
        with self.db.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM workflow_jobs WHERE id=?',(identity,)).fetchone()
            if row is None or row['status']!='running' or row['owner']!=owner:return False
            lease=c.execute("SELECT owner,expires FROM workflow_leases WHERE name='heavy-worker'").fetchone()
            if not lease or lease['owner']!=owner or lease['expires']<time.time():return False
            if status=='succeeded' and result and result.get('status')=='needs_review': status='needs_review'
            if status in ('succeeded','needs_review') and row['cancel_requested']:
                status='cancelled';result=None;error='Cancelled by owner'
            payload=json.loads(row['payload_json'])
            if payload.get('pipeline')=='playlist-1':
                from .playlist.store import publish
                project = c.execute('SELECT revision FROM playlist_projects WHERE id=?',(payload['project_id'],)).fetchone()
                if project is None or project[0]!=payload['project_revision']:
                    status='interrupted';result=None;error='Project changed; reload and mix the current revision'
                elif status in ('succeeded','needs_review') and (not result or not publish(c,row,payload,result)):
                    status='failed';result=None;error='The playlist job returned no publishable plan'
            if status in ('succeeded','needs_review') and payload.get('parent_job_id'):
                parent=c.execute('SELECT status FROM workflow_jobs WHERE id=?',(payload['parent_job_id'],)).fetchone()
                if parent is None or parent['status']=='cancelled':
                    status='cancelled';result=None;error='The parent review was cancelled'
                current=c.execute('SELECT MAX(revision) FROM transition_reviews WHERE job_id=?',(payload['parent_job_id'],)).fetchone()[0]
                if current!=payload['review_revision']:
                    status='interrupted';result=None;error='Review changed during this job. Reload and preview or resume the current revision.'
                if status in ('succeeded','needs_review'):
                    for record in payload.get('foundation_records',[]):
                        actual=c.execute('SELECT COALESCE(MAX(revision),0) FROM timeline_corrections WHERE timeline_id=?',(record['timeline_id'],)).fetchone()[0]
                        if actual!=record['revision']:
                            status='interrupted';result=None;error='Timing corrections changed during this job. Reload and preview again.';break
            if status=='succeeded' and payload.get('pipeline')=='improved-transitions-1':
                from .transition_review import register_artifacts
                if not result or result.get('status')!='validated': raise ValueError('Improved audio must pass validation before publication')
                register_artifacts(self,c,row,result)
            if result and payload.get('pipeline')=='improved-transitions-1':
                result['source_hashes']=[s['content_hash'] for s in payload['sources']]
                if result.get('plan'):
                    result['applied_transitions']=[{'bars':j['candidate']['bars'],'seconds':j['candidate']['overlap_seconds']} for j in result['plan']['joins']]
            if status=='succeeded' and row['kind']=='train':
                model=result['model'];path=(self.storage.root/'models'/model['storage_name']).resolve()
                if not path.is_relative_to((self.storage.root/'models').resolve()) or sha256(path/'manifest.json')!=model['manifest_hash']:
                    raise ValueError('Completed model artifact is invalid')
                c.execute('INSERT INTO decision_models VALUES (?,?,?,?,?,CURRENT_TIMESTAMP)',
                          (model['id'],identity,json.loads(row['payload_json'])['draft_id'],model['storage_name'],canonical(model)))
            c.execute('UPDATE workflow_jobs SET status=?,stage=?,progress=?,result_json=?,error=?,finished_at=CURRENT_TIMESTAMP WHERE id=?',
                      (status,'Completed' if status=='succeeded' else 'Needs review' if status=='needs_review' else status.capitalize(),1 if status=='succeeded' else row['progress'],
                       canonical(result) if result else None,str(error)[:2000] if error else None,identity))
            if status=='needs_review':
                c.execute("DELETE FROM workflow_leases WHERE name='heavy-worker' AND owner=?",(owner,))
        if status!='succeeded':self.fail_render_attempts(identity,error or status)
        return True

    def fail_render_attempts(self,identity,error):
        with self.db.connection() as c:
            rows=c.execute("SELECT id,snapshot_json FROM render_attempts WHERE status='running'").fetchall()
            for row in rows:
                planning=json.loads(row['snapshot_json']).get('provenance',{}).get('planning',{})
                if planning.get('workflow_job_id')==identity:
                    c.execute("UPDATE render_attempts SET status='failed',error=? WHERE id=? AND status='running'",(str(error),row['id']))
