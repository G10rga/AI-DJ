"""Production bar evidence must remain local, observed and conservative."""
import unittest
import numpy as np
from backend.app.audio.bar_evidence import regular_bar_spans


class BarEvidenceTests(unittest.TestCase):
    def source(self):
        beats = np.round(.08+np.arange(600)*60/127, 2)
        return {'beats': beats.tolist(), 'downbeats': beats[::4].tolist(), 'duration_seconds': 300.}

    def test_source_wide_numbers_do_not_reset_at_chunk_boundaries(self):
        source = self.source()
        spans = regular_bar_spans(source)
        for span in spans:
            self.assertEqual(span['observed_downbeats'][0], source['downbeats'][span['bar_index']])
            self.assertAlmostEqual(span['source_bpm'], 127., delta=.05)
        around_seam = regular_bar_spans(source, 60.)
        self.assertGreater(around_seam[0]['bar_index'], 20)
        self.assertEqual(around_seam[0]['phrase_status'], 'candidate; completion unknown')

    def test_noncoincident_downbeats_never_establish_bar_phase(self):
        source = self.source()
        source['downbeats'] = [t+.2 for t in source['downbeats']]
        self.assertEqual(regular_bar_spans(source), [])

    def test_local_drift_missing_and_half_tempo_remain_unsupported(self):
        for kind in ('drift', 'missing', 'half'):
            source = self.source()
            if kind == 'drift':
                source['beats'] = (np.array(source['beats']) + .0002*np.arange(600)**2).tolist()
                source['downbeats'] = source['beats'][::4]
                source['duration_seconds'] = 400.
            elif kind == 'missing':
                source['beats'] = source['beats'][::2]
            else:
                source['beats'] = [t*2 for t in source['beats']]
                source['downbeats'] = source['beats'][::4]
                source['duration_seconds'] = 600.
            with self.subTest(kind=kind):
                self.assertEqual(regular_bar_spans(source), [])

    def test_invalid_parameters_are_rejected_and_empty_markers_stay_unknown(self):
        self.assertEqual(regular_bar_spans({'beats': [], 'downbeats': [], 'duration_seconds': 10}), [])
        for kwargs in ({'bars':0}, {'anchor':float('nan')}, {'after_span_context':-1}):
            with self.assertRaises(ValueError):
                regular_bar_spans(self.source(), **kwargs)


if __name__ == '__main__':
    unittest.main()
