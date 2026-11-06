import json
from pathlib import Path
import tempfile
import unittest
from backend.app.planning.preferences import PreferenceStore


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.store=PreferenceStore(self.root/'feedback')
    def candidate(self,pair,fade):
        audio=self.root/f'{pair}-{fade}.mp3';audio.write_bytes(f'test-only-{pair}-{fade}'.encode())
        report={'output':str(audio),'tracks':[{'content_hash':f'{pair}-a','source_bpm':120,'source_in':30,'source_out':150},
                                            {'content_hash':f'{pair}-b','source_bpm':120,'source_in':30,'source_out':150}],
                'overlap_seconds':64,'target_bpm':120,'stems':True,
                'recipe':{'blend_profile':'long_groove','vocal_schedule':{'outgoing_fade_duration_seconds':fade,'incoming_fade_duration_seconds':fade,'vocal_eq':True}}}
        p=audio.with_suffix('.json');p.write_text(json.dumps(report));return self.store.register(p)
    def test_cold_start_has_no_fabricated_training(self):
        self.candidate('a',8)
        model=self.store.train();self.assertFalse(model['ready']);self.assertEqual(model['comparisons'],0)
        self.assertEqual(self.store.rank()['ranking'],[])
    def test_first_vote_learns_experimentally_without_auto_activation(self):
        a,b=self.candidate('first',8),self.candidate('first',16)
        model=self.store.feedback('prefer',b,a)
        self.assertFalse(model['ready']);self.assertTrue(model['weights'])
        ranked=self.store.rank();self.assertTrue(ranked['experimental']);self.assertEqual(ranked['ranking'][0]['id'],b)
        report=json.loads(self.store.candidates()[0]['report_json'])
        settings=self.store.settings(report,4,'standard');self.assertFalse(settings['ready']);self.assertEqual(settings['fade_bars'],4)
    def test_explicit_preferences_change_ranking_and_generalize_by_pair(self):
        groups=[]
        for pair in ('a','b','c'):
            ids=[self.candidate(pair,d) for d in (2,8,16)];groups.append(ids)
            self.store.feedback('prefer',ids[2],ids[1]);model=self.store.feedback('prefer',ids[1],ids[0])
        self.assertTrue(model['ready']);self.assertEqual(model['comparisons'],6)
        self.assertEqual(model['held_out_song_pair_accuracy'],1)
        key=next(r['pair_key'] for r in self.store.candidates() if r['id']==groups[0][0])
        ranking=self.store.rank(key)['ranking'];self.assertEqual(ranking[0]['id'],groups[0][2])
        self.assertEqual(PreferenceStore(self.root/'feedback').train()['weights'],model['weights'])
    def test_duplicate_votes_do_not_inflate_dataset_and_reversal_replaces_vote(self):
        a,b=self.candidate('a',8),self.candidate('a',16)
        for _ in range(4):self.store.feedback('prefer',a,b)
        self.assertEqual(len(self.store.comparisons()),1)
        self.store.feedback('prefer',b,a)
        self.assertEqual(self.store.comparisons()[0][2:],(b,a))
    def test_invalid_cross_pair_feedback_rejected(self):
        a,b=self.candidate('a',8),self.candidate('b',16)
        for args in [('prefer',a,a),('prefer',a,b),('rate',a,None,6),('rate',a,None,float('nan'))]:
            with self.assertRaises(ValueError):self.store.feedback(*args)
    def test_ratings_generate_only_within_pair_comparisons(self):
        a,b,c=self.candidate('a',8),self.candidate('a',16),self.candidate('b',16)
        for identity,rating in [(a,2),(b,5),(c,5)]:self.store.feedback('rate',identity,value=rating)
        self.assertEqual(len(self.store.comparisons()),1)
