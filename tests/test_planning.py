"""Learned planning invariants and real persistence; no copyrighted fixtures."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import importlib.util
from backend.app.config import Settings
from backend.app.db import Database
from backend.app.models import MixPlan
from backend.app.storage import Storage

AVAILABLE = all(importlib.util.find_spec(name) for name in ('numpy', 'sklearn', 'librosa'))
if AVAILABLE:
    import numpy as np
    from backend.app.planning.learning import fit_library
    from backend.app.planning.planner import build_plan, change_transition
    from scripts.plan_mix import collect_entries, persist_plan


def track(identity, family=0, bpm=120, duration=240, reliable=True):
    chroma = np.zeros(12)
    chroma[family % 12] = .7
    chroma[(family+7) % 12] += .3
    windows = [{'start': float(start), 'end': min(float(start+16), duration), 'bpm': bpm,
                'phase': .1, 'coverage': .95, 'error': .002, 'rms': .15}
               for start in range(0, int(duration), 16)] if reliable and bpm else []
    analysis = {'version': 'test', 'config': 'test-config', 'content_hash': 'content-'+identity,
                'audio': {'duration': duration}, 'chroma': chroma.tolist(),
                'mfcc_mean': [0]+[float(family*5+i) for i in range(12)],
                'mfcc_std': [1]*13, 'spectral_summary': [2000+family*100, 100, .1],
                'energy': [.1+family*.02]*max(1, int(duration*5)), 'energy_frame_seconds': .2,
                'rhythm': {'version': 'test', 'bpm': bpm, 'reliable': reliable and bpm is not None,
                           'confidence': .95 if reliable and bpm else 0, 'valid_fraction': 1 if windows else 0,
                           'windows': windows}}
    return {'entry_id': identity, 'path': 'D:/fixtures/'+identity+'.wav', 'analysis': analysis}


@unittest.skipUnless(AVAILABLE, 'Install the audio and ML extras')
class PlanningTests(unittest.TestCase):
    def library(self):
        return [track(f'{family}-{copy}', family, 120+family) for family in range(3) for copy in range(2)]

    def test_fitted_embedding_distinguishes_timbre_and_records_real_model(self):
        entries = self.library()
        learned = fit_library(entries)
        self.assertIsNotNone(learned['model']['pca'])
        self.assertIsNotNone(learned['model']['pair_model'])
        self.assertEqual(learned['model']['training_samples'], 6)
        near = np.linalg.norm(learned['embedding'][0]-learned['embedding'][1])
        far = np.linalg.norm(learned['embedding'][0]-learned['embedding'][4])
        self.assertLess(near, far)
        json.dumps(learned['model'], allow_nan=False)

    def test_deterministic_plan_and_model_under_input_permutation(self):
        entries = self.library()
        first, details = build_plan(entries, 'mix')
        second, _ = build_plan(list(reversed(entries)), 'mix')
        self.assertEqual(first, second)
        self.assertEqual(details['method'], 'ml')
        self.assertEqual(MixPlan.from_json(first.to_json()), first)

    def test_duplicate_audio_is_retained_but_not_reweighted_in_training(self):
        entries = self.library()
        duplicate = deepcopy(entries[0])
        duplicate['entry_id'] = 'duplicate-upload'
        entries.append(duplicate)
        learned = fit_library(entries)
        self.assertEqual(learned['model']['training_samples'], 6)
        plan, _ = build_plan(entries, 'mix', learned=learned)
        self.assertEqual(len(plan.excerpts), 7)
        self.assertEqual({x.track_id for x in plan.excerpts}, {x['entry_id'] for x in entries})

    def test_single_and_degenerate_libraries_are_finite(self):
        single, _ = build_plan([track('one')], 'mix')
        self.assertEqual(len(single.excerpts), 1)
        self.assertFalse(single.transitions)
        entries = [track(str(i)) for i in range(5)]
        learned = fit_library(entries)
        self.assertIsNone(learned['model']['pca'])
        self.assertIsNone(learned['model']['pair_model'])
        plan, _ = build_plan(entries, 'mix', learned=learned)
        plan.validate()
        json.dumps(learned['model'], allow_nan=False)

    def test_unknown_features_and_tempo_outliers_stay_in_plan(self):
        entries = [track('house'), track('outlier', bpm=180), track('unknown', bpm=None, reliable=False)]
        for name in ('chroma', 'mfcc_mean', 'mfcc_std', 'spectral_summary'):
            entries[-1]['analysis'].pop(name)
        plan, _ = build_plan(entries, 'mix')
        self.assertEqual(len(plan.excerpts), 3)
        self.assertTrue(any(x.style == 'boundary_fade' for x in plan.transitions))
        for excerpt in plan.excerpts:
            self.assertLessEqual(abs(excerpt.target_bpm/excerpt.source_bpm-1), .0600001)

    def test_short_sources_and_overlaps_never_consume_excerpts(self):
        entries = [track(str(i), i % 3, bpm=120+i, duration=duration)
                   for i, duration in enumerate((3, 12, 35, 64, 120, 150, 240))]
        plan, _ = build_plan(entries, 'mix', requested_seconds=180)
        plan.validate()
        self.assertEqual(len(plan.excerpts), len(entries))
        for i, excerpt in enumerate(plan.excerpts):
            self.assertGreater(excerpt.source_out, excerpt.source_in)
            self.assertLessEqual(excerpt.source_out, excerpt.source_duration)
            overlaps = (plan.transitions[i-1].overlap_seconds if i else 0)+(plan.transitions[i].overlap_seconds if i < len(plan.transitions) else 0)
            self.assertLess(overlaps, excerpt.output_duration)

    def test_style_change_preserves_order_and_validates_geometry(self):
        plan, _ = build_plan(self.library(), 'mix')
        changed = change_transition(plan, 0, 'boundary_fade')
        self.assertEqual(changed.excerpts, plan.excerpts)
        self.assertEqual(changed.revision, 2)
        short, _ = build_plan([track('a', duration=20), track('b', duration=20)], 'short')
        with self.assertRaises(ValueError):
            change_transition(short, 0, 'smooth')

    def test_invalid_numeric_features_and_duplicate_entry_ids_rejected(self):
        entries = self.library()
        entries[0]['analysis']['mfcc_mean'][1] = float('nan')
        with self.assertRaises(ValueError):
            fit_library(entries)
        with self.assertRaises(ValueError):
            fit_library([track('same'), track('same')])
        with self.assertRaises(ValueError):
            build_plan([], 'empty')

    def test_plan_round_trips_sqlite_with_all_original_members(self):
        entries = self.library()
        plan, _ = build_plan(entries, 'persist')
        with tempfile.TemporaryDirectory() as root:
            settings = Settings(data_root=Path(root))
            persist_plan(entries, plan, settings)
            database = Database(settings.data_root/'app.sqlite3')
            self.assertEqual(database.load_plan('persist', 1), plan)
            with database.connection() as connection:
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM mix_tracks WHERE mix_id=?', ('persist',)).fetchone()[0], 6)

    def test_failed_input_does_not_produce_a_reduced_playlist(self):
        valid = track('good')
        with tempfile.TemporaryDirectory() as root:
            settings = Settings(data_root=Path(root))
            storage = Storage(settings.data_root)
            storage.initialize()
            with patch('scripts.plan_mix.analyze', side_effect=[valid['analysis'], ValueError('corrupt audio')]), \
                 patch('scripts.plan_mix.analyze_rhythm', return_value=valid['analysis']['rhythm']):
                with self.assertRaises(ValueError):
                    collect_entries([Path('good.mp3'), Path('bad.mp3')], settings, storage)
            reports = list((settings.data_root/'plans').glob('analysis-errors-*.json'))
            self.assertEqual(len(reports), 1)
            self.assertFalse(json.loads(reports[0].read_text())['plan_created'])

    def test_baseline_comparison_retains_same_membership(self):
        entries = self.library()
        learned = fit_library(entries)
        ml, _ = build_plan(entries, 'mix', learned=learned)
        baseline, details = build_plan(entries, 'mix', method='baseline', learned=learned)
        self.assertEqual({x.track_id for x in ml.excerpts}, {x.track_id for x in baseline.excerpts})
        self.assertEqual(details['method'], 'baseline')
