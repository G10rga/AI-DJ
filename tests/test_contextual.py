"""Context-sensitive proposals, immutable records and actual recipe audio checks."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import soundfile as sf
from backend.app.config import Settings
from backend.app.models import MixPlan, Excerpt, Transition
from backend.app.storage import Storage
from backend.app.db import Database
from backend.app.rendering import render_set
from backend.app.timelines import VERSION as TIMELINE_VERSION, derive_bars
from backend.app.planning.contextual import propose_pair, RECIPES
from backend.app.planning.candidate_store import CandidateStore
from backend.app.planning.contextual_set import contextualize_plan
from backend.app.audio.mdx import sha256_file
from backend.app.audio.probe import run_audio, AudioError
from backend.app.auditions import validate_candidate, render_candidate, evaluate_pair, match_auditions
from scripts.synthetic_audio import write_fixture


def record(name, content='fixture', duration=240., bpm=120.):
    beat = 60/bpm
    layer = lambda times, method='fixture': {'times': times, 'confidence': None, 'provenance': method}
    downs = np.arange(.5, duration, 4*beat).tolist()
    data = {'version': TIMELINE_VERSION, 'content_hash': content, 'duration_seconds': duration,
            'beats': layer(np.arange(.5, duration, beat).tolist()), 'downbeats': layer(downs),
            'phrase_boundaries': layer(downs[::8], {'method':'human correction','revision':1}),
            'features': [{'start': float(i), 'end': min(float(i+1), duration), 'rms': .1, 'peak': .5,
                          'bass_rms': .06, 'transient_peaks_per_second': 2., 'chroma': [1.]+[0.]*11}
                         for i in range(int(duration))],
            'embeddings': [{'start': float(i), 'end': min(float(i+5), duration), 'vector': [1.]+[0.]*767}
                           for i in range(0, int(duration), 5)],
            'vocal_activity': [{'start': float(i)/2, 'end': min((i+1)/2,duration),'active':False,'rms':0.}
                               for i in range(int(duration*2))],
            'vocal_status': {'available':True}, 'sections': [], 'config': {'test_model':'frozen'}}
    data['bars'] = derive_bars(data)
    return {'track_id':name,'timeline_id':'timeline-'+name,'revision':1,'prediction':deepcopy(data),'effective':data}


class ContextProposalTests(unittest.TestCase):
    def test_all_recipes_cue_variation_limit_and_immutable_inputs(self):
        a,b=record('a'),record('b')
        before=deepcopy(a)
        batch=propose_pair(a,b)
        self.assertLessEqual(len(batch['candidates']),12)
        self.assertEqual({c['recipe'] for c in batch['candidates']},set(RECIPES))
        self.assertGreater(len({tuple(c['anchors_seconds']) for c in batch['candidates']}),1)
        self.assertEqual(a,before)
        for c in batch['candidates']:
            MixPlan.from_json(json.dumps(c['plan'])).validate()
            self.assertEqual(c['sources'][0]['correction_revision'],1)
            self.assertEqual(c['duration_seconds'],128)
            self.assertEqual(c['handoff_seconds'],64)
        with self.assertRaises(ValueError):propose_pair(a,b,maximum=13)

    def test_unknown_vocals_do_not_mean_a_gap_and_spike_does_not_allow_cut(self):
        a,b=record('a'),record('b')
        for r in (a,b):
            r['effective']['vocal_status']['available']=False
        batch=propose_pair(a,b)
        self.assertTrue(batch['candidates'])
        self.assertNotIn('phrase_cut',{c['recipe'] for c in batch['candidates']})
        a,b=record('a'),record('b')
        for r in (a,b):r['effective']['phrase_boundaries']['provenance']='tentative grid'
        batch=propose_pair(a,b)
        self.assertNotIn('phrase_cut',{c['recipe'] for c in batch['candidates']})

    def test_preserves_outgoing_buildup_and_rejects_energy_collapse(self):
        a,b=record('a'),record('b')
        a['effective']['phrase_boundaries']['times']=[144.5]
        for f in a['effective']['features']:f['rms']=.04 if f['start']<144.5 else .2
        batch=propose_pair(a,b)
        self.assertFalse(batch['candidates'])
        self.assertTrue(any('buildup' in r['reason'] for r in batch['rejections']))
        a,b=record('a'),record('b')
        for f in b['effective']['features']:f['rms']=.01
        batch=propose_pair(a,b)
        self.assertFalse(batch['candidates'])
        self.assertTrue(any('collapse energy' in r['reason'] for r in batch['rejections']))

    def test_tempo_outliers_short_sources_and_uncertain_bars(self):
        self.assertFalse(propose_pair(record('a'),record('b',bpm=180))['candidates'])
        self.assertFalse(propose_pair(record('a',duration=3),record('b',duration=3))['candidates'])
        a=record('a');a['effective']['downbeats']['times']=a['effective']['beats']['times'][::3]
        self.assertFalse(propose_pair(a,record('b'))['candidates'])

    def test_corrections_change_identity_and_store_rejects_mutation(self):
        a,b=record('a'),record('b');first=propose_pair(a,b)['candidates'][0]
        a['revision']=2
        self.assertNotEqual(first['id'],propose_pair(a,b)['candidates'][0]['id'])
        with tempfile.TemporaryDirectory() as root:
            store=CandidateStore(root);store.register(first);store.register(first)
            store.event(first['id'],'rejected',{'reason':'fixture waveform failure'})
            self.assertEqual(store.load(first['id']),first)
            self.assertEqual(len(store.events(first['id'])),1)
            changed=deepcopy(first);changed['context_score']+=1
            with self.assertRaises(ValueError):store.register(changed)

    def test_set_geometry_retains_all_entries_and_missing_timelines_fallback(self):
        plan=MixPlan('set',1,(Excerpt('a',0,160,240,120,120),Excerpt('b',0,160,240,120,120)),(Transition('eq_cut',16,8),))
        entries=[{'entry_id':name,'path':name+'.wav','analysis':{'content_hash':name}} for name in ('a','b')]
        details={'joins':[{'style':'eq_cut','bars':8}]}
        with tempfile.TemporaryDirectory() as root:
            settings=Settings(data_root=Path(root),min_free_bytes=0);storage=Storage(Path(root));storage.initialize()
            result,explanation=contextualize_plan(entries,plan,details,settings,storage)
            self.assertEqual(result,plan)
            self.assertIn('Missing',explanation['contextual']['joins'][0]['fallback'])
            candidate=propose_pair(record('a'),record('b'))['candidates'][0]
            applied=MixPlan.from_json(json.dumps(candidate['plan']))
            with patch('backend.app.planning.contextual_set.TimelineStore.for_content',side_effect=[record('a'),record('b')]), \
                 patch('backend.app.planning.contextual_set.evaluate_pair',return_value={'validations':[{'candidate':candidate,'validation':{'applied_plan':json.loads(applied.to_json())}}],'rejections':[]}):
                result,explanation=contextualize_plan(entries,plan,details,settings,storage)
            self.assertEqual({e.track_id for e in result.excerpts},{'a','b'})
            self.assertIsNotNone(explanation['contextual']['joins'][0]['selected'])
            result.validate()

    def test_middle_track_geometry_rejects_conflicting_adjacent_choices(self):
        names=('a','b','c')
        plan=MixPlan('three',1,tuple(Excerpt(n,0,180,240,120,120) for n in names),
                     (Transition('eq_cut',16,8),Transition('eq_cut',16,8)))
        entries=[{'entry_id':n,'path':n+'.wav','analysis':{'content_hash':n}} for n in names]
        c1=next(c for c in propose_pair(record('a'),record('b'))['candidates'] if c['recipe']=='groove_32')
        c2=next(c for c in propose_pair(record('b'),record('c'))['candidates'] if c['recipe']=='groove_32')
        p1=MixPlan.from_json(json.dumps(c1['plan']));p2=MixPlan.from_json(json.dumps(c2['plan']))
        p2=replace(p2,excerpts=(replace(p2.excerpts[0],source_in=0,source_out=100),p2.excerpts[1]))
        results=[{'validations':[{'candidate':c,'validation':{'applied_plan':json.loads(p.to_json())}}],'rejections':[]}
                 for c,p in ((c1,p1),(c2,p2))]
        with tempfile.TemporaryDirectory() as root:
            settings=Settings(data_root=Path(root),min_free_bytes=0);storage=Storage(Path(root));storage.initialize()
            with patch('backend.app.planning.contextual_set.TimelineStore.for_content',side_effect=[record('a'),record('b'),record('b'),record('c')]), \
                 patch('backend.app.planning.contextual_set.evaluate_pair',side_effect=results):
                changed,details=contextualize_plan(entries,plan,{'joins':[{},{}]},settings,storage)
            self.assertEqual({e.track_id for e in changed.excerpts},set(names))
            self.assertIsNone(details['contextual']['joins'][1]['selected'])
            self.assertTrue(details['contextual']['joins'][1]['fallback'])
            changed.validate()


class ContextAudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings=Settings.from_env()
        try:run_audio([cls.settings.ffmpeg,'-version'],timeout=15)
        except AudioError as exc:raise unittest.SkipTest(str(exc))
        parent=cls.settings.data_root/'tmp';parent.mkdir(parents=True,exist_ok=True)
        cls.temp=tempfile.TemporaryDirectory(dir=parent,prefix='test-context-audio-')
        cls.root=Path(cls.temp.name);cls.settings=replace(cls.settings,data_root=cls.root,min_free_bytes=0)
        cls.storage=Storage(cls.root);cls.storage.initialize()
        cls.source=cls.root/'source.wav';write_fixture(cls.source,seconds=240)
        h=sha256_file(cls.source)
        cls.batch=propose_pair(record('a',h),record('b',h))
        cls.sources={'a':cls.source,'b':cls.source}

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    @staticmethod
    def fake_separator(path,pointer,settings,storage):
        samples,rate=sf.read(path,dtype='float32',always_2d=True)
        vocals=path.with_name(path.stem+'-voice.wav');sf.write(vocals,np.zeros_like(samples),rate,subtype='FLOAT')
        return {'instrumental':str(path),'vocals':str(vocals)}

    def test_all_four_recipes_render_with_common_handoff_and_valid_tails(self):
        reports=[]
        for recipe in RECIPES:
            c=next(c for c in self.batch['candidates'] if c['recipe']==recipe)
            validation=validate_candidate(c,self.sources,self.settings,self.storage)
            report=render_candidate(c,validation,self.sources,self.settings,self.storage,separate=self.fake_separator)
            self.assertAlmostEqual(report['duration'],128,delta=.15)
            self.assertEqual(report['handoff_seconds'],64)
            self.assertLess(report['encoded_peak'],1)
            self.assertGreater(report['energy_rms_2s'][-2],.01)
            reports.append(report)
        self.assertEqual(reports[1]['recipe']['blend_profile'],'controlled')
        self.assertEqual(reports[-1]['recipe']['name'],'phrase_cut')
        matched=match_auditions(reports[:2],self.settings,self.storage)
        self.assertLess(abs(matched[0]['loudness']['integrated_lufs']-matched[1]['loudness']['integrated_lufs']),.3)
        self.assertTrue(all(r['loudness']['true_peak_dbfs'] <= -1 for r in matched))
        self.assertTrue(all(Path(r['matched_from']).exists() and r.get('audio_sha256') for r in matched))

    def test_waveform_failures_are_disqualified_before_selection(self):
        batch=dict(self.batch,candidates=self.batch['candidates'][:2])
        with patch('backend.app.auditions.validate_candidate',side_effect=ValueError('late beat drift')):
            result=evaluate_pair(batch,self.sources,self.settings,self.storage,audition_count=0)
        self.assertFalse(result['validations'])
        self.assertTrue(any(r['reason']=='late beat drift' for r in result['rejections']))

    def test_full_set_renderer_honors_controlled_blend_and_phrase_cut(self):
        for recipe in ('controlled_16','phrase_cut'):
            c=next(c for c in self.batch['candidates'] if c['recipe']==recipe)
            validation=validate_candidate(c,self.sources,self.settings,self.storage)
            plan=replace(MixPlan.from_json(json.dumps(validation['applied_plan'])),mix_id='full-'+recipe)
            entries=[{'entry_id':n,'path':str(self.source),'analysis':{'content_hash':sha256_file(self.source)}} for n in ('a','b')]
            db=Database(self.root/'app.sqlite3');db.initialize();db.register_plan(entries,plan)
            # Use float instrumentals here, matching the actual separator's format.
            def float_separator(path,pointer,settings,storage):
                result=self.fake_separator(path,pointer,settings,storage)
                samples,rate=sf.read(path,dtype='float32',always_2d=True)
                inst=path.with_name(path.stem+'-float.wav');sf.write(inst,samples,rate,subtype='FLOAT')
                result['instrumental']=str(inst);return result
            report=render_set(entries,plan,{'contextual':{'joins':[{'selected':{'candidate_id':c['id']}}]}},
                              self.settings,self.storage,separate=float_separator)
            self.assertEqual(report['applied_plan']['transitions'][0]['style'],plan.transitions[0].style)
            self.assertEqual(report['applied_plan']['transitions'][0]['bars'],plan.transitions[0].bars)
            self.assertTrue(report['published'])

    def test_changed_source_rejected(self):
        c=self.batch['candidates'][0]
        with self.assertRaisesRegex(ValueError,'source changed'):
            validate_candidate(c,{'a':self.source,'b':Path(__file__)},self.settings,self.storage)


if __name__=='__main__':unittest.main()
