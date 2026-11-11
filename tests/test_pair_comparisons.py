"""Explicit comparison feedback, immutable media and contextual ranking inputs."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.app.web import create_app
from backend.app.pair_comparisons import enqueue_pair,preferences,comparison_audio,save_feedback
from backend.app.planning.preferences import features,FEATURES
from scripts.setup_timeline import sha256
import tests.test_workflow as workflow_fixture
import tests.test_preferences as preference_fixture


class PairComparisonTests(unittest.TestCase):
    setUp=workflow_fixture.WorkflowTests.setUp

    def complete(self):
        ids=[s['id'] for s in self.store.catalog()[:2]]
        job=enqueue_pair(self.store,ids);self.store.claim('pair-worker')
        alternatives=[];prefs=preferences(self.store)
        for slot,fade in (('a',2),('b',8)):
            path=self.root/'renders'/('test-'+slot+'.mp3');path.write_bytes(('synthetic-test-only-'+slot).encode())
            report={'output':str(path),'target_bpm':120,'overlap_seconds':16,'stems':True,
                'tracks':[{'content_hash':h,'source_bpm':120,'source_in':20,'source_out':100,'source_duration':180} for h in ('first','second')],
                'recipe':{'vocal_schedule':{'outgoing_fade_duration_seconds':fade,'incoming_fade_duration_seconds':fade}},
                'requested_candidate':{'evidence':{'energy_change_db':fade}}}
            path.with_suffix('.json').write_text(json.dumps(report))
            alternatives.append({'storage_name':path.name,'audio_hash':sha256(path),'preference_id':prefs.register(path.with_suffix('.json')),'candidate_id':'candidate-'+slot})
        source_hashes=[s['content_hash'] for s in self.store.job(job['id'],True)['payload']['sources']]
        self.store.finish(job['id'],'pair-worker','succeeded',{'alternatives':alternatives,'source_hashes':source_hashes})
        return job,alternatives

    def test_only_registered_pairs_and_frozen_existing_timelines(self):
        sources=self.store.catalog();ids=[s['id'] for s in sources[:2]]
        record={'timeline_id':'pinned','revision':3,'track_id':'track','effective':{'context':'fixture'}}
        with patch('backend.app.pair_comparisons.TimelineStore.for_content',return_value=record):
            job=enqueue_pair(self.store,ids)
        payload=self.store.job(job['id'],True)['payload']
        self.assertEqual(payload['timelines'][0]['revision'],3)
        self.assertNotIn('path',json.dumps(job))
        for pair in ([ids[0],ids[0]],['D:/secret.mp3',ids[0]],ids[:1]):
            with self.assertRaises(ValueError):enqueue_pair(self.store,pair)
        with self.assertRaisesRegex(ValueError,'six distinct'):enqueue_pair(self.store,ids,True)

    def test_feedback_a_b_tie_neither_and_conflicting_window(self):
        job,alts=self.complete();identity=job['id']
        first=save_feedback(self.store,identity,'a',0,'Cleaner bass')
        self.assertEqual(first['model']['comparisons'],1)
        self.assertFalse(first['model']['ready'])
        with self.assertRaisesRegex(ValueError,'reload'):save_feedback(self.store,identity,'b',0,'stale')
        tied=save_feedback(self.store,identity,'tie',1,'Same quality')
        self.assertEqual(tied['model']['comparisons'],0)
        neither=save_feedback(self.store,identity,'neither',2,'Both clash')
        self.assertEqual(neither['model']['comparisons'],0)
        reversed=save_feedback(self.store,identity,'b',3,'B is better')
        self.assertEqual(reversed['model']['comparisons'],1)
        self.assertEqual(preferences(self.store).comparisons()[0][2:],(alts[1]['preference_id'],alts[0]['preference_id']))
        with preferences(self.store).connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM feedback').fetchone()[0],4)

    def test_media_and_feedback_reject_changed_or_unpublished_audio(self):
        job,_=self.complete();identity=job['id']
        path=comparison_audio(self.store,identity,'a');path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'audio changed'):save_feedback(self.store,identity,'a',0,'')
        self.assertEqual(preferences(self.store).comparisons(),[])
        ids=[s['id'] for s in self.store.catalog()[:2]]
        pending=enqueue_pair(self.store,ids)
        with self.assertRaises(KeyError):comparison_audio(self.store,pending['id'],'a')

    def test_api_reload_byte_ranges_origin_and_stale_feedback(self):
        job,_=self.complete();client=TestClient(create_app(self.settings),base_url='http://127.0.0.1')
        state=client.get('/api/v1/comparisons').json();self.assertEqual(state['jobs'][0]['review']['revision'],0)
        url=f'/api/v1/comparisons/{job["id"]}'
        self.assertEqual(client.get(url+'/audio/a',headers={'Range':'bytes=0-3'}).status_code,206)
        self.assertEqual(client.get(url+'/audio/c').status_code,404)
        self.assertEqual(client.post(url+'/feedback',json={'choice':'a','expected_revision':0,'notes':'test-only'}).status_code,200)
        self.assertEqual(client.post(url+'/feedback',json={'choice':'b','expected_revision':0}).status_code,409)
        self.assertEqual(client.get('/api/v1/comparisons').json()['jobs'][0]['review']['choice'],'a')
        self.assertEqual(client.post('/api/v1/comparisons',headers={'Origin':'https://elsewhere.example'},json={}).status_code,403)

    def test_cancellation_before_publication_keeps_previews_unavailable(self):
        ids=[s['id'] for s in self.store.catalog()[:2]]
        job=enqueue_pair(self.store,ids);self.store.claim('worker');self.store.cancel(job['id'])
        self.store.finish(job['id'],'worker','succeeded',{'alternatives':[]})
        self.assertEqual(self.store.job(job['id'])['status'],'cancelled')
        with self.assertRaises(KeyError):comparison_audio(self.store,job['id'],'a')

    def test_neither_skips_only_explicitly_rejected_candidates_in_that_pair(self):
        job,_=self.complete();save_feedback(self.store,job['id'],'neither',0,'both poor')
        ids=[s['id'] for s in self.store.catalog()[:2]]
        following=enqueue_pair(self.store,ids)
        self.assertEqual(self.store.job(following['id'],True)['payload']['rejected_candidate_ids'],['candidate-a','candidate-b'])
        reverse=enqueue_pair(self.store,list(reversed(ids)))
        self.assertEqual(self.store.job(reverse['id'],True)['payload']['rejected_candidate_ids'],[])


class ContextPreferenceTests(unittest.TestCase):
    setUp=preference_fixture.PreferenceTests.setUp
    candidate=preference_fixture.PreferenceTests.candidate

    def test_legacy_vectors_remain_trainable_and_neutral_clears_ratings(self):
        a,b=self.candidate('legacy',2),self.candidate('legacy',8)
        with self.store.connect() as c:
            for row in self.store.candidates():c.execute('UPDATE candidates SET features_json=? WHERE id=?',(json.dumps(json.loads(row['features_json'])[:12]),row['id']))
        self.store.feedback('rate',a,value=1);self.store.feedback('rate',b,value=5)
        self.assertEqual(self.store.train()['comparisons'],1)
        self.store.feedback('tie',a,b)
        self.assertEqual(self.store.train()['comparisons'],0)
        model=self.store.feedback('prefer',b,a)
        self.assertEqual(len(model['weights']),len(FEATURES))

    def test_context_and_unknown_masks_are_distinct(self):
        identity=self.candidate('context',2)
        report=json.loads(self.store.candidates()[0]['report_json'])
        unknown=features(report)
        report['requested_candidate']={'evidence':{'energy_change_db':0}}
        measured=features(report)
        index=FEATURES.index('energy_change_db')
        self.assertEqual(unknown[index],measured[index])
        self.assertNotEqual(unknown[index+1],measured[index+1])
