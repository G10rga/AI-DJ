"""Transition extraction and human review must preserve evidence and listening truth."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from fastapi.testclient import TestClient
from backend.app.audio.probe import AudioInfo
from backend.app.config import Settings
from backend.app.reference_review import ReferenceReviewStore, presence, fit_mapping
from backend.app.web import create_app


class ReferenceReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.settings = Settings(data_root=self.root)
        self.store = ReferenceReviewStore(self.settings)
        for name in ('recording.mp4', 'first.mp3', 'second.mp3'):
            (self.root/name).write_bytes((name*10).encode())
        manifest = self.root/'manifest.json'
        manifest.write_text(json.dumps({'title':'Synthetic reference', 'recording':'recording.mp4',
            'tracks':[{'title':'First', 'sources':['first.mp3']}, {'title':'Second', 'sources':['second.mp3']}]}), encoding='utf-8')
        with patch('backend.app.references.probe', return_value=AudioInfo(200, 44100, 2, 'test')):
            self.reference = self.store.references.import_manifest(manifest)
        originals = self.reference['import']['tracks']
        hashes = [t['sources'][0]['content_hash'] for t in originals]
        def hypothesis(offset):
            return {'scale':1., 'offset_seconds':offset, 'similarity':.9, 'supporting_windows':3,
                    'anchors':[{'source_seconds':s,'mix_seconds':s+offset,'window_seconds':16,
                                'scale':1.,'similarity':.9} for s in (20,40,60)]}
        alignment = {'tracks':[{'alternatives':[{'source_hash':h,'hypotheses':[hypothesis(offset)]}]} for h,offset in zip(hashes,(0,80))],
                     'ordered_suggestions':[{'source_hash':h,'hypothesis_index':0,'anchor_mix_seconds':center} for h,center in zip(hashes,(48,128))]}
        self.store.references._save_alignment(self.reference['id'], alignment)
        rng=np.random.default_rng(9)
        first,second=rng.normal(size=(400,32)),rng.normal(size=(400,32))
        recording=np.zeros((800,32)); recording[:400]=first; recording[320:400]=(first[320:]+second[:80])/2; recording[400:720]=second[80:]
        self.features={self.reference['import']['recording']['content_hash']:recording,hashes[0]:first,hashes[1]:second}
        with patch.object(self.store.references, '_features', side_effect=lambda s:self.features[s['content_hash']]):
            self.batch = self.store.extract(self.reference['id'])
        self.client = TestClient(create_app(self.settings), base_url='http://127.0.0.1')

    def payload(self, learn=True):
        review=deepcopy(self.batch['transitions'][0]['draft'])
        review.update(learn=learn,reviewed=True)
        return review

    def test_measured_overlap_mapping_and_zero_unreviewed_exports(self):
        draft=self.batch['transitions'][0]['draft']
        self.assertAlmostEqual(draft['mix_start'],80,delta=5)
        self.assertAlmostEqual(draft['mix_end'],100,delta=5)
        self.assertAlmostEqual(draft['outgoing_source_in'],draft['mix_start'],delta=.01)
        self.assertAlmostEqual(draft['incoming_source_in'],draft['mix_start']-80,delta=.01)
        self.assertEqual(self.batch['counts']['reviewed'],0)
        self.assertEqual(self.store.export(self.batch['id'])['examples'],[])
        self.assertIsNone(draft['recipe'])
        self.assertAlmostEqual(fit_mapping({'scale':1.,'anchors':[{'source_seconds':x,'mix_seconds':x+10,'window_seconds':16,'scale':1.} for x in (0,40,80)]})['scale'],1.)

    def test_drafts_are_immutable_and_review_revisions_append(self):
        with patch.object(self.store.references, '_features', side_effect=lambda s:self.features[s['content_hash']]):
            same=self.store.extract(self.reference['id'])
        self.assertEqual(same['id'],self.batch['id'])
        original=deepcopy(self.batch['transitions'][0]['draft'])
        saved=self.store.save(self.batch['id'],0,0,self.payload())
        self.assertEqual(saved['counts'],{'total':1,'reviewed':1,'included':1,'excluded':0,'draft_saved':0})
        self.assertEqual(saved['transitions'][0]['draft'],original)
        self.assertEqual(len(self.store.export(self.batch['id'])['examples']),1)
        self.assertEqual(self.store.export(self.batch['id'])['style_examples'],0)
        with self.assertRaisesRegex(ValueError,'reload'):
            self.store.save(self.batch['id'],0,0,self.payload())
        self.store.save(self.batch['id'],0,1,self.payload(False))
        self.assertEqual(self.store.export(self.batch['id'])['examples'],[])
        with self.store.database.connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM reference_transition_reviews').fetchone()[0],2)

    def test_invalid_reviews_never_create_training_examples(self):
        changes=({'reviewed':None},{'learn':None},{'mix_start':-1},{'mix_end':float('nan')},
                 {'incoming_hash':'not registered'},{'incoming_source_in':None},{'recipe':'invented'},
                 {'overlap_bars':True},{'note':False},{'outgoing_source_out':999},{'unexpected':True})
        for change in changes:
            review=self.payload();review.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.store.save(self.batch['id'],0,0,review)
        self.assertEqual(self.store.batch(self.batch['id'])['counts']['reviewed'],0)

    def test_exclusion_can_preserve_unknowns_and_cut_can_be_zero_duration(self):
        review={key:None for key in self.payload()};review.update(reviewed=True,learn=False,note='Unusable source')
        self.store.save(self.batch['id'],0,0,review)
        cut=self.payload();cut.update(recipe='cut',mix_start=90,mix_end=90,outgoing_source_in=90,
                                     outgoing_source_out=90,incoming_source_in=10,incoming_source_out=10)
        self.store.save(self.batch['id'],0,1,cut)
        self.assertEqual(self.store.export(self.batch['id'])['style_examples'],1)

    def test_display_precision_at_source_end_round_trips_inside_bounds(self):
        review=self.payload();review['outgoing_source_out']=200.0004
        saved=self.store.save(self.batch['id'],0,0,review)
        self.assertEqual(saved['transitions'][0]['review']['outgoing_source_out'],200)
        review['outgoing_source_out']=200.001
        with self.assertRaises(ValueError):
            self.store.save(self.batch['id'],0,1,review)

    def test_recording_times_save_without_learning_decision_or_source_cues(self):
        pending={'reviewed':False,'learn':None,'mix_start':82,'mix_end':98}
        saved=self.store.save(self.batch['id'],0,0,pending)
        self.assertEqual(saved['counts'],{'total':1,'reviewed':0,'included':0,'excluded':0,'draft_saved':1})
        self.assertEqual(saved['transitions'][0]['review']['mix_start'],82)
        self.assertIsNone(saved['transitions'][0]['review']['incoming_source_in'])
        self.assertEqual(self.store.export(self.batch['id'])['examples'],[])
        # One endpoint can also be saved while the other is being located.
        pending['mix_end']=None
        updated=self.store.save(self.batch['id'],0,1,pending)
        self.assertIsNone(updated['transitions'][0]['review']['mix_end'])
        self.assertEqual(updated['transitions'][0]['revision'],2)
        with self.assertRaisesRegex(ValueError,'reload'):
            self.store.save(self.batch['id'],0,1,pending)

    def test_pending_include_is_not_approved_and_correction_revokes_old_export(self):
        self.store.save(self.batch['id'],0,0,self.payload())
        self.assertEqual(len(self.store.export(self.batch['id'])['examples']),1)
        pending=self.payload();pending.update(reviewed=False,mix_start=83,incoming_source_in=None)
        saved=self.store.save(self.batch['id'],0,1,pending)
        self.assertEqual(saved['counts']['reviewed'],0)
        self.assertEqual(saved['counts']['draft_saved'],1)
        self.assertEqual(self.store.export(self.batch['id'])['examples'],[])
        # Explicit approval remains strict even after timing-only saving exists.
        pending['reviewed']=True
        with self.assertRaisesRegex(ValueError,'six timing'):
            self.store.save(self.batch['id'],0,2,pending)
        self.store.save(self.batch['id'],0,2,self.payload())
        self.assertEqual(len(self.store.export(self.batch['id'])['examples']),1)

    def test_pending_timings_still_reject_invalid_values_with_field_names(self):
        for values in ({'mix_start':90,'mix_end':85},{'mix_start':201},{'mix_end':float('nan')}):
            with self.subTest(values=values),self.assertRaisesRegex(ValueError,'Recording entry/exit'):
                self.store.save(self.batch['id'],0,0,{'reviewed':False,'learn':None,**values})

    def test_api_review_ranges_changed_sources_and_path_restrictions(self):
        self.assertEqual(self.client.get('/references').status_code,200)
        self.assertEqual(self.client.get('/api/v1/references').json()['references'][0]['counts']['total'],1)
        draft_url='/api/v1/reference-drafts/'+self.batch['id']
        self.assertEqual(self.client.get(draft_url).json()['id'],self.batch['id'])
        audio_url=self.batch['audio_url']
        response=self.client.get(audio_url,headers={'Range':'bytes=0-5'})
        self.assertEqual(response.status_code,206)
        self.assertEqual(response.content,b'record')
        source_url=self.batch['tracks'][0]['sources'][0]['audio_url']
        self.assertEqual(self.client.get(source_url).status_code,200)
        self.assertEqual(self.client.get(source_url.replace(self.batch['tracks'][0]['sources'][0]['content_hash'],'unknown')).status_code,404)
        url=draft_url+'/transitions/0/reviews';payload={'expected_revision':0,'review':self.payload()}
        self.assertEqual(self.client.post(url,json=payload,headers={'Origin':'https://wrong.example'}).status_code,403)
        self.assertEqual(self.client.post(url,json=payload).status_code,200)
        self.assertEqual(self.client.post(url,json=payload).status_code,409)
        exported=self.client.get(draft_url+'/training-examples')
        self.assertEqual(len(exported.json()['examples']),1)
        self.assertIn('attachment',exported.headers['content-disposition'])
        self.assertEqual(self.client.post(url,json=[]).status_code,422)
        (self.root/'first.mp3').write_bytes(b'changed')
        self.assertEqual(self.client.get(source_url).status_code,409)

    def test_missing_alignment_stays_visible_as_unresolved_pair(self):
        original=self.store.references.get(self.reference['id'])['alignments'][-1]
        original.pop('id');original['ordered_suggestions'][1]=None
        self.store.references._save_alignment(self.reference['id'],original)
        with patch.object(self.store.references,'_features',side_effect=lambda s:self.features[s['content_hash']]):
            result=self.store.extract(self.reference['id'])
        self.assertEqual(len(result['transitions']),1)
        self.assertIsNone(result['transitions'][0]['draft']['mix_start'])
        self.assertEqual(result['transitions'][0]['kind'],'unresolved')


if __name__=='__main__':
    unittest.main()
