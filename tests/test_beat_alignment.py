"""Independent beat/downbeat comparisons must reject common rhythm errors."""
import unittest
import numpy as np
from backend.app.research.beat_alignment import marker_alignment,bar_support,require_alignment


class BeatAlignmentTests(unittest.TestCase):
    def test_matching_kicks_can_still_have_wrong_bar_phase(self):
        beats=np.arange(0,20,.5)
        self.assertEqual(marker_alignment(beats,beats+.005,1,19)['status'],'aligned')
        # Same 120 BPM, but incoming beat one is a beat later in each bar.
        result=marker_alignment(np.arange(0,20,2),np.arange(.5,20,2),1,19,.07)
        self.assertEqual(result['status'],'mismatch')
        self.assertAlmostEqual(result['p90_absolute_offset_seconds'],.5)

    def test_half_beat_and_half_tempo_errors_fail(self):
        beats=np.arange(0,20,.5)
        for other in (np.arange(.25,20,.5),np.arange(0,20,1)):
            with self.subTest(other=other[:3]):
                self.assertEqual(marker_alignment(beats,other,1,19)['status'],'mismatch')

    def test_missing_or_invalid_predictions_never_claim_alignment(self):
        self.assertEqual(marker_alignment([],[],1,19)['status'],'unknown')
        for other in ([1,float('nan'),3],[3,2,1],[1,1,2]):
            with self.assertRaises(ValueError):marker_alignment([1,2,3],other,1,19)

    def test_sparse_or_irregular_bars_and_missing_evidence_block_publication(self):
        beats=np.arange(0,20,.5)
        regular=bar_support(beats,np.arange(0,20,2),1,19)
        self.assertEqual(regular['status'],'regular')
        irregular=bar_support(beats,np.arange(0,20,1),1,19)
        self.assertEqual(irregular['status'],'unknown')
        sparse=bar_support(beats,[2,4],1,19)
        self.assertEqual(sparse['status'],'unknown')
        good={'beats':{'status':'aligned'},'downbeats':{'status':'aligned'},'bar_support':[regular,regular]}
        require_alignment(good)
        for bad in ({},{**good,'downbeats':{'status':'mismatch'}},
                    {**good,'beats':{'status':'unknown'}},{**good,'bar_support':[regular,irregular]},
                    {**good,'bar_support':[regular,sparse]}):
            with self.assertRaisesRegex(ValueError,'publication blocked'):require_alignment(bad)


if __name__=='__main__':unittest.main()
