"""Protect ongoing vocal playback and require complete quiet-region evidence."""
import unittest
import numpy as np
from backend.app.research.vocal_handoff import envelopes,require_quiet,activity_rows


class VocalHandoffTests(unittest.TestCase):
    def test_outgoing_line_stays_at_full_gain_and_intro_rises_over_bars(self):
        out,inc=envelopes(60000,1000,22,30,38)
        self.assertTrue(np.all(out[:30001]==1))
        self.assertTrue(np.all(inc[:22001]==0))
        self.assertAlmostEqual(inc[30000],.25)
        self.assertAlmostEqual(out[34000],.5)
        self.assertTrue(np.all(out[38000:]==0))
        self.assertTrue(np.all(inc[38000:]==1))
        self.assertLess(float(np.abs(np.diff(inc)).max()),.001)
        self.assertLess(float(np.abs(np.diff(out)).max()),.001)

    def test_vocal_anywhere_in_fade_rejects_even_if_selected_bar_is_quiet(self):
        rows=[[i*.5,.001,.1,.01] for i in range(50)]
        require_quiet(rows,5,20)
        rows[18][1]=.06;rows[18][3]=.6
        with self.assertRaisesRegex(ValueError,'Vocal activity'):require_quiet(rows,5,20)

    def test_missing_unknown_or_uncovered_activity_never_counts_as_silence(self):
        rows=[[i*.5,.001,.1,.01] for i in range(50)]
        for invalid,start,end in [(rows[:8]+rows[9:],5,20),(rows,0,26),([],0,5),
                                  ([[0,.1,.1,float('nan')],[.5,.1,.1,.1]],0,1)]:
            with self.assertRaises(ValueError):require_quiet(invalid,start,end)

    def test_screening_preserves_source_offsets_and_relative_vocal_levels(self):
        master=np.ones((4000,2),dtype=np.float32)*.2
        vocal=master*.05
        rows=activity_rows(vocal,master,1000,54)
        self.assertEqual(rows[0][0],54)
        self.assertEqual(rows[-1][0],57.5)
        self.assertAlmostEqual(rows[0][3],.05)
        require_quiet(rows,54,58)


if __name__=='__main__':unittest.main()
