"""Run in the isolated CPU runtime without web or scikit-learn dependencies."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import numpy as np
from backend.app.planning.decision_learning import fit, predict


@unittest.skipUnless(importlib.util.find_spec('torch'), 'Use isolated PyTorch runtime')
class AutomaticStyleTrainingTests(unittest.TestCase):
    def test_automatic_agreement_is_separate_from_human_accuracy(self):
        rng=np.random.default_rng(7)
        rows=[]
        for i in range(16):
            origin='human' if i%4<2 else 'automatic_spectral_estimate' if i%4==2 else 'unknown'
            rows.append({'x':rng.normal(size=130).tolist(),'y':[.2,.4,.1,.3,.5],
                         'durations':[200,200],'source_hashes':[f'a{i}',f'b{i}'],
                         'style':2 if origin=='human' else 1 if origin=='automatic_spectral_estimate' else -1,
                         'style_origin':origin,'style_weight':.35 if origin=='automatic_spectral_estimate' else 1.})
        with tempfile.TemporaryDirectory() as directory:
            result=fit({'rows':rows},Path(directory),epochs=10)
            report=result['report']
            self.assertEqual(report['human_style_examples'],8)
            self.assertEqual(report['automatic_style_examples'],4)
            self.assertEqual(report['evaluation']['evaluated_style_examples'],2)
            self.assertEqual(report['evaluation']['automatic_style_examples'],1)
            self.assertIsNotNone(report['evaluation']['automatic_style_agreement'])
            self.assertFalse(report['active'])
            self.assertIn(predict(directory,[{'x':[0.]*130,'durations':[200,200]}])[0]['recipe'],('eq_8','controlled_16'))
