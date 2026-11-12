"""Shared entry points, actual float mixing/encoding, and publication gates."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import soundfile as sf

from backend.app.audio.mdx import sha256_file
from backend.app.audio.probe import run_audio, AudioError
from backend.app.audio.vocal_automation import relative_gain
from backend.app.config import Settings
from backend.app.improved_transitions import generate, compare
from backend.app.planning.vocal_preserving import plan_set
from backend.app.storage import Storage
from backend.app.vocal_rendering import mix_float, render_plan
from tests.test_vocal_planner import fixture


class SharedServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.storage = Storage(Path(self.temporary.name)); self.storage.initialize()
        self.records = [fixture('a'), fixture('b')]
        self.calls = []

    def fake_renderer(self, plan, records, paths, settings, storage, **kwargs):
        output = storage.path('renders', f'test-{len(self.calls)}.mp3')
        output.write_bytes(b'isolated test artifact')
        self.calls.append(plan)
        return {'status':'validated','output':str(output),'plan':plan,'audio_sha256':sha256_file(output),
                'loudness':{'integrated_lufs':-20.,'true_peak_dbfs':-3.}}

    def test_generate_and_compare_share_planner_controls_renderer_and_pin_selections(self):
        generated = generate(self.records,['a','b'],None,self.storage,renderer=self.fake_renderer)
        compared = compare(self.records,['a','b'],None,self.storage,renderer=self.fake_renderer)
        self.assertEqual(generated['status'],'validated')
        self.assertEqual(compared['status'],'validated')
        self.assertEqual(generated['plan']['joins'][0]['candidate']['id'], compared['alternatives'][0]['plan']['joins'][0]['candidate']['id'])
        self.assertEqual(len(self.calls),3)
        self.assertEqual({r['plan']['joins'][0]['candidate']['recipe'] for r in compared['alternatives']},
                         {'plain_crossfade','protected_vocal'})
        self.assertFalse(compared['preference_learning_eligible'])
        for alternative in compared['alternatives']:
            self.assertTrue(Path(alternative['output']).is_file())

    def test_compare_does_not_replace_selected_failure_or_publish_half_a_pair(self):
        calls = []
        def renderer(*args, **kwargs):
            calls.append(args[0]['joins'][0]['candidate']['id'])
            return {'status':'needs_review','review_items':[{'code':'independent_timing_failed'}]}
        result = compare(self.records,['a','b'],None,self.storage,renderer=renderer)
        self.assertEqual(result['status'],'needs_review')
        self.assertEqual(len(calls),1)
        self.assertEqual(result['alternatives'],[])
        self.assertEqual(list((self.storage.root/'renders').iterdir()),[])

    def test_rejected_candidates_never_reappear_and_cancelled_work_does_not_render(self):
        candidates = plan_set(self.records)['proposals'][0]['candidates']
        result = compare(self.records,['a','b'],None,self.storage,
            rejected_ids=[c['id'] for c in candidates],renderer=self.fake_renderer)
        self.assertEqual(result['status'],'needs_review')
        with self.assertRaises(RuntimeError):
            generate(self.records,['a','b'],None,self.storage,live=lambda:False,renderer=self.fake_renderer)
        self.assertEqual(self.calls,[])

    def test_both_existing_job_entry_points_dispatch_to_same_opt_in_backend(self):
        from scripts.workflow_job import execute
        from backend.app.pair_comparisons import generate_pair
        store = SimpleNamespace(settings=None, progress=lambda *args:None)
        job = {'id':'test-job','kind':'pair_audition','payload':{'pipeline':'improved-transitions-1'}}
        with patch('backend.app.improved_transitions.execute_job', return_value={'status':'needs_review'}) as operation:
            execute(store,job,'owner',self.storage.root)
            generate_pair(store,job,'owner',lambda *args:None)
        self.assertEqual(operation.call_count,2)


class FloatRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = Settings.from_env()
        try:
            run_audio([cls.settings.ffmpeg,'-version'])
        except AudioError as exc:
            raise unittest.SkipTest(str(exc))

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.storage = Storage(self.root/'storage'); self.storage.initialize()
        self.settings = Settings(data_root=self.storage.root, min_free_bytes=0,
            ffmpeg=self.settings.ffmpeg, ffprobe=self.settings.ffprobe)

    def test_streamed_mixer_keeps_source_samples_continuous_across_block_boundaries(self):
        rate = 44100; count = 8*rate
        t = np.arange(count)/rate
        a = np.column_stack((t*.1,-t*.1)).astype('float32')
        b = np.column_stack((np.sin(t)*.2,np.cos(t)*.3)).astype('float32')
        paths = [self.root/'a.wav',self.root/'b.wav']
        for path, data in zip(paths,(a,b)): sf.write(path,data,rate,subtype='FLOAT')
        plan = {'duration_seconds':12.,'sources':[{'start_seconds':0.},{'start_seconds':4.}],
            'joins':[{'entry_seconds':4.,'fade_start_seconds':6.,'end_seconds':8.,'candidate':{'recipe':'protected_vocal'}}]}
        output = self.root/'mix.wav'; mix_float(paths,plan,output)
        actual,_ = sf.read(output,dtype='float32',always_2d=True)
        times = np.arange(12*rate)/rate
        expected = np.zeros_like(actual)
        expected[:count] += a*relative_gain(plan,0,times[:count])[:,None]
        expected[4*rate:] += b*relative_gain(plan,1,times[4*rate:])[:,None]
        np.testing.assert_allclose(actual,expected,atol=2e-7)

    def originals(self):
        paths = [self.root/'original-a.wav',self.root/'original-b.wav']
        rate = 44100
        t = np.arange(100*rate)/rate
        for i,path in enumerate(paths):
            samples = np.column_stack((1.2*np.sin(2*np.pi*(220+i*110)*t),
                                       .9*np.sin(2*np.pi*(330+i*110)*t))).astype('float32')
            sf.write(path,samples,rate,subtype='FLOAT')
        records = [fixture(f'source-{i}',duration=100.,source_hash=sha256_file(path)) for i,path in enumerate(paths)]
        result = plan_set(records,seconds=40.,predictions=[{'recipe':'protected_vocal'}])
        self.assertEqual(result['status'],'planned')
        return paths, records, result['plan']

    def test_real_float_preparation_encoding_and_timing_failure_publication_guard(self):
        paths,records,plan = self.originals()
        seen = []
        def timing(prepared, decoded, actual_plan, *args):
            seen.append(actual_plan['id'])
            self.assertEqual(sf.info(decoded).subtype,'FLOAT')
            self.assertTrue(all(sf.info(path).subtype=='FLOAT' for path in prepared))
            return {'status':'needs_review','joins':[{'status':'needs_review'}]}
        failed = render_plan(plan,records,paths,self.settings,self.storage,timing=timing)
        self.assertEqual(failed['status'],'needs_review')
        self.assertEqual(list((self.storage.root/'renders').iterdir()),[])
        def valid(*args): return {'status':'validated','joins':[{'status':'validated'}]}
        passed = render_plan(plan,records,paths,self.settings,self.storage,timing=valid)
        self.assertEqual(passed['status'],'validated',passed.get('review_items'))
        self.assertEqual(passed['plan']['id'],plan['id'])
        self.assertTrue(Path(passed['output']).is_file())
        self.assertGreater(passed['preparations'][0]['sample_peak_before_gain'],1.)
        self.assertLess(passed['sample_peak'],1.)
        self.assertLessEqual(passed['loudness']['true_peak_dbfs'],-1.)
        self.assertEqual(seen,[plan['id']])


if __name__=='__main__': unittest.main()
