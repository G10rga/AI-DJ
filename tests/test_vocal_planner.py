"""Hard musical constraints, bounded proposals and continuous set geometry."""
from copy import deepcopy
import math
import unittest

import numpy as np

from backend.app.audio.analysis_evidence import interval_activity
from backend.app.audio.beat_validation import audit_join, window_alignment
from backend.app.audio.vocal_automation import relative_gain
from backend.app.planning.vocal_preserving import propose_pair, plan_set, validate_plan, digest


def fixture(identity, duration=160., bpm=125., source_hash=None):
    beats = (.08+np.arange(math.ceil(duration*bpm/60))*60/bpm)
    beats = beats[beats < duration].tolist()
    layer = lambda times: {'times': times, 'confidence': None, 'provenance': 'synthetic observed markers'}
    model = {'sha256': 'fixture-model'}
    rows = [{'start': float(t), 'end': float(min(duration, t+.5)), 'rms':.001, 'master_rms':.1,
             'vocal_ratio':.01, 'state':'observed', 'active':False, 'chunk_index':0}
            for t in np.arange(0, duration, .5)]
    data = {'version':'musical-timeline-1', 'content_hash':source_hash or identity, 'duration_seconds':duration,
        'beats':layer(beats), 'downbeats':layer(beats[::4]), 'phrase_boundaries':layer(beats[::32]),
        'features':[{'start':float(t), 'end':min(duration,t+1), 'rms':.1, 'peak':.5, 'bass_rms':.05,
            'transient_peaks_per_second':2., 'chroma':[1.]+[0.]*11} for t in np.arange(0,duration)],
        'embeddings':[], 'sections':[], 'vocal_activity':rows, 'vocal_status':{'available':True},
        'config':{'analysis_profile':'transition-foundation-1', 'separator':model},
        'analysis_evidence':{'version':'transition-evidence-1'}, 'vocal_chunks':[{'index':0,
            'original_sha256':source_hash or identity, 'core_interval':[0.,duration], 'context_source_interval':[0.,duration],
            'context_sha256':'fixture-context', 'stem_sha256':{'vocals':'fixture-vocals'}, 'configuration':{'model':model}}]}
    return {'track_id':identity, 'timeline_id':'timeline-'+identity, 'revision':0, 'prediction':deepcopy(data), 'effective':data}


def active(record, start, end):
    for row in record['effective']['vocal_activity']:
        if row['start'] < end and row['end'] > start:
            row.update(rms=.05, vocal_ratio=.5, active=True)


class VocalPlannerTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = fixture('a'), fixture('b')

    def test_two_recipes_eight_bar_default_bounded_immutable_and_sixteen_requires_context(self):
        before = deepcopy((self.a, self.b))
        result = propose_pair(self.a, self.b)
        self.assertLessEqual(len(result['candidates']), 12)
        self.assertEqual({c['recipe'] for c in result['candidates']}, {'plain_crossfade','protected_vocal'})
        self.assertEqual(result['candidates'][0]['bars'], 8)
        self.assertEqual((self.a, self.b), before)
        long = propose_pair(self.a, self.b, prediction={'overlap_seconds':30.72})
        self.assertTrue(long['candidates'])
        self.assertTrue(all(c['bars'] == 16 for c in long['candidates']))
        short = fixture('short', duration=25.)
        self.assertFalse(propose_pair(short, self.b, prediction={'overlap_seconds':30.72})['candidates'])

    def test_outgoing_line_and_guard_are_protected_even_with_quiet_future_bar(self):
        active(self.a, 40, 70)
        result = propose_pair(self.a, self.b)
        self.assertTrue(result['candidates'])
        for candidate in result['candidates']:
            cue = candidate['source_cues'][0]; ratio = candidate['source_ratios'][0]
            start = cue+candidate['fade_start_local_seconds']*ratio-2
            end = cue+candidate['overlap_seconds']*ratio
            self.assertEqual(interval_activity(self.a['effective']['vocal_activity'], start, end)['status'], 'quieter_candidate')
            self.assertTrue(end <= 40 or start >= 70)

    def test_incoming_entire_overlap_and_missing_coverage_fail_closed(self):
        active(self.b, 4, 160)
        result = propose_pair(self.a, self.b)
        self.assertEqual(result['candidates'], [])
        self.assertTrue(result['review_items'])
        b = fixture('gapped')
        b['effective']['vocal_activity'] = [row for row in b['effective']['vocal_activity'] if int(row['start'])%4]
        self.assertEqual(propose_pair(self.a,b)['candidates'], [])
        legacy = fixture('legacy'); legacy['effective']['config'] = {}
        self.assertEqual(propose_pair(self.a, legacy)['candidates'], [])

    def test_optional_model_never_bypasses_constraints_or_substitutes_recipe(self):
        unsupported = propose_pair(self.a,self.b,prediction={'recipe':'loop_filter_delay'})
        self.assertEqual(unsupported['candidates'], [])
        self.assertEqual(unsupported['review_items'][0]['code'], 'model_recipe_unsupported')
        hint = {'recipe':'protected_vocal','outgoing_source_in':62.,'incoming_source_in':4.,'overlap_seconds':15.36}
        result = propose_pair(self.a,self.b,prediction=hint)
        self.assertTrue(result['candidates'])
        for c in result['candidates']:
            self.assertEqual(c['requested']['prediction'],hint)
            self.assertEqual(c['recipe'],'protected_vocal')
            self.assertLessEqual(abs(c['source_cues'][0]-62),32)
        active(self.b,0,160)
        self.assertFalse(propose_pair(self.a,self.b,prediction=hint)['candidates'])

    def test_three_song_plan_preserves_middle_source_progression_and_gain_plateau(self):
        records = [fixture('a',bpm=124), fixture('b',bpm=125), fixture('c',bpm=126)]
        result = plan_set(records)
        self.assertEqual(result['status'],'planned')
        plan = result['plan']; validate_plan(plan,records)
        middle = plan['sources'][1]; incoming,outgoing = plan['joins']
        self.assertEqual(middle['source_in'],incoming['candidate']['source_cues'][1])
        self.assertEqual(middle['source_out'],outgoing['candidate']['source_cues'][0]+outgoing['candidate']['overlap_seconds']*outgoing['candidate']['source_ratios'][0])
        self.assertGreater(outgoing['entry_seconds'],incoming['end_seconds'])
        times = np.linspace(incoming['end_seconds'],outgoing['fade_start_seconds'],1000)
        self.assertTrue(np.all(relative_gain(plan,1,times)==1))
        self.assertEqual([s['entry_id'] for s in plan['sources']],['entry-0','entry-1','entry-2'])

    def test_protected_sample_envelopes_have_gradual_entrance_and_continuous_boundaries(self):
        result = plan_set([self.a,self.b], predictions=[{'recipe':'protected_vocal'}])
        self.assertEqual(result['status'],'planned')
        plan = result['plan']; join = plan['joins'][0]
        times = np.arange(round(plan['duration_seconds']*44100))/44100
        out,inc = relative_gain(plan,0,times), relative_gain(plan,1,times)
        self.assertTrue(np.all(out[times <= join['fade_start_seconds']]==1))
        self.assertLess(float(inc[times < join['fade_start_seconds']].max()),.251)
        self.assertLess(float(np.abs(np.diff(out)).max()),1e-4)
        self.assertLess(float(np.abs(np.diff(inc)).max()),1e-4)
        self.assertGreater(join['fade_start_seconds']-join['entry_seconds'],7.)

    def test_selected_candidate_is_pinned_and_stale_or_unsafe_selection_never_falls_back(self):
        result = plan_set([self.a,self.b])
        identity = result['plan']['joins'][0]['candidate']['id']
        pinned = plan_set([self.a,self.b],selected_ids=[identity])
        self.assertEqual(pinned['plan']['joins'][0]['candidate']['id'],identity)
        self.assertEqual(plan_set([self.a,self.b],selected_ids=['stale'])['status'],'needs_review')
        active(self.b,0,160)
        self.assertEqual(plan_set([self.a,self.b],selected_ids=[identity])['status'],'needs_review')

    def test_conflicting_middle_joins_request_review_instead_of_source_skip(self):
        records = [self.a,self.b,fixture('c')]
        hints = [{'recipe':'protected_vocal','incoming_source_in':110.},
                 {'recipe':'protected_vocal','outgoing_source_in':20.}]
        result = plan_set(records,predictions=hints)
        self.assertEqual(result['status'],'needs_review')
        self.assertIsNone(result['plan'])

    def test_tampered_plan_or_evidence_revision_is_rejected(self):
        result = plan_set([self.a,self.b]); plan = result['plan']
        changed = deepcopy(plan); changed['sources'][1]['source_in'] += 1
        changed['id'] = digest({k:v for k,v in changed.items() if k!='id'})
        with self.assertRaises(ValueError): validate_plan(changed,[self.a,self.b])
        changed = deepcopy(self.b); changed['revision'] += 1
        with self.assertRaisesRegex(ValueError,'revision'): validate_plan(plan,[self.a,changed])

    def test_independent_local_checks_detect_late_slip_bar_phase_and_shared_wrong_grid(self):
        beats = np.arange(0,40,.48).tolist()
        original = {'beats':beats,'downbeats':beats[::4]}
        aligned = audit_join(original,original,[original,original],4,4+15.36,original)
        self.assertEqual(aligned['status'],'validated')
        wrong = {'beats':beats,'downbeats':beats[1::4]}
        self.assertEqual(audit_join(original,wrong,[original,original],4,19.36,original)['status'],'needs_review')
        drift = {'beats':[t+(.1 if t>12 else 0) for t in beats], 'downbeats':original['downbeats']}
        self.assertEqual(audit_join(original,drift,[original,original],4,19.36,original)['status'],'needs_review')
        half = {'beats':beats[::2],'downbeats':beats[::8]}
        self.assertEqual(audit_join(half,half,[original,original],4,19.36,half)['status'],'needs_review')

    def test_local_window_edges_keep_real_matches_without_hiding_missing_markers(self):
        a = np.arange(0,40,1.92)
        b = a+.02
        left = float(a[4]+.01); right = float(a[8]+.01)
        match = window_alignment(a.tolist(),b.tolist(),left,right,.07)
        self.assertEqual(match['status'],'aligned')
        missing = np.delete(b,[5,6]).tolist()
        self.assertNotEqual(window_alignment(a.tolist(),missing,left,right,.07)['status'],'aligned')


if __name__=='__main__': unittest.main()
