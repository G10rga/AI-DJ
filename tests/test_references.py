"""Reference matching must retain uncertainty and require explicit human review."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from scipy.io import wavfile
from backend.app.audio.probe import AudioInfo
from backend.app.audio.reference import correlation, spectral_features, suggest_matches, ordered_suggestions, STEP
from backend.app.config import Settings
from backend.app.references import ReferenceStore


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = Settings.from_env()
        from dataclasses import replace
        self.settings = replace(self.settings, data_root=self.root, min_free_bytes=0)
        self.store = ReferenceStore(self.settings)
        for name in ('mix.mp4', 'a.mp3', 'b.mp3'):
            (self.root/name).write_bytes(name.encode())
        self.manifest = self.root/'manifest.json'
        self.data = {'recording': 'mix.mp4', 'tracks': [
            {'title': 'First', 'sources': ['a.mp3']},
            {'title': 'Second', 'sources': ['b.mp3']},
            {'title': 'First again', 'sources': ['a.mp3']}]}

    def importing(self):
        self.manifest.write_text(json.dumps(self.data), encoding='utf-8')
        with patch('backend.app.references.probe', return_value=AudioInfo(3600, 44100, 2, 'test')):
            return self.store.import_manifest(self.manifest)

    def test_order_repeats_missing_sources_and_idempotent_import(self):
        self.data['tracks'][1]['sources'] = []
        imported = self.importing()
        self.assertEqual(imported['id'], self.importing()['id'])
        self.assertEqual([t['position'] for t in imported['import']['tracks']], [0, 1, 2])
        self.assertEqual(imported['import']['tracks'][0]['sources'], imported['import']['tracks'][2]['sources'])
        self.assertEqual(imported['import']['tracks'][1]['sources'], [])
        with patch.object(self.store, '_features', return_value=np.zeros((100, 32))):
            result = self.store.align(imported['id'])
        self.assertEqual(result['tracks'][1]['status'], 'missing_source')
        self.assertEqual(result['tracks'][0]['alternatives'][0]['hypotheses'], [])

    def test_missing_file_does_not_publish_partial_import(self):
        self.data['tracks'][2]['sources'] = ['absent.mp3']
        with self.assertRaises(FileNotFoundError):
            self.importing()
        with self.store.database.connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM reference_imports').fetchone()[0], 0)

    def test_changed_source_rejected_even_when_features_cached(self):
        source = self.importing()['import']['tracks'][0]['sources'][0]
        (self.root/'a.mp3').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.store._features(source)

    def review(self):
        imported = self.importing()
        payload = self.store.review_template(imported['id'])
        payload['reviewed'] = True
        for i, track in enumerate(payload['tracks']):
            track.update(source_hash=imported['import']['tracks'][i]['sources'][0]['content_hash'],
                         source_in=10, source_out=110, mix_in=i*80, mix_out=i*80+100)
        return imported['id'], payload

    def test_review_is_explicit_append_only_and_unknown_stays_unknown(self):
        identity, payload = self.review()
        bad = deepcopy(payload)
        bad['reviewed'] = False
        with self.assertRaises(ValueError):
            self.store.annotate(identity, bad)
        result = self.store.annotate(identity, payload)
        self.assertEqual(result['revision'], 1)
        self.assertIsNone(result['annotation']['transitions'][0]['recipe'])
        with self.assertRaisesRegex(ValueError, 'reload'):
            self.store.annotate(identity, payload)
        payload['expected_revision'] = 1
        self.store.annotate(identity, payload)
        with self.store.database.connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM reference_annotations').fetchone()[0], 2)

    def test_bad_intervals_order_and_unimported_identity_are_rejected(self):
        identity, payload = self.review()
        changes = [('mix_in', -1), ('source_out', 4000), ('source_in', float('nan')),
                   ('source_hash', 'not imported'), ('mix_out', 0), ('position', 9)]
        for key, value in changes:
            bad = deepcopy(payload)
            bad['tracks'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.store.annotate(identity, bad)
        self.assertEqual(self.store.get(identity)['revision'], 0)

    def test_matching_finds_tempo_changed_excerpt_without_timestamps(self):
        rng = np.random.default_rng(42)
        source = rng.normal(size=(240, 32)).astype(np.float32)
        scale = 1.05
        excerpt = source[40:200]
        warped = np.stack([np.interp(np.arange(168)/scale, np.arange(160), excerpt[:, b]) for b in range(32)], axis=1)
        recording = rng.normal(size=(800, 32)).astype(np.float32)
        recording[240:408] = warped
        results = suggest_matches(recording, source, scales=[1., 1.05])
        self.assertTrue(results)
        best = results[0]
        self.assertAlmostEqual(best['offset_seconds'], (240-40*scale)*STEP, delta=.5)
        self.assertEqual(best['status'], 'needs_review')
        self.assertGreaterEqual(best['supporting_windows'], 2)
        self.assertEqual(suggest_matches(recording, np.ones_like(source)), [])
        self.assertEqual(suggest_matches(recording, rng.normal(size=source.shape)), [])

    def test_normalized_correlation_rejects_static_audio_and_handles_gain(self):
        rng = np.random.default_rng(3)
        template = rng.normal(size=(40, 32))
        recording = rng.normal(size=(240, 32))
        recording[75:115] = template*2+4
        scores = correlation(recording, template)
        self.assertEqual(int(scores.argmax()), 75)
        self.assertAlmostEqual(scores[75], 1.)
        self.assertTrue(np.isfinite(correlation(np.ones((100, 32)), template)).all())
        self.assertTrue(np.all(correlation(np.zeros((100, 32)), template) == 0))

    def test_ordered_proposals_do_not_reuse_an_earlier_occurrence(self):
        def candidate(time, score=.8, support=3):
            return {'supporting_windows': support, 'similarity': score,
                    'anchors': [{'mix_seconds': time, 'window_seconds': 16, 'scale': 1}]}
        tracks = [
            {'alternatives': [{'source_hash': 'repeated', 'hypotheses': [candidate(10), candidate(210)]}]},
            {'alternatives': [{'source_hash': 'middle', 'hypotheses': [candidate(110)]}]},
            {'alternatives': []},
            {'alternatives': [{'source_hash': 'repeated', 'hypotheses': [candidate(10), candidate(210)]}]},
            {'alternatives': [{'source_hash': 'weak', 'hypotheses': [candidate(300, support=1)]}]}]
        result = ordered_suggestions(tracks)
        self.assertEqual(result[0]['hypothesis_index'], 0)
        self.assertEqual(result[3]['hypothesis_index'], 1)
        self.assertIsNone(result[2])
        self.assertIsNone(result[4])
        # Short-window searches need more independent evidence.
        tracks[-1]['alternatives'][0]['hypotheses'][0].update(
            supporting_windows=3, minimum_supporting_windows=4)
        self.assertIsNone(ordered_suggestions(tracks)[-1])

    def test_transition_validation_does_not_create_annotations_on_failure(self):
        identity, payload = self.review()
        for change in ({'recipe': 'invented'}, {'mix_start': 50}, {'overlap_bars': -1},
                       {'mix_start': 500, 'mix_end': 550}, {'vocal_behavior': False},
                       {'mix_start': 120, 'mix_end': 140}):
            bad = deepcopy(payload)
            bad['transitions'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.store.annotate(identity, bad)
        self.assertEqual(self.store.get(identity)['revision'], 0)

    def test_refinement_preserves_parent_and_translates_local_anchors(self):
        identity = self.importing()['id']
        def hypothesis(start):
            return {'offset_seconds': start, 'scale': 1., 'supporting_windows': 2,
                    'similarity': .9, 'status': 'needs_review',
                    'anchors': [{'source_seconds': s, 'mix_seconds': start+s, 'window_seconds': 16,
                                 'scale': 1., 'similarity': .9, 'offset_seconds': start} for s in (0, 4)]}
        with patch.object(self.store, '_features', return_value=np.zeros((400, 32))), patch(
                'backend.app.references.suggest_matches', side_effect=[[hypothesis(0)], [], [hypothesis(80)]]):
            initial = self.store.align(identity)
        self.assertIsNone(initial['ordered_suggestions'][1])
        with patch.object(self.store, '_features', return_value=np.zeros((400, 32))), patch(
                'backend.app.references.suggest_matches', return_value=[hypothesis(20)]):
            refined = self.store.refine(identity)
        self.assertEqual(refined['parent_alignment_id'], initial['id'])
        self.assertIsNotNone(refined['ordered_suggestions'][1])
        local = refined['tracks'][1]['alternatives'][0]['hypotheses'][0]
        self.assertEqual(local['anchors'][0]['mix_seconds'], 30)
        reference = self.store.get(identity)
        self.assertEqual(len(reference['alignments']), 2)
        self.assertEqual(reference['alignments'][0], initial)
        self.assertEqual(reference['revision'], 0)
        self.assertIn('not track start times', self.store.report(identity))
        self.assertNotIn('Unresolved', self.store.report(identity))

    def test_real_audio_crosses_decode_chunks_and_matches_excerpt(self):
        rate = 8000
        rng = np.random.default_rng(17)
        # Vary the spectral content over time; a steady beat alone cannot identify a song.
        blocks = []
        for i in range(200):
            time = np.arange(2000)/rate
            frequencies = rng.uniform(100, 3300, 4)
            blocks.append(.12*np.sin(2*np.pi*time[:, None]*frequencies).sum(axis=1))
        audio = np.concatenate(blocks).astype(np.float32)
        source = self.root/'source.wav'
        mix = self.root/'recording.wav'
        wavfile.write(source, rate, audio)
        wavfile.write(mix, rate, np.concatenate((rng.normal(0,.03,rate*8), audio[rate*10:rate*45], np.zeros(rate*5))).astype(np.float32))
        a = spectral_features(source, 50, self.settings, self.root)
        b = spectral_features(mix, 48, self.settings, self.root)
        self.assertEqual(len(a), 199)  # continuous feature grid across 40-second chunks
        result = suggest_matches(b, a, scales=[1.])
        self.assertTrue(result)
        self.assertAlmostEqual(result[0]['offset_seconds'], -2, delta=.5)


if __name__ == '__main__':
    unittest.main()
