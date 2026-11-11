"""Attribution truth, conservative labels and immutable automatic supervision."""
from copy import deepcopy
import hashlib
import json
import os
import shutil
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from fastapi.testclient import TestClient
from backend.app.transition_analysis import attribute, attribute_interval, analyze_snapshot, map_recipe, VERSION
from backend.app.timelines import canonical
from backend.app.planning.decision_learning import dataset_from_snapshot
from backend.app.db import Database, SCHEMA
from backend.app.web import create_app
import tests.test_workflow as fixtures


class SpectralAttributionTests(unittest.TestCase):
    def test_context_observes_outgoing_exit_beyond_marked_overlap(self):
        _,a,b,decision=self.mixture()
        original=deepcopy(decision)
        times=np.arange(len(a))*.25+.128
        incoming=np.clip((times-20)/32,0,1)
        mix=np.log(np.exp(a)*(times<52)[:,None]+np.exp(b)*incoming[:,None]**2+1e-20)
        inside=attribute_interval(mix,a,b,decision)
        result=attribute(mix,a,b,decision)
        self.assertEqual(inside['technique'],'unknown')
        self.assertNotEqual(result['technique'],'unknown',result)
        self.assertEqual(decision,original)
        self.assertEqual(result['quality']['analysis_interval_seconds'],[18.,54.])
        self.assertIn('32.0 seconds',result['description'])
        self.assertTrue(any('Outgoing bass fades down' in text for text in result['observations']))

    def test_old_running_server_cannot_silently_request_different_algorithm(self):
        with self.assertRaisesRegex(ValueError,'analyzer changed'):
            analyze_snapshot({'algorithm_version':'obsolete'},None)

    def test_real_decoding_and_spectral_cache_preserve_known_fade(self):
        from scipy.io import wavfile
        from backend.app.audio.reference import spectral_features
        from backend.app.config import Settings
        ffmpeg=os.environ.get('AI_DJ_FFMPEG','ffmpeg')
        if not shutil.which(ffmpeg):self.skipTest('FFmpeg unavailable')
        rate=8000;t=np.arange(rate*40)/rate
        a=sum(np.sin(2*np.pi*f*t) for f in (100,500,1700))/6
        b=sum(np.sin(2*np.pi*f*t) for f in (180,1000,2800))/6
        fraction=np.clip((t-4)/32,0,1)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);features=[]
            for name,audio in (('mix',a*(1-fraction)+b*fraction),('a',a),('b',b)):
                path=root/(name+'.wav');wavfile.write(path,rate,audio.astype(np.float32))
                features.append(spectral_features(path,40,Settings(ffmpeg=ffmpeg),root))
            decision={'mix_start':4.,'mix_end':36.,'outgoing_source_in':4.,'outgoing_source_out':36.,
                      'incoming_source_in':4.,'incoming_source_out':36.}
            result=attribute(*features,decision)
            self.assertEqual(result['technique'],'gradual_blend',result)
            self.assertEqual(result['confidence'],'high')

    def mixture(self, eq=False, mismatch=False, identical=False):
        rng=np.random.default_rng(15)
        a=np.exp(rng.normal(0, .9, (400,32)))
        a*=np.tile([.3,2.],16)
        b=a.copy() if identical else np.exp(rng.normal(0, .9, (400,32)))*np.tile([2.,.3],16)
        times=np.arange(400)*.25+.128
        fraction=np.clip((times-20)/32,0,1)
        g=np.broadcast_to(fraction[:,None],a.shape).copy()
        if eq:g[:,:11]=np.clip((fraction[:,None]-.65)/.15,0,1)
        mix=a*(1-g)**2+b*g**2
        if mismatch:mix=np.exp(rng.normal(0,2.,mix.shape))
        decision={'mix_start':20.,'mix_end':52.,'outgoing_source_in':20.,'outgoing_source_out':52.,
                  'incoming_source_in':20.,'incoming_source_out':52.}
        return np.log(mix+1e-20),np.log(a),np.log(b),decision

    def test_recovers_full_band_and_frequency_staggered_handoffs(self):
        for eq,expected in ((False,'gradual_blend'),(True,'eq_handoff')):
            with self.subTest(eq=eq):
                result=attribute(*self.mixture(eq))
                self.assertEqual(result['technique'],expected,result)
                self.assertEqual(result['confidence'],'high')
                self.assertLess(result['quality']['relative_spectral_error'],.18)
                self.assertIsNone(result['recipe'])
                result=map_recipe(result,32,8 if eq else 16)
                self.assertTrue(result['training_eligible'])
                self.assertEqual(result['recipe'],'eq_8' if eq else 'controlled_16')

    def test_mismatch_and_indistinguishable_sources_abstain(self):
        for option in ('mismatch','identical'):
            with self.subTest(option=option):
                result=attribute(*self.mixture(**{option:True}))
                self.assertEqual(result['technique'],'unknown')
                self.assertIsNone(map_recipe(result,32,16)['recipe'])

    def test_duration_alone_never_supplies_style_or_cut(self):
        arrays=list(self.mixture());arrays[-1]['mix_end']=arrays[-1]['mix_start']
        result=attribute(*arrays)
        self.assertEqual(result['technique'],'unknown')
        self.assertIsNone(map_recipe(result,0,0)['recipe'])
        result=attribute(*self.mixture())
        self.assertIsNone(map_recipe(result,32,None)['recipe'])
        self.assertIsNone(map_recipe(result,32,8)['recipe'])

    def test_cut_requires_an_actual_abrupt_change_either_side(self):
        _,a,b,decision=self.mixture()
        times=np.arange(len(a))*.25+.128
        mix=np.where((times<36)[:,None],a,b)
        decision={key:36. for key in decision}
        result=attribute(mix,a,b,decision)
        self.assertEqual(result['technique'],'cut',result)
        self.assertEqual(map_recipe(result,0,None)['recipe'],'cut')


class AnalysisWorkflowTests(unittest.TestCase):
    setUp=fixtures.WorkflowTests.setUp

    def publish(self, position=1):
        job=self.store.enqueue_analysis('draft',position,1)
        self.store.claim('analysis-worker')
        review=self.store.reviews.batch('draft')['transitions'][position]['review']
        result={'position':position,'review_revision':1,'algorithm_version':VERSION,
                'source_hashes':[review['outgoing_hash'],review['incoming_hash']],
                'recording_hash':self.imported['import']['recording']['content_hash'],
                'decision_hash':hashlib.sha256(canonical(review).encode()).hexdigest(),
                'recipe':'controlled_16','confidence':'high','training_eligible':True,
                'label_origin':'automatic_spectral_estimate','human_confirmed':False}
        self.assertTrue(self.store.finish(job['id'],'analysis-worker','succeeded',{'analyses':[result]}))
        return job,result

    def test_separate_labels_pin_and_invalidate_without_mutating_reviews(self):
        original=self.store.reviews.export('draft')
        job,result=self.publish()
        enriched=self.store.training_export('draft')
        self.assertEqual(self.store.reviews.export('draft'),original)
        self.assertEqual(enriched['examples'][1]['automatic_style']['job_id'],job['id'])
        self.assertIsNone(enriched['examples'][1]['decision']['recipe'])
        fingerprint=self.store.readiness('draft')['review_fingerprint']
        training=self.store.enqueue_train('draft')
        frozen=self.store.job(training['id'],True)['payload']['snapshot']
        changed={**self.reviews[1],'mix_start':61.}
        self.store.reviews.save('draft',1,1,changed)
        self.assertTrue(self.store.analysis_state('draft')['analyses']['1']['stale'])
        self.assertNotIn('automatic_style',self.store.training_export('draft')['examples'][1])
        self.assertNotEqual(fingerprint,self.store.readiness('draft')['review_fingerprint'])
        self.assertIn('automatic_style',frozen['examples'][1])

    def test_cancel_before_finish_does_not_publish_labels(self):
        job=self.store.enqueue_analysis('draft',1,1);self.store.claim('worker')
        self.store.cancel(job['id'])
        self.store.finish(job['id'],'worker','succeeded',{'analyses':[{'invalid':'must not publish'}]})
        self.assertEqual(self.store.job(job['id'])['status'],'cancelled')
        self.assertEqual(self.store.analysis_state('draft')['analyses'],{})

    def test_pending_batch_exclusion_and_revision_guard(self):
        self.store.reviews.save('draft',1,1,{**self.reviews[1],'reviewed':False})
        self.store.reviews.save('draft',2,1,{**self.reviews[2],'learn':False})
        job=self.store.enqueue_analysis('draft')
        snapshot=self.store.job(job['id'],True)['payload']['snapshot']
        self.assertEqual([e['position'] for e in snapshot['examples']],[0])
        with self.assertRaisesRegex(ValueError,'reload'):self.store.enqueue_analysis('draft',1,1)
        self.assertEqual(self.store.reviews.batch('draft')['counts']['reviewed'],2)

    def test_human_label_precedence_and_lower_weight_training_provenance(self):
        self.publish(0)
        self.assertNotIn('automatic_style',self.store.training_export('draft')['examples'][0])
        self.publish(1)
        job=self.store.enqueue_train('draft')
        snapshot=self.store.job(job['id'],True)['payload']['snapshot']
        with patch.object(self.store.reviews.references,'_features',return_value=np.ones((80,32))):
            dataset=dataset_from_snapshot(snapshot,self.store.reviews.references)
        self.assertEqual(dataset['rows'][0]['style_origin'],'human')
        self.assertEqual(dataset['rows'][1]['style_weight'],.35)
        self.assertEqual(dataset['rows'][2]['style'],-1)
        recording=Path(self.imported['import']['recording']['path'])
        recording.write_bytes(b'changed recording')
        with patch.object(self.store.reviews.references,'_features',return_value=np.ones((80,32))):
            with self.assertRaisesRegex(ValueError,'recording changed'):dataset_from_snapshot(snapshot,self.store.reviews.references)
        corrupted=deepcopy(snapshot);corrupted['examples'][1]['automatic_style']['source_hashes']=[]
        with patch.object(self.store.reviews.references,'_features',return_value=np.ones((80,32))):
            with self.assertRaisesRegex(ValueError,'provenance'):dataset_from_snapshot(corrupted,self.store.reviews.references)

    def test_analysis_api_state_enqueue_dedup_and_validation(self):
        client=TestClient(create_app(self.settings),base_url='http://127.0.0.1')
        url='/api/v1/reference-drafts/draft/analysis'
        job=client.post(url,json={'position':1,'expected_revision':1})
        self.assertEqual(job.status_code,200)
        self.assertEqual(job.json()['id'],client.post(url,json={'position':1,'expected_revision':1}).json()['id'])
        self.assertEqual(client.get(url).json()['jobs'][0]['status'],'queued')
        self.assertEqual(client.post(url,json={'position':True}).status_code,422)
        self.assertEqual(client.post(url,json={'position':1,'expected_revision':0}).status_code,409)

    def test_result_counts_distinguish_processed_audio_from_recognized_techniques(self):
        job=self.store.enqueue_analysis('draft',1,1);self.store.claim('worker')
        summary={'processed':1,'recognized':0,'training_labels':0,'uncertain':1}
        self.store.finish(job['id'],'worker','succeeded',{'summary':summary,'analyses':[],'algorithm_version':VERSION})
        state=self.store.analysis_state('draft')
        self.assertEqual(state['jobs'][0]['summary'],summary)
        self.assertFalse(state['jobs'][0]['outdated'])


class AnalysisMigrationTests(unittest.TestCase):
    def test_version_seven_jobs_and_model_foreign_keys_survive(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'app.sqlite3'
            c=sqlite3.connect(path)
            c.executescript(SCHEMA.replace("'train','test_mix','transition_analysis'","'train','test_mix'"))
            c.execute('PRAGMA user_version=7')
            c.execute("INSERT INTO reference_imports(id,snapshot_json) VALUES ('ref','{}')")
            c.execute("INSERT INTO reference_alignments(id,reference_id,snapshot_json) VALUES ('align','ref','{}')")
            c.execute("INSERT INTO reference_transition_drafts(id,reference_id,alignment_id,snapshot_json) VALUES ('draft','ref','align','{}')")
            c.execute("INSERT INTO workflow_jobs(id,kind,request_key,status,payload_json) VALUES ('train','train','key','succeeded','{}')")
            c.execute("INSERT INTO decision_models VALUES ('model','train','draft','model','{}',CURRENT_TIMESTAMP)")
            c.commit();c.close()
            db=Database(path);db.initialize();db.initialize()
            with db.connection() as c:
                self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],9)
                self.assertIsNone(c.execute('PRAGMA foreign_key_check').fetchone())
                self.assertEqual(c.execute('SELECT job_id FROM decision_models').fetchone()[0],'train')
                c.execute("INSERT INTO workflow_jobs(id,kind,request_key,status,payload_json) VALUES ('analysis','transition_analysis','key2','queued','{}')")
