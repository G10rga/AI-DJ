"""Observed bar fitting must preserve tempo despite quantized beat timestamps."""
import unittest
import numpy as np
from backend.app.research.steady_bars import stable_spans


class SteadyBarTests(unittest.TestCase):
    def test_early_intro_requires_explicit_short_leading_context(self):
        beats=.08+np.arange(600)*.48
        source={'beats':beats.tolist(),'downbeats':beats[::4].tolist(),'duration_seconds':307.6}
        self.assertEqual(stable_spans(source,3.92),[])
        choice=stable_spans(source,3.92,minimum_start=0)[0]
        self.assertAlmostEqual(choice['source_cue'],3.92)
        self.assertAlmostEqual(choice['source_bpm'],125.)

    def source(self):
        beats=np.round(10+np.arange(400)*60/127,2)
        return {'beats':beats.tolist(),'downbeats':beats[::4].tolist(),'duration_seconds':220}

    def test_fitted_tempo_avoids_bias_from_twenty_ms_marker_rounding(self):
        source=self.source()
        choices=stable_spans(source,100.)
        self.assertTrue(choices)
        choice=choices[0]
        self.assertAlmostEqual(choice['source_bpm'],127.,delta=.05)
        self.assertLess(choice['fit_p90_seconds'],.015)
        self.assertEqual(len(choice['observed_beats']),33)
        self.assertLess(choice['distance_from_old_cue_seconds'],1)

    def test_wrong_meter_or_dropped_beats_cannot_supply_eight_regular_bars(self):
        source=self.source()
        source['downbeats']=source['beats'][::2]
        self.assertEqual(stable_spans(source,100.),[])
        source=self.source()
        source['beats']=[beat for i,beat in enumerate(source['beats']) if i%5]
        self.assertEqual(stable_spans(source,100.),[])

    def test_invalid_or_insufficient_evidence_is_rejected(self):
        source=self.source();source['beats'][5]=float('nan')
        with self.assertRaises(ValueError):stable_spans(source,100.)
        source=self.source();source['downbeats']=source['downbeats'][:3]
        self.assertEqual(stable_spans(source,100.),[])


if __name__=='__main__':unittest.main()
