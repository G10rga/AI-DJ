"""Listening batch definitions stay frozen and never manufacture acceptance."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.app.config import Settings
from backend.app.workflow import Workflow
from backend.app.transition_review import pipeline
from backend.app.transition_review import capture
from backend.app.timelines import TimelineStore
from backend.app.planning.vocal_preserving import plan_set, propose_pair
from scripts.listening_acceptance import PAIRS, freeze, inspect
from scripts.setup_timeline import sha256
from tests.test_vocal_planner import fixture


class ListeningAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Workflow(Settings(data_root=self.root, min_free_bytes=0))
        reference = self.root/'experiments/open-dj/auditions/vocal-handoff-fdc44c762ab34ca8990521d1b53addc0'
        reference.mkdir(parents=True)
        for name in ('handoff.mp3', 'report.json'):
            (reference/name).write_bytes(b'isolated regression fixture')
        catalog = []
        for i, identity in enumerate([v for p in PAIRS for v in p[1:]]):
            path = self.root/f'original-{i}.mp3'; path.write_bytes(f'isolated original {i}'.encode())
            catalog.append({'id': identity, 'name': path.name, 'path': str(path), 'content_hash': sha256(path)})
        self.catalog = patch.object(self.store, 'catalog', return_value=catalog)
        self.catalog.start(); self.addCleanup(self.catalog.stop)

    def test_freeze_and_inspect_preserve_definition_and_no_votes_or_default(self):
        root = freeze(self.store)
        manifest_hash = sha256(root/'manifest.json')
        manifest = json.loads((root/'manifest.json').read_text())
        jobs = json.loads((root/'jobs.json').read_text())
        self.assertEqual(len(jobs['pairs']), 5)
        self.assertEqual(len(manifest['set_sources']), 5)
        self.assertEqual(manifest['owner_acceptance'], None)
        for item in manifest['regression']['files']:
            self.assertEqual(sha256(Path(item['retained'])), item['sha256'])
        owner = 'isolated-listening-test'
        job = self.store.claim(owner)
        self.store.finish(job['id'], owner, 'succeeded', {'status': 'needs_review', 'review_items': [{'code': 'uncertain'}]})
        report = inspect(self.store, root)
        self.assertEqual(report['jobs'][0]['status'], 'needs_review')
        self.assertEqual(report['jobs'][0]['review_items'][0]['code'], 'uncertain')
        self.assertIsNone(report['owner_acceptance'])
        self.assertEqual(sha256(root/'manifest.json'), manifest_hash)
        self.assertEqual(pipeline(self.store), 'legacy-v1')
        with self.store.db.connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM improved_listening_reviews').fetchone()[0], 0)
        with self.assertRaisesRegex(ValueError, 'already used'):
            freeze(self.store)

    def test_inspect_rejects_changed_frozen_definition(self):
        root = freeze(self.store)
        with (root/'manifest.json').open('a') as f:
            f.write(' ')
        with self.assertRaisesRegex(ValueError, 'definition changed'):
            inspect(self.store, root)

    def test_completed_comparison_requires_both_recipes_matched_level_and_intact_audio(self):
        root = freeze(self.store)
        owner = 'isolated-comparison-owner'; job = self.store.claim(owner)
        records = []; timelines = TimelineStore(self.root)
        for source in job['payload']['sources']:
            data = fixture(source['id'], source_hash=source['content_hash'])['effective']
            keys = timelines.save(source['path'], data, data['config'])
            records.append(timelines.get(**keys))
        capture(self.store, job, owner, records)
        reports = []
        candidates = propose_pair(*records)['candidates']
        for i, recipe in enumerate(('plain_crossfade', 'protected_vocal')):
            candidate = next(c for c in candidates if c['recipe'] == recipe)
            plan = plan_set(records, selected_ids=[candidate['id']])['plan']
            self.assertIsNotNone(plan)
            path = self.root/'renders'/f'isolated-comparison-{i}.mp3'
            path.write_bytes(f'isolated validated media fixture {i}'.encode())
            reports.append({'status': 'validated', 'pipeline': 'improved-transitions-1',
                'output': str(path), 'audio_sha256': sha256(path), 'plan': plan,
                'preparations': [{'gain_db': -3.} for _ in records], 'post_mix_gain_db': -3.,
                'loudness': {'integrated_lufs': -20.+i*.2, 'true_peak_dbfs': -3.},
                'duration_seconds': plan['duration_seconds']})
        self.store.finish(job['id'], owner, 'succeeded', {'status': 'validated', 'alternatives': reports})
        result = inspect(self.store, root)['jobs'][0]
        self.assertTrue(result['baseline_comparison_available'])
        self.assertAlmostEqual(result['level_difference_lu'], .2)
        self.assertIsNone(result['owner_feedback']['choice'])
        Path(reports[0]['output']).write_bytes(b'changed artifact')
        with self.assertRaisesRegex(ValueError, 'Saved audio changed'):
            inspect(self.store, root)


if __name__ == '__main__':
    unittest.main()
