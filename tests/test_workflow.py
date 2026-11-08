"""Persistent owner-operated learning jobs: pinning, fencing, recovery and API."""
import json
from pathlib import Path
import tempfile,time
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.audio.probe import AudioInfo
from backend.app.reference_review import TIMES
from backend.app.workflow import Workflow
from backend.app.web import create_app
from scripts.setup_timeline import sha256


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.settings=Settings(data_root=self.root,min_free_bytes=0)
        self.store=Workflow(self.settings)
        for name in ('recording.mp4','a.mp3','b.mp3','c.mp3','d.mp3'):(self.root/name).write_bytes(name.encode())
        manifest=self.root/'manifest.json';manifest.write_text(json.dumps({'title':'Reference','recording':'recording.mp4',
            'tracks':[{'title':name,'sources':[name+'.mp3']} for name in ('a','b','c','d')]}),encoding='utf-8')
        with patch('backend.app.references.probe',return_value=AudioInfo(180,44100,2,'test')):
            imported=self.store.reviews.references.import_manifest(manifest)
        self.imported=imported
        alignment=self.store.reviews.references._save_alignment(imported['id'],{'test':True})
        tracks=[{'position':i,'title':r['title'],'sources':[{'name':Path(s['path']).name,'content_hash':s['content_hash'],
                 'duration_seconds':s['duration_seconds']} for s in r['sources']]} for i,r in enumerate(imported['import']['tracks'])]
        transitions=[]
        for i in range(3):
            draft=dict.fromkeys(TIMES)
            draft.update(outgoing_hash=tracks[i]['sources'][0]['content_hash'],incoming_hash=tracks[i+1]['sources'][0]['content_hash'],
                         mix_start=20+i*40,mix_end=28+i*40,outgoing_source_in=50,outgoing_source_out=58,
                         incoming_source_in=30,incoming_source_out=38,recipe='eq_8' if i==0 else None)
            transitions.append({'position':i,'draft':draft,'title':'handoff','reason':'test','focus_seconds':24+i*40})
        snapshot={'reference_id':imported['id'],'alignment_id':alignment['id'],'recording_hash':imported['import']['recording']['content_hash'],
                  'duration_seconds':180,'title':'Reference','tracks':tracks,'transitions':transitions}
        with self.store.db.connection() as c:
            c.execute('INSERT INTO reference_transition_drafts(id,reference_id,alignment_id,snapshot_json) VALUES (?,?,?,?)',
                      ('draft',imported['id'],alignment['id'],json.dumps(snapshot)))
        self.reviews=[]
        for i,t in enumerate(transitions):
            review={**t['draft'],'reviewed':True,'learn':True}
            self.reviews.append(review);self.store.reviews.save('draft',i,0,review)

    def test_train_pins_revisions_and_deduplicates_active_request(self):
        job=self.store.enqueue_train('draft');again=self.store.enqueue_train('draft')
        self.assertEqual(job['id'],again['id'])
        frozen=self.store.job(job['id'],True)['payload']['snapshot']
        self.assertEqual(len(frozen['examples']),3)
        self.assertNotIn('path',json.dumps(job))
        self.store.reviews.save('draft',1,1,{**self.reviews[1],'learn':False})
        fresh=self.store.enqueue_train('draft')
        self.assertNotEqual(job['id'],fresh['id'])
        self.assertEqual(len(self.store.job(job['id'],True)['payload']['snapshot']['examples']),3)
        self.assertEqual([r['position'] for r in self.store.job(fresh['id'],True)['payload']['snapshot']['examples']],[0,2])
        self.assertNotEqual(frozen['review_fingerprint'],self.store.readiness('draft')['review_fingerprint'])

    def test_pending_and_excluded_reviews_never_train(self):
        self.store.reviews.save('draft',0,1,{**self.reviews[0],'reviewed':False})
        self.store.reviews.save('draft',1,1,{**self.reviews[1],'learn':False})
        readiness=self.store.readiness('draft')
        self.assertEqual(readiness['examples'],1);self.assertFalse(readiness['can_train'])
        with self.assertRaisesRegex(ValueError,'two completed'):self.store.enqueue_train('draft')

    def test_one_worker_lease_recovery_cancel_retry_and_stale_finish(self):
        job=self.store.enqueue_train('draft');now=time.time()
        claimed=self.store.claim('worker-a',now)
        self.assertEqual(claimed['id'],job['id']);self.assertTrue(self.store.live(job['id'],'worker-a'))
        self.assertIsNone(self.store.claim('worker-b',now+1))
        self.assertFalse(self.store.finish(job['id'],'worker-b','failed',error='stale'))
        self.store.claim('worker-b',now+31)
        self.assertEqual(self.store.job(job['id'])['status'],'interrupted')
        retry=self.store.retry(job['id']);self.assertNotEqual(retry['id'],job['id'])
        self.assertEqual(self.store.cancel(retry['id'])['status'],'cancelled')

    def test_registered_song_ids_preserve_order_and_repeated_occurrences(self):
        songs=self.store.catalog();ids=[songs[2]['id'],songs[0]['id'],songs[2]['id']]
        job=self.store.enqueue_test(None,ids,60,True)
        sources=self.store.job(job['id'],True)['payload']['sources']
        self.assertEqual([s['id'] for s in sources],ids)
        with self.assertRaises(ValueError):self.store.enqueue_test(None,['D:/secret.mp3',ids[0]],60,True)
        with self.assertRaises(ValueError):self.store.enqueue_test(None,ids,float('nan'),True)

    def test_model_registration_integrity_and_changed_review_guard(self):
        job=self.store.enqueue_train('draft');self.store.claim('worker')
        name='decision-model-'+job['id'];directory=self.root/'models'/name;directory.mkdir()
        (directory/'manifest.json').write_text('{}')
        model={'id':job['id'],'storage_name':name,'manifest_hash':sha256(directory/'manifest.json'),
               'review_fingerprint':self.store.readiness('draft')['review_fingerprint'],'report':{'status':'experimental'},'active':False}
        self.assertTrue(self.store.finish(job['id'],'worker','succeeded',{'model':model}))
        self.assertEqual(len(self.store.models()),1)
        ids=[r['id'] for r in self.store.catalog()[:2]]
        self.store.enqueue_test(job['id'],ids,60)
        self.store.reviews.save('draft',0,1,{**self.reviews[0],'learn':False})
        with self.assertRaisesRegex(ValueError,'Reviews changed'):self.store.enqueue_test(job['id'],ids,60)
        (directory/'manifest.json').write_text('changed')
        with self.assertRaisesRegex(ValueError,'manifest changed'):self.store.model(job['id'])

    def test_api_enqueues_without_commands_and_origin_guard(self):
        client=TestClient(create_app(self.settings),base_url='http://127.0.0.1')
        state=client.get('/api/v1/learning/state').json()
        self.assertEqual(state['readiness']['examples'],3)
        self.assertEqual(client.post('/api/v1/learning/train',json={'draft_id':'draft'},headers={'Origin':'https://foreign.example'}).status_code,403)
        response=client.post('/api/v1/learning/train',json={'draft_id':'draft'})
        self.assertEqual(response.status_code,200);identity=response.json()['id']
        self.assertEqual(client.post('/api/v1/learning/jobs/'+identity+'/cancel').json()['status'],'cancelled')
        self.assertEqual(client.post('/api/v1/learning/jobs/'+identity+'/retry').status_code,200)
        self.assertEqual(client.post('/api/v1/learning/test-mixes',json={'track_ids':['unknown'],'baseline':True}).status_code,422)
        self.assertEqual(client.get('/api/v1/learning/jobs/unknown/log').status_code,404)

    def test_browser_song_import_is_bounded_registered_and_cleans_failed_files(self):
        client=TestClient(create_app(self.settings),base_url='http://127.0.0.1')
        with patch('backend.app.web.probe',return_value=AudioInfo(180,44100,2,'mp3')):
            response=client.post('/api/v1/learning/library',content=b'audio bytes',headers={'X-File-Name':'new%20song.mp3'})
        self.assertEqual(response.status_code,200)
        imported=next(s for s in self.store.catalog(True) if s['id']==response.json()['id'])
        self.assertEqual(imported['name'],'new song.mp3')
        self.assertTrue(Path(imported['path']).is_relative_to(self.root/'uploads'))
        self.assertEqual(Path(imported['path']).read_bytes(),b'audio bytes')
        before=len(list((self.root/'uploads').iterdir()))
        with patch('backend.app.web.probe',side_effect=ValueError('No audio stream')):
            failure=client.post('/api/v1/learning/library',content=b'bad',headers={'X-File-Name':'bad.mp3'})
        self.assertEqual(failure.status_code,422)
        self.assertEqual(len(list((self.root/'uploads').iterdir())),before)
        self.assertEqual(client.post('/api/v1/learning/library',content=b'bad',headers={'X-File-Name':'document.pdf'}).status_code,422)


if __name__=='__main__':unittest.main()
