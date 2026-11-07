"""Musical timeline contracts, append-only corrections and local editor API."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from fastapi.testclient import TestClient
from backend.app.audio.timeline_features import chunk_windows, merge_markers, feature_bins, section_candidates
from backend.app.config import Settings
from backend.app.db import Database
from backend.app.timelines import TimelineStore, VERSION, identity, validate_timeline
from backend.app.web import create_app
from scripts.setup_timeline import sha256


def prediction(content_hash):
    layer = lambda times: {'times': times, 'confidence': None, 'provenance': 'test fixture'}
    return {'version': VERSION, 'content_hash': content_hash, 'duration_seconds': 8,
            'beats': layer([i*.5 for i in range(16)]), 'downbeats': layer([0., 2., 4., 6.]),
            'phrase_boundaries': layer([0.]), 'features': [], 'embeddings': [],
            'vocal_activity': [], 'vocal_status': {'available': False}, 'sections': []}


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'track.wav'
        self.source.write_bytes(b'audio fixture')
        self.store = TimelineStore(self.root)
        self.config = {'model': 'frozen-test-v1', 'chunk_seconds': 30}
        self.prediction = prediction(sha256(self.source))
        self.keys = self.store.save(self.source, self.prediction, self.config)

    def get(self):
        return self.store.get(**self.keys)

    def test_cache_identity_includes_source_config_and_model(self):
        self.assertEqual(self.store.find(self.prediction['content_hash'], self.config), self.prediction)
        self.assertIsNone(self.store.find('changed source', self.config))
        self.assertIsNone(self.store.find(self.prediction['content_hash'], dict(self.config, model='new')))
        changed = deepcopy(self.prediction)
        changed['beats']['times'] = changed['beats']['times'][:-1]
        with self.assertRaisesRegex(ValueError, 'Cannot change a cached prediction'):
            self.store.save(self.source, changed, self.config)
        self.assertEqual(self.get()['prediction'], self.prediction)

    def test_manual_corrections_override_without_replacing_estimates(self):
        changes = {'downbeats': [.5, 2.5, 4.5, 6.5], 'phrase_boundaries': [.5]}
        corrected = self.store.correct(**self.keys, expected_revision=0, changes=changes, note='First bar begins later')
        self.assertEqual(corrected['revision'], 1)
        self.assertEqual(corrected['prediction'], self.prediction)
        self.assertEqual(corrected['effective']['downbeats']['times'], changes['downbeats'])
        self.assertEqual(corrected['effective']['downbeats']['provenance']['method'], 'human correction')
        self.assertEqual(corrected['effective']['bars'][0]['beat_count'], 4)
        with self.assertRaisesRegex(ValueError, 'reload'):
            self.store.correct(**self.keys, expected_revision=0, changes=changes)
        self.store.correct(**self.keys, expected_revision=1, changes={'downbeats': self.prediction['downbeats']['times']})
        self.assertEqual(self.get()['revision'], 2)

    def test_bad_corrections_never_append_a_revision(self):
        for changes in ({'downbeats': [-1.]}, {'beats': [2., 1.]}, {'beats': [float('nan')]},
                        {'downbeats': [.2]}, {'phrase_boundaries': [8.]}, {'beats': [True]},
                        {'phrase_boundaries': [1., 1.001]}, {'unexpected': []}, {}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.store.correct(**self.keys, expected_revision=0, changes=changes)
        self.assertEqual(self.get()['revision'], 0)

    def test_embedding_dimensions_and_interval_bounds(self):
        for embedding in ({'start': 0, 'end': 5, 'vector': [0]*767},
                          {'start': 0, 'end': 9, 'vector': [0]*768}):
            changed = deepcopy(self.prediction)
            changed['embeddings'] = [embedding]
            with self.assertRaises(ValueError):
                validate_timeline(changed)

    def test_migration_preserves_previous_plan_tables(self):
        with self.store.database.connection() as c:
            c.execute("INSERT INTO mixes(id) VALUES ('existing')")
            c.execute('PRAGMA user_version=2')
        Database(self.root/'app.sqlite3').initialize()
        with self.store.database.connection() as c:
            self.assertEqual(c.execute('SELECT id FROM mixes').fetchone()[0], 'existing')
        self.assertEqual(self.get()['prediction'], self.prediction)

    def test_new_analysis_versions_do_not_duplicate_library_rows(self):
        other = deepcopy(self.prediction)
        other['phrase_boundaries']['times'] = [.5]
        new_keys = self.store.save(self.source, other, dict(self.config, model='new'))
        rows = self.store.tracks()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['timeline_id'], new_keys['timeline_id'])
        self.assertEqual(self.get()['prediction'], self.prediction)

    def test_changed_source_cannot_be_bound_to_cached_timeline(self):
        self.source.write_bytes(b'changed source')
        with self.assertRaisesRegex(ValueError, 'Source changed'):
            self.store.save(self.source, self.prediction, self.config)

    def test_editor_api_ids_origin_conflicts_and_audio_range(self):
        client = TestClient(create_app(Settings(data_root=self.root)), base_url='http://127.0.0.1')
        path = f'/api/v1/tracks/{self.keys["track_id"]}/timelines/{self.keys["timeline_id"]}'
        self.assertEqual(client.get('/').status_code, 200)
        self.assertEqual(len(client.get('/api/v1/tracks').json()['tracks']), 1)
        self.assertEqual(client.get(path).json()['revision'], 0)
        payload = {'expected_revision': 0, 'changes': {'phrase_boundaries': [.5]}, 'note': 'heard a phrase'}
        self.assertEqual(client.post(path+'/corrections', json=payload, headers={'Origin': 'http://foreign.invalid'}).status_code, 403)
        self.assertEqual(client.post(path+'/corrections', json=payload).status_code, 200)
        self.assertEqual(client.post(path+'/corrections', json=payload).status_code, 409)
        audio_path = f'/api/v1/tracks/{self.keys["track_id"]}/audio'
        response = client.get(audio_path, headers={'Range': 'bytes=0-3'})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, b'audi')
        self.source.write_bytes(b'changed')
        self.assertEqual(client.get(audio_path).status_code, 409)
        self.assertEqual(client.get('/api/v1/tracks/missing/audio').status_code, 404)


class FeatureTests(unittest.TestCase):
    def test_chunk_cores_cover_source_once_with_context(self):
        windows = list(chunk_windows(61))
        self.assertEqual(windows, [(0., 30., 0., 34.), (30., 60., 26., 61), (60., 61, 56., 61)])
        self.assertEqual(sum(end-start for start, end, _, _ in windows), 61)
        self.assertEqual(merge_markers([[.5, 1.], [1.04, 1.5]]), [.5, 1., 1.5])

    def test_dsp_energy_bass_and_silence_are_finite(self):
        rate = 24000
        tone = .1*np.sin(2*np.pi*80*np.arange(rate*2)/rate)
        rows = feature_bins(tone, rate, 30.)
        self.assertEqual([(r['start'],r['end']) for r in rows], [(30.,31.),(31.,32.)])
        self.assertGreater(rows[1]['bass_rms'], .06)
        self.assertAlmostEqual(sum(rows[0]['chroma']), 1)
        silence = feature_bins(np.zeros(rate), rate, 0)[0]
        self.assertEqual(silence['rms'], 0)
        self.assertEqual(sum(silence['chroma']), 0)

    def test_section_changes_require_embedding_evidence(self):
        self.assertEqual(section_candidates([], [], []), [])
        embeddings = [{'start': i*5.,'end':(i+1)*5.,'vector':[1.,0.] if i<3 else [0.,1.]} for i in range(6)]
        sections = section_candidates(embeddings, [], [0., 8., 16., 24.])
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]['time'], 16.)
        self.assertEqual(sections[0]['label'], 'section-change candidate')


if __name__ == '__main__':
    unittest.main()
