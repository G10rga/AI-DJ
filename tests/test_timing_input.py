"""Analysis inputs are gain-invariant, bounded and bound to timing reports."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

from backend.app.audio.timing_input import canonical_timing_input, CONTEXT_SECONDS, VERSION
from backend.app.audio.mdx import sha256_file
from backend.app.config import Settings, PROJECT_ROOT
from backend.app.vocal_rendering import independent_timing, timing_failure_message


class TimingInputTests(unittest.TestCase):
    def test_gain_invariance_without_changing_source_samples(self):
        t=np.arange(44100)/44100
        signal=np.column_stack((.1*np.sin(t*300),.12*np.sin(t*300))).astype('float32')
        before=signal.copy()
        first,metadata=canonical_timing_input(signal)
        second,_=canonical_timing_input(signal*.025)
        np.testing.assert_allclose(first,second,atol=3e-8)
        np.testing.assert_array_equal(signal,before)
        self.assertAlmostEqual(float(np.sqrt(np.mean(first.mean(axis=1)**2))),.1,places=6)
        self.assertEqual(metadata['policy'],VERSION)
        self.assertEqual(CONTEXT_SECONDS,24.)

    def test_peak_limit_and_silence_remain_explicit(self):
        signal=np.zeros((10000,2),dtype='float32');signal[100]=20
        actual,metadata=canonical_timing_input(signal)
        self.assertLessEqual(float(np.max(np.abs(actual.mean(axis=1)))),.980001)
        self.assertEqual(metadata['status'],'observed')
        for silent in (np.zeros((100,2)),np.column_stack((np.ones(100),-np.ones(100)))):
            actual,metadata=canonical_timing_input(silent)
            self.assertIsNone(actual)
            self.assertEqual(metadata['status'],'unknown')
            self.assertIsNone(metadata['gain'])

    def test_invalid_audio_cannot_generate_beat_evidence(self):
        for signal in (np.zeros(100),np.zeros((100,1)),np.zeros((0,2)),
                       np.full((100,2),np.nan),np.full((100,2),np.inf),np.ones((100,2),complex)):
            with self.assertRaises(ValueError):canonical_timing_input(signal)

    def test_changed_detector_policy_cannot_reuse_a_timing_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);settings=Settings(data_root=root)
            runtime=root/('timeline/venv/Scripts/python.exe' if os.name=='nt' else 'timeline/venv/bin/python')
            runtime.parent.mkdir(parents=True);runtime.touch()
            prepared=root/'prepared.wav';prepared.write_bytes(b'isolated audio')
            decoded=root/'decoded.wav';decoded.write_bytes(b'isolated encoded PCM')
            records=[{'revision':0,'effective':{'beats':{'times':[0.,.5,1.]},'downbeats':{'times':[0.]}}}]
            policy_override=None
            def worker(command,**kwargs):
                request=json.loads(Path(command[-2]).read_text())
                report={'prepared_sha256':request['prepared_sha256'],'encoded_pcm_sha256':request['encoded_pcm_sha256'],
                    'plan_id':request['plan']['id'],'worker_sha256':sha256_file(PROJECT_ROOT/'scripts/transition_timing_worker.py'),
                    'detector_policy_sha256':policy_override or request['detector_policy_sha256']}
                report['source_marker_revisions']=request['source_marker_revisions']
                Path(command[-1]).write_text(json.dumps(report))
            with patch('backend.app.vocal_rendering.subprocess.run',side_effect=worker):
                independent_timing([prepared],decoded,{'id':'frozen-plan'},records,settings,root)
                policy_override='changed-analysis-input-policy'
                with self.assertRaisesRegex(ValueError,'different audio'):
                    independent_timing([prepared],decoded,{'id':'frozen-plan'},records,settings,root)

    def test_failure_message_identifies_rhythm_stage_instead_of_vocal_marks(self):
        message=timing_failure_message({'joins':[{'bar_support':[{'status':'unknown'},{'status':'regular'}]}]})
        self.assertIn('outgoing',message);self.assertIn('timeline editor',message)
        message=timing_failure_message({'joins':[{'bar_support':[{'status':'regular'}]*2,
            'checks':[{'comparison':'original_mapping_0','status':'mismatch','resolved_by':'same-context-original-1'}],
            'solo_checks':[{'status':'mismatch'}]}]})
        self.assertIn('encoded',message)
        self.assertNotIn('vocal',message)


if __name__=='__main__':unittest.main()
