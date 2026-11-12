"""Revisioned correction jobs, migration/media fences and pipeline isolation."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.app.audio.mdx import sha256_file
from backend.app.config import Settings
from backend.app.db import Database
from backend.app.models import ImprovedPlan, read_plan
from backend.app.planning.vocal_preserving import plan_set, propose_pair
from backend.app.timelines import TimelineStore
from backend.app.transition_review import capture, state, save, enqueue, media, choose_default, pipeline
from backend.app.web import create_app
from backend.app.workflow import Workflow
from tests.test_vocal_planner import fixture, active


class TransitionReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.settings=Settings(data_root=self.root,min_free_bytes=0)
        self.store=Workflow(self.settings);self.owner='test-owner';self.records=[]
        timelines=TimelineStore(self.root)
        for i in range(2):
            path=self.root/f'Original {i}.wav';path.write_bytes(f'isolated source {i}'.encode())
            data=fixture(f'source-{i}',source_hash=sha256_file(path))['effective']
            keys=timelines.save(path,data,data['config']);self.records.append(timelines.get(**keys))
        self.ids=[s['id'] for s in self.store.catalog()]
        self.client=TestClient(create_app(self.settings),base_url='http://127.0.0.1')

    def waiting(self):
        queued=self.store.enqueue_test(None,self.ids,72,True,'improved-transitions-1')
        job=self.store.claim(self.owner);self.assertEqual(job['id'],queued['id'])
        capture(self.store,job,self.owner,self.records)
        self.assertTrue(self.store.finish(job['id'],self.owner,'succeeded',{'status':'needs_review','review_items':[{'code':'timing_unknown','message':'Check this handoff.'}]}))
        return job['id']

    def report(self,records=None):
        records=records or self.records;plan=plan_set(records)['plan'];self.assertIsNotNone(plan)
        path=self.root/'renders'/('fixture-'+__import__('uuid').uuid4().hex+'.mp3');path.write_bytes(b'isolated validated artifact fixture')
        return {'status':'validated','pipeline':'improved-transitions-1','output':str(path),'audio_sha256':sha256_file(path),
            'plan':plan,'preparations':[{'gain_db':-3.} for _ in records],'post_mix_gain_db':-3.,
            'loudness':{'integrated_lufs':-20.,'true_peak_dbfs':-3.},'duration_seconds':plan['duration_seconds']}

    def test_public_pipeline_is_pinned_and_review_releases_worker_without_audio(self):
        identity=self.waiting();job=self.store.job(identity)
        self.assertEqual(job['status'],'needs_review');self.assertEqual(job['payload']['pipeline'],'improved-transitions-1')
        with self.store.db.connection() as c:
            self.assertIsNone(c.execute("SELECT * FROM workflow_leases WHERE name='heavy-worker'").fetchone())
        self.assertEqual(self.client.get(f'/api/v1/learning/jobs/{identity}/audio/mix').status_code,404)
        self.assertEqual(pipeline(self.store),'legacy-v1')
        r=self.client.post('/api/v1/learning/test-mixes',json={'track_ids':self.ids,'baseline':True,'pipeline':'unrecognized'})
        self.assertEqual(r.status_code,422)
        self.assertEqual(self.client.post('/api/v1/comparisons',json={'track_ids':self.ids,'pipeline':'improved-transitions-1','use_preferences':True}).status_code,422)

    def test_revision_conflict_preview_resume_and_source_evidence_history(self):
        identity=self.waiting();original=deepcopy(self.records)
        row={'0':{'outgoing_line_end':60.,'incoming_entry':.08,'vocal_confirmed':True}}
        saved=save(self.store,identity,0,row);self.assertEqual(saved['revision'],1)
        with self.assertRaisesRegex(ValueError,'reload'): save(self.store,identity,0,row)
        preview=enqueue(self.store,identity,1,join_index=0)
        child=self.store.job(preview['id'],internal=True)
        self.assertEqual(child['kind'],'join_preview');self.assertEqual(child['payload']['review_revision'],1)
        self.assertEqual(child['payload']['foundation_records'],original)
        resumed=enqueue(self.store,identity,1)
        self.assertEqual(self.store.job(resumed['id'],internal=True)['payload']['sources'],self.store.job(identity,internal=True)['payload']['sources'])
        self.assertEqual(self.store.job(identity)['status'],'needs_review')
        self.assertEqual(state(self.store,identity)['history'][0]['revision'],0)
        self.assertEqual(TimelineStore(self.root).get(original[0]['track_id'],original[0]['timeline_id'])['prediction'],original[0]['prediction'])

    def test_stale_preview_and_cancellation_cannot_publish(self):
        identity=self.waiting();preview=enqueue(self.store,identity,0,join_index=0)
        job=self.store.claim(self.owner);self.assertEqual(job['id'],preview['id'])
        save(self.store,identity,0,{})
        self.store.finish(job['id'],self.owner,'succeeded',self.report())
        self.assertEqual(self.store.job(job['id'])['status'],'interrupted')
        with self.assertRaisesRegex(ValueError,'reload'):self.store.retry(job['id'])
        with self.assertRaises(KeyError):media(self.store,job['id'])
        next_job=enqueue(self.store,identity,1,join_index=0);job=self.store.claim(self.owner)
        self.store.cancel(job['id']);self.store.finish(job['id'],self.owner,'succeeded',self.report())
        self.assertEqual(self.store.job(next_job['id'])['status'],'cancelled')
        with self.assertRaises(KeyError):media(self.store,job['id'])

    def test_validated_audio_version_two_plans_defaults_and_older_preview_remain_pinned(self):
        identity=self.waiting();preview=enqueue(self.store,identity,0,join_index=0);job=self.store.claim(self.owner)
        report=self.report();self.store.finish(job['id'],self.owner,'succeeded',report)
        saved_path=media(self.store,job['id']);self.assertEqual(saved_path.name,Path(report['output']).name)
        with self.store.db.connection() as c:
            raw=c.execute('SELECT plan_json FROM improved_plans WHERE job_id=?',(job['id'],)).fetchone()[0]
        self.assertIsInstance(read_plan(raw),ImprovedPlan)
        save(self.store,identity,0,{})
        self.assertEqual(media(self.store,job['id']),saved_path)
        with self.assertRaises(ValueError):choose_default(self.store,job['id'],True)
        resumed=enqueue(self.store,identity,1);run=self.store.claim(self.owner)
        self.store.finish(run['id'],self.owner,'succeeded',self.report())
        with self.assertRaises(ValueError):choose_default(self.store,resumed['id'],False)
        choose_default(self.store,resumed['id'],True)
        self.assertEqual(pipeline(self.store),'improved-transitions-1')
        self.assertEqual(self.store.job(identity)['payload']['pipeline'],'improved-transitions-1')
        url=f'/api/v1/learning/jobs/{run["id"]}/audio/mix'
        self.assertEqual(self.client.get(url,headers={'Range':'bytes=0-3'}).status_code,206)
        saved_path=media(self.store,run['id']);saved_path.write_bytes(b'changed')
        self.assertEqual(self.client.get(url).status_code,409)

    def test_api_original_ranges_revision_conflicts_and_origin_guard(self):
        identity=self.waiting();base=f'/api/v1/learning/jobs/{identity}/transition-review'
        value=self.client.get(base).json();self.assertEqual(value['revision'],0)
        self.assertEqual(len(value['sources']),2)
        self.assertEqual(self.client.get(value['sources'][0]['audio_url'],headers={'Range':'bytes=0-4'}).status_code,206)
        payload={'expected_revision':0,'corrections':{}}
        self.assertEqual(self.client.post(base+'/save',json=payload,headers={'Origin':'http://foreign.invalid'}).status_code,403)
        self.assertEqual(self.client.post(base+'/save',json=payload).status_code,200)
        self.assertEqual(self.client.post(base+'/save',json=payload).status_code,409)
        self.assertEqual(self.client.post(base+'/preview',json={'expected_revision':1}).status_code,422)
        self.assertEqual(self.client.get('/transition-review/'+identity).status_code,200)

    def test_human_corrections_resolve_vocal_uncertainty_but_not_broken_bars(self):
        a,b=deepcopy(self.records)
        active(a,0,160);active(b,0,160)
        correction={'outgoing_line_end':60.,'incoming_entry':.08,'vocal_confirmed':True}
        self.assertFalse(propose_pair(a,b)['candidates'])
        corrected=propose_pair(a,b,correction=correction)
        self.assertTrue(corrected['candidates'])
        self.assertTrue(all(c['evidence']['outgoing_quiet_guard']['status']=='human_verified' for c in corrected['candidates']))
        self.assertTrue(all(c['source_cues'][0]+c['fade_start_local_seconds']*c['source_ratios'][0]>=62 for c in corrected['candidates']))
        b['effective']['beats']['times']=b['effective']['beats']['times'][::2]
        b['effective']['downbeats']['times']=b['effective']['beats']['times'][::4]
        self.assertFalse(propose_pair(a,b,correction=correction)['candidates'])

    def test_schema_nine_migration_preserves_old_rows_and_new_review_relations(self):
        identity=self.waiting()
        with self.store.db.connection() as c:c.execute('PRAGMA user_version=9')
        Database(self.root/'app.sqlite3').initialize()
        self.assertEqual(self.store.job(identity)['status'],'needs_review')
        self.assertEqual(state(self.store,identity)['revision'],0)
        with self.store.db.connection() as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],10)
            self.assertIsNone(c.execute('PRAGMA foreign_key_check').fetchone())

    def test_new_comparison_feedback_is_separate_and_neither_only_excludes_this_ordered_pair(self):
        from backend.app.pair_comparisons import enqueue_pair,save_feedback
        queued=enqueue_pair(self.store,self.ids,pipeline='improved-transitions-1');job=self.store.claim(self.owner)
        capture(self.store,job,self.owner,self.records)
        result={'status':'validated','pipeline':'improved-transitions-1','alternatives':[self.report(),self.report()]}
        self.store.finish(job['id'],self.owner,'succeeded',result)
        saved=save_feedback(self.store,queued['id'],'neither',0,'isolated fixture')
        self.assertFalse(saved['preference_learning_eligible'])
        again=enqueue_pair(self.store,self.ids,pipeline='improved-transitions-1')
        self.assertEqual(set(self.store.job(again['id'],internal=True)['payload']['rejected_candidate_ids']),
                         {a['candidate_id'] for a in self.store.job(queued['id'])['result']['alternatives']})
        reversed_pair=enqueue_pair(self.store,list(reversed(self.ids)),pipeline='improved-transitions-1')
        self.assertEqual(self.store.job(reversed_pair['id'],internal=True)['payload']['rejected_candidate_ids'],[])
        with self.assertRaisesRegex(ValueError,'reload'):save_feedback(self.store,queued['id'],'tie',0,'')

    def test_preview_pins_latest_saved_timing_and_fences_subsequent_edits(self):
        identity=self.waiting();record=self.records[0];timelines=TimelineStore(self.root)
        keys={key:record[key] for key in ('track_id','timeline_id')}
        timelines.correct(**keys,expected_revision=0,changes={'phrase_boundaries':[2.]})
        preview=enqueue(self.store,identity,0,join_index=0);job=self.store.claim(self.owner)
        self.assertEqual(job['payload']['foundation_records'][0]['revision'],1)
        timelines.correct(**keys,expected_revision=1,changes={'phrase_boundaries':[4.]})
        self.store.finish(preview['id'],self.owner,'succeeded',self.report(job['payload']['foundation_records']))
        self.assertEqual(self.store.job(preview['id'])['status'],'interrupted')
        with self.assertRaises(KeyError):media(self.store,preview['id'])


if __name__=='__main__':unittest.main()
