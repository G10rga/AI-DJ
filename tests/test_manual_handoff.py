"""Manual positions determine the fade; old template plans remain reproducible."""
from copy import deepcopy
import unittest
import numpy as np
from backend.app.planning.vocal_preserving import propose_pair,plan_set,validate_plan
from backend.app.planning.manual_handoff import estimate
from backend.app.audio.vocal_automation import relative_gain
from backend.app.audio.beat_validation import audit_join
from tests.test_vocal_planner import fixture,active


class ManualHandoffTests(unittest.TestCase):
    def setUp(self):
        self.records=[fixture('manual-a',duration=240.),fixture('manual-b',duration=240.)]
        self.row={'incoming_at_outgoing':40.25,'outgoing_line_end':100.,'incoming_entry':50.7,'vocal_confirmed':True}

    def test_long_hold_and_exact_explicit_end_preserve_source_progression(self):
        row={**self.row,'outgoing_source_out':120.}
        result=plan_set(self.records,corrections={'0':row});self.assertEqual(result['status'],'planned')
        p=result['plan'];self.assertEqual(p['version'],'vocal-preserving-planner-2')
        self.assertAlmostEqual(p['sources'][0]['source_out'],120.)
        self.assertEqual(p['sources'][1]['source_in'],50.7)
        j=p['joins'][0];self.assertGreater(j['fade_start_seconds']-j['entry_seconds'],30.)
        self.assertGreaterEqual(j['fade_start_seconds'],102.-1e-8)
        t=np.linspace(j['entry_seconds'],101.999,1000)
        np.testing.assert_array_equal(relative_gain(p,0,t),np.ones(len(t)))
        self.assertLessEqual(float(relative_gain(p,1,t).max()),.25)
        validate_plan(p,self.records)

    def test_estimate_never_confirms_or_creates_eligible_candidates(self):
        row={**self.row,'vocal_confirmed':False}
        value=estimate(*self.records,row)
        self.assertEqual(value['status'],'estimated');self.assertTrue(value['confirmation_required'])
        self.assertNotIn('candidates',value);self.assertFalse(row['vocal_confirmed'])

    def test_first_end_must_leave_time_for_the_marked_vocal(self):
        row={**self.row,'outgoing_source_out':101.}
        value=estimate(*self.records,row)
        self.assertEqual(value['status'],'needs_input')
        self.assertEqual(value['review_items'][0]['code'],'finish_before_vocal_tail')
        self.assertEqual(row['outgoing_source_out'],101.)

    def test_vocal_mark_optional_when_observed_quiet_fade_exists(self):
        row={k:v for k,v in {**self.row,'outgoing_source_out':120.}.items() if k!='outgoing_line_end'}
        self.assertTrue(propose_pair(*self.records,correction=row)['candidates'])
        active(self.records[0],0,240)
        value=estimate(*self.records,row)
        self.assertEqual(value['review_items'][0]['code'],'vocal_end_required')

    def test_natural_final_ending_does_not_invent_vocal_completion(self):
        active(self.records[1],0,240)
        result=plan_set(self.records,corrections={'0':self.row})
        self.assertEqual(result['status'],'planned')
        p=result['plan'];self.assertEqual(p['sources'][-1]['source_out'],240.)
        self.assertEqual(p['sources'][-1]['ending_policy'],'natural_source_end')
        self.assertIsNone(p['listening_accepted']);validate_plan(p,self.records)

    def test_old_manual_template_plans_still_validate_with_their_own_policy(self):
        row={'outgoing_line_end':60.,'incoming_entry':.08,'vocal_confirmed':True}
        old=plan_set(self.records,corrections={'0':row},manual_mode=False)['plan']
        self.assertEqual(old['version'],'vocal-preserving-planner-1')
        validate_plan(old,self.records)
        new=plan_set(self.records,corrections={'0':row})['plan']
        self.assertEqual(new['version'],'vocal-preserving-planner-2')
        validate_plan(new,self.records);validate_plan(old,self.records)

    def test_candidate_tampering_cannot_modify_cached_source_anchors(self):
        before=propose_pair(*self.records,correction=self.row)['candidates'][0]
        identity=before['id'];before['evidence']['local_bar_anchors'][0]['source_cue']=999
        after=propose_pair(*self.records,correction=self.row)['candidates'][0]
        self.assertEqual(after['id'],identity)
        self.assertNotEqual(after['evidence']['local_bar_anchors'][0]['source_cue'],999)
        for r in self.records[0]['effective']['features']:r['rms']=0.
        self.assertFalse(propose_pair(*self.records,correction=self.row)['candidates'])

    def test_short_manual_phase_uses_whole_overlap_but_rejects_a_wrong_bar(self):
        beats=np.arange(0,40,.48).tolist();normal={'beats':beats,'downbeats':beats[::4]}
        strict=audit_join(normal,normal,[normal,normal],9.6,17.28,normal)
        self.assertEqual(strict['status'],'needs_review')
        manual=audit_join(normal,normal,[normal,normal],9.6,17.28,normal,manual=True)
        self.assertEqual(manual['status'],'validated')
        self.assertTrue(any(c.get('verification') for c in manual['checks']))
        wrong={'beats':beats,'downbeats':beats[1::4]}
        bad=audit_join(normal,wrong,[normal,wrong],9.6,17.28,normal,manual=True)
        self.assertEqual(bad['status'],'needs_review')


if __name__=='__main__':unittest.main()
