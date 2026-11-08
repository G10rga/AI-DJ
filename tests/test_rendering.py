"""Persistence failure cases and shared rendering with real generated audio."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import soundfile as sf
from backend.app.config import Settings
from backend.app.db import Database
from backend.app.models import Excerpt, MixPlan, Transition
from backend.app.storage import Storage
from backend.app.audio.mdx import sha256_file
from backend.app.audio.probe import probe, run_audio, AudioError
from backend.app.rendering import render_set
from backend.app.library import discover, collect_entries
from scripts.synthetic_audio import write_fixture


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = Database(self.root/'app.sqlite3')
        self.db.initialize()
        self.entries = [{'entry_id': x, 'path': str(self.root/(x+'.wav')),
                         'analysis': {'content_hash': x}} for x in ('a', 'b')]
        self.plan = MixPlan('mix', 1, tuple(Excerpt(x, 0, 24, 24, 120, 120) for x in ('a', 'b')),
                            (Transition('eq_cut', 16, 8),))

    def test_atomic_registration_rolls_back_identity_conflicts(self):
        self.db.register_plan(self.entries, self.plan)
        conflicting = [dict(e, analysis={'content_hash': 'changed'}) for e in self.entries]
        with self.assertRaises(ValueError):
            self.db.register_plan(conflicting, replace(self.plan, mix_id='other'))
        with self.db.connection() as c:
            self.assertIsNone(c.execute("SELECT id FROM mixes WHERE id='other'").fetchone())
        self.assertEqual(self.db.load_plan('mix', 1), self.plan)

    def test_failure_retry_stale_completion_and_immutable_attempts(self):
        self.db.register_plan(self.entries, self.plan)
        first = self.db.begin_render(self.plan, {'model': 'baseline-v1'})
        self.assertTrue(self.db.finish_render(first, 'one.mp3', {'valid': True}))
        second_plan = replace(self.plan, revision=2)
        self.db.save_plan(second_plan)
        stale = self.db.begin_render(second_plan, {'model': 'baseline-v1'})
        self.db.save_plan(replace(self.plan, revision=3))
        self.assertFalse(self.db.finish_render(stale, 'stale.mp3', {'valid': True}))
        current_plan = self.db.load_plan('mix', 3)
        failed = self.db.begin_render(current_plan, {})
        self.db.fail_render(failed, 'separator failed')
        with self.db.connection() as c:
            self.assertEqual(c.execute('SELECT playable_revision FROM mixes').fetchone()[0], 1)
            saved = json.loads(c.execute('SELECT snapshot_json FROM render_attempts WHERE id=?', (first,)).fetchone()[0])
            self.assertEqual(saved['provenance']['model'], 'baseline-v1')
        retry = self.db.begin_render(current_plan, {})
        self.assertTrue(self.db.finish_render(retry, 'three.mp3', {'valid': True}))
        for identity in (first, stale, failed, retry):
            with self.assertRaises(ValueError):
                self.db.fail_render(identity, 'cannot change a finished attempt')
        with self.assertRaises(ValueError):
            self.db.begin_render(replace(current_plan, transitions=(Transition('boundary_fade', .25, 0),)), {})

    def test_additive_migration_retains_old_records(self):
        self.db.register_plan(self.entries, self.plan)
        with self.db.connection() as c:
            c.execute('DROP TABLE render_attempts')
            c.execute('PRAGMA user_version=1')
        self.db.initialize()
        self.assertEqual(self.db.load_plan('mix', 1), self.plan)
        with self.db.connection() as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0], 7)


class SharedRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = Settings.from_env()
        try:
            run_audio([cls.settings.ffmpeg, '-version'], timeout=15)
        except AudioError as exc:
            raise unittest.SkipTest(str(exc))

    def setUp(self):
        parent = self.settings.data_root/'tmp'
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent, prefix='test-shared-render-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = replace(self.settings, data_root=self.root, min_free_bytes=0)
        self.storage = Storage(self.root)
        self.storage.initialize()
        self.source = self.root/'source.wav'
        write_fixture(self.source)

    def setup_plan(self, count, boundary=False):
        entries = [{'entry_id': str(i), 'path': str(self.source),
                    'analysis': {'content_hash': sha256_file(self.source)}} for i in range(count)]
        plan = MixPlan('mix', 1, tuple(Excerpt(str(i), 0, 24, 24, 120, 120) for i in range(count)),
                       tuple(Transition('boundary_fade', .25, 0) if boundary else Transition('eq_cut', 16, 8)
                             for _ in range(count-1)))
        db = Database(self.root/'app.sqlite3')
        db.initialize()
        db.register_plan(entries, plan)
        return entries, plan, db

    @staticmethod
    def fake_separator(path, pointer, settings, storage):
        # Actual audio/FFmpeg rendering runs; only model inference is substituted.
        audio, rate = sf.read(path, dtype='float32', always_2d=True)
        vocals = path.with_name(path.stem+'-vocals.wav')
        sf.write(vocals, np.zeros_like(audio), rate, subtype='FLOAT')
        return {'instrumental': str(path), 'vocals': str(vocals)}

    def test_single_entry_real_encode_and_publication(self):
        entries, plan, db = self.setup_plan(1)
        report = render_set(entries, plan, {}, self.settings, self.storage, separate=self.fake_separator)
        self.assertTrue(report['published'])
        self.assertAlmostEqual(probe(Path(report['output']), self.settings).duration, 24, delta=.15)
        self.assertEqual(report['applied_plan'], json.loads(plan.to_json()))

    def test_three_duplicate_sources_boundary_joins_and_stereo_tail(self):
        entries, plan, db = self.setup_plan(3, boundary=True)
        with patch('backend.app.rendering.pulse_grid', side_effect=AssertionError('Boundary joins must not be beatmatched')):
            report = render_set(entries, plan, {}, self.settings, self.storage, separate=self.fake_separator)
        self.assertEqual([t['entry_id'] for t in report['tracks']], ['0', '1', '2'])
        self.assertAlmostEqual(report['duration'], 71.5, delta=.15)
        self.assertTrue(all(join['bars']==0 for join in report['joins']))
        self.assertGreater(report['energy_rms_2s'][-2], .01)
        self.assertEqual(probe(Path(report['output']), self.settings).channels, 2)

    def test_two_sources_beatmatched_and_checked_after_separation(self):
        entries, plan, db = self.setup_plan(2)
        report = render_set(entries, plan, {}, self.settings, self.storage, separate=self.fake_separator)
        self.assertEqual(report['joins'][0]['bars'], 8)
        self.assertTrue(report['joins'][0]['instrumental_checks'])
        self.assertAlmostEqual(report['duration'], 32, delta=.15)

    def test_selected_model_recipe_does_not_silently_fallback(self):
        entries,plan,db=self.setup_plan(2)
        with patch('backend.app.rendering.pulse_grid',side_effect=ValueError('bad phase')):
            with self.assertRaisesRegex(ValueError,'not silently replaced'):
                render_set(entries,plan,{'strict_join_settings':True},self.settings,self.storage,separate=self.fake_separator)
        with db.connection() as c:
            self.assertIsNone(c.execute("SELECT playable_revision FROM mixes WHERE id='mix'").fetchone()[0])

    def test_cancelled_workflow_cannot_publish_over_previous_audio(self):
        entries,plan,db=self.setup_plan(1)
        old=render_set(entries,plan,{},self.settings,self.storage,separate=self.fake_separator)
        changed=replace(plan,revision=2);db.save_plan(changed)
        with self.assertRaisesRegex(RuntimeError,'not published'):
            render_set(entries,changed,{},self.settings,self.storage,separate=self.fake_separator,publish_guard=lambda:False)
        with db.connection() as c:
            self.assertEqual(c.execute("SELECT playable_revision FROM mixes WHERE id='mix'").fetchone()[0],1)
        self.assertTrue(Path(old['output']).is_file())

    def test_separator_failure_preserves_playable_render(self):
        entries, plan, db = self.setup_plan(1)
        first = render_set(entries, plan, {}, self.settings, self.storage, separate=self.fake_separator)
        changed = replace(plan, revision=2)
        db.save_plan(changed)
        with self.assertRaisesRegex(RuntimeError, 'offline'):
            render_set(entries, changed, {}, self.settings, self.storage,
                       separate=lambda *args: (_ for _ in ()).throw(RuntimeError('offline')))
        with db.connection() as c:
            self.assertEqual(c.execute('SELECT playable_revision FROM mixes').fetchone()[0], 1)
            self.assertEqual(c.execute("SELECT count(*) FROM render_attempts WHERE status='failed'").fetchone()[0], 1)
        self.assertTrue(Path(first['output']).exists())

    def test_discovery_keeps_duplicates_and_reports_invalid_audio(self):
        self.assertEqual(discover([self.source, self.source]), [self.source, self.source])
        invalid = self.root/'invalid.wav'
        invalid.write_bytes(b'not audio')
        with self.assertRaisesRegex(ValueError, 'Input errors prevented plan creation'):
            collect_entries([invalid], self.settings, self.storage)
        errors = list((self.root/'plans').glob('analysis-errors-*.json'))
        self.assertEqual(len(errors), 1)

    def test_source_changes_reject_render_without_publishing(self):
        entries, plan, db = self.setup_plan(1)
        entries[0]['analysis']['content_hash'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'Source changed since analysis'):
            render_set(entries, plan, {}, self.settings, self.storage, separate=self.fake_separator)
        with db.connection() as c:
            self.assertIsNone(c.execute('SELECT playable_revision FROM mixes').fetchone()[0])

    def test_phase_correction_is_preserved_in_applied_snapshot(self):
        entries, plan, db = self.setup_plan(2)
        plan = replace(plan, revision=2, excerpts=(replace(plan.excerpts[0], source_out=20),
                       replace(plan.excerpts[1], source_in=.125, source_out=20.125)))
        db.save_plan(plan)
        report = render_set(entries, plan, {}, self.settings, self.storage, separate=self.fake_separator)
        self.assertEqual(report['joins'][0]['bars'], 8)
        actual = report['applied_plan']['excerpts'][1]
        correction = abs(actual['source_in']-.125) + report['pcm_delays_seconds'][1]
        self.assertGreater(correction, .01)
        self.assertEqual(report['plan']['excerpts'][1]['source_in'], .125)
        self.assertEqual(db.load_plan('mix', 2), plan)


if __name__ == '__main__':
    unittest.main()
