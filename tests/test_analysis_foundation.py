"""Coverage, immutable profile caches, correction pins and verified MDX artifacts."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import soundfile as sf

from backend.app.audio.analysis_evidence import (
    VERSION, vocal_bins, interval_activity, quieter_passages, build_evidence, foundation_evidence,
)
from backend.app.audio.mdx import sha256_file
from backend.app.audio.separation_cache import separate_verified
from backend.app.config import Settings
from backend.app.timeline_analysis import analyze_timeline, analyze_registered_pair, FOUNDATION_PROFILE
from backend.app.timelines import TimelineStore, VERSION as TIMELINE_VERSION


def prediction(digest, config):
    layer = lambda times: {'times': times, 'confidence': None, 'provenance': 'test observed markers'}
    data = {'version': TIMELINE_VERSION, 'content_hash': digest, 'duration_seconds': 12.,
        'beats': layer([i*.5 for i in range(24)]), 'downbeats': layer([float(i) for i in range(0, 12, 2)]),
        'phrase_boundaries': layer([0.]), 'features': [], 'embeddings': [], 'vocal_activity': [],
        'vocal_status': {'available': False}, 'sections': [], 'config': config}
    if config.get('analysis_profile') == FOUNDATION_PROFILE:
        master = np.ones((12000, 2), dtype=np.float32)*.2
        data['vocal_activity'] = vocal_bins(master*.05, master, 1000, 0, 0, 12, chunk_index=0)
        data['vocal_chunks'] = [{'index': 0, 'original_sha256': digest, 'core_interval': [0., 12.],
            'context_source_interval': [0., 12.], 'context_sha256': 'test-context',
            'stem_sha256': {'vocals': 'test-vocals'}, 'configuration': {'model': config.get('separator')}}]
        data['analysis_evidence'] = build_evidence(data)
    return data


class VocalEvidenceTests(unittest.TestCase):
    def rows(self):
        master = np.ones((3250, 2), dtype=np.float32)*.2
        return vocal_bins(master*.05, master, 1000, 26., 28., 30., chunk_index=1)

    def test_actual_partial_tail_and_source_offset_are_preserved(self):
        rows = self.rows()
        self.assertEqual(rows[0]['start'], 28.)
        self.assertEqual(rows[-1]['end'], 29.25)
        self.assertEqual(interval_activity(rows, 28, 29.25)['status'], 'quieter_candidate')
        self.assertEqual(interval_activity(rows, 28, 29.3)['status'], 'unknown')
        self.assertEqual(quieter_passages(rows)[0]['end'], 29.25)

    def test_gaps_unknown_digital_silence_legacy_rows_and_overlap_never_count_as_quiet(self):
        rows = self.rows()
        invalid = [[], rows[1:], rows[:1]+rows[2:], rows+[deepcopy(rows[-1])],
                   [{'start':28.,'end':30.,'rms':0.,'active':False}]]
        silent = np.zeros((2000, 2), dtype=np.float32)
        invalid.append(vocal_bins(silent, silent, 1000, 28., 28., 30., chunk_index=2))
        for evidence in invalid:
            with self.subTest(evidence=evidence):
                self.assertEqual(interval_activity(evidence, 28, 29.25)['status'], 'unknown')

    def test_active_line_remains_active_even_with_a_quiet_future_destination(self):
        rows = self.rows()
        rows[0].update(rms=.1, vocal_ratio=.5, active=True)
        self.assertEqual(interval_activity(rows, 28, 29.25)['status'], 'active')
        self.assertEqual(interval_activity(rows, 28.5, 29.25)['status'], 'quieter_candidate')
        self.assertEqual(quieter_passages(rows)[0]['start'], 28.5)
        self.assertEqual(quieter_passages(rows)[0]['phrase_completion'], 'unknown')

    def test_structure_phrases_and_vocal_evidence_stay_distinct(self):
        data = prediction('source', {})
        data['sections'] = [{'time': 8., 'embedding_change': .8, 'label': 'section-change candidate'}]
        data['vocal_activity'] = [{'start':0.,'end':12.,'rms':0.,'active':False}]
        evidence = build_evidence(data)
        self.assertEqual(evidence['vocal_status'], 'unknown')
        self.assertEqual(evidence['quieter_passages'], [])
        self.assertEqual(evidence['structural_changes'][0]['status'], 'candidate')
        self.assertEqual(evidence['phrase_boundaries']['phrase_completion'], 'unknown')


class FoundationCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.settings = Settings(data_root=self.root, min_free_bytes=0)
        self.source = self.root/'original.wav'
        sf.write(self.source, np.ones((12000,2), dtype=np.float32)*.2, 1000, subtype='FLOAT')
        models = self.root/'timeline/models'
        models.mkdir(parents=True)
        (models/'mert').mkdir()
        (models/'beat.ckpt').write_bytes(b'pinned beat fixture')
        (models/'mert/weights.bin').write_bytes(b'pinned embedding fixture')
        manifest = {'beat_this': {'files': {'beat.ckpt':sha256_file(models/'beat.ckpt')}},
                    'mert': {'files': {'weights.bin':sha256_file(models/'mert/weights.bin')}}}
        (models/'manifest.json').write_text(json.dumps(manifest))
        runtime = self.root/'timeline/venv/Scripts/python.exe'
        runtime.parent.mkdir(parents=True)
        runtime.touch()
        base = self.root/'separation/models'
        base.mkdir(parents=True)
        (base/'model.onnx').write_bytes(b'pinned separator fixture')
        (base/'selected_model.json').write_text(json.dumps({'filename':'model.onnx',
            'sha256':sha256_file(base/'model.onnx'), 'parameters':{'compensate':1.}}))
        runtime = self.root/'separation/venv/Scripts/python.exe'
        runtime.parent.mkdir(parents=True)
        runtime.touch()
        self.worker_calls = []
        def output(args, **kwargs):
            return 'ffmpeg fixture\n' if '-version' in args else '{}'
        def worker(args, **kwargs):
            self.worker_calls.append(args)
            request = json.loads(Path(args[-2]).read_text())
            data = prediction(request['content_hash'], request['config'])
            Path(args[-1]).write_text(json.dumps(data))
        self.addCleanup(patch.stopall)
        patch('backend.app.timeline_analysis.subprocess.check_output', side_effect=output).start()
        patch('backend.app.timeline_analysis.subprocess.run', side_effect=worker).start()
        patch('backend.app.timeline_analysis.probe', return_value=SimpleNamespace(duration=12.)).start()

    def test_new_profile_reuses_cache_and_preserves_old_predictions_and_corrections(self):
        store = TimelineStore(self.root)
        old = analyze_timeline(self.source, self.settings, with_vocals=True)
        old_prediction = store.get(**old)['prediction']
        corrected = store.correct(**old, expected_revision=0, changes={'phrase_boundaries':[2.]})
        new = analyze_timeline(self.source, self.settings, with_vocals=True, profile=FOUNDATION_PROFILE)
        self.assertNotEqual(old['timeline_id'], new['timeline_id'])
        before = len(self.worker_calls)
        self.assertEqual(analyze_timeline(self.source, self.settings, with_vocals=True, profile=FOUNDATION_PROFILE), new)
        self.assertEqual(len(self.worker_calls), before)
        self.assertEqual(store.get(**old), corrected)
        self.assertEqual(store.get(**old)['prediction'], old_prediction)
        self.assertEqual(store.for_content(sha256_file(self.source)), corrected)
        self.assertEqual(store.tracks()[0]['timeline_id'], old['timeline_id'])
        self.assertEqual(store.tracks(profile=FOUNDATION_PROFILE)[0]['timeline_id'], new['timeline_id'])
        self.assertEqual(store.for_content(sha256_file(self.source), profile=FOUNDATION_PROFILE)['timeline_id'], new['timeline_id'])
        current = store.correct(**new, expected_revision=0, changes={'phrase_boundaries':[4.]})
        evidence = foundation_evidence(current)
        self.assertEqual(evidence['reference']['correction_revision'], 1)
        self.assertEqual(evidence['phrase_boundaries']['times'], [4.])
        self.assertEqual(store.get(**new)['prediction']['phrase_boundaries']['times'], [0.])

    def test_changed_model_or_profile_is_not_silently_reused(self):
        with self.assertRaisesRegex(ValueError, 'source changed'):
            analyze_timeline(self.source, self.settings, expected_content_hash='stale catalog hash')
        analyze_timeline(self.source, self.settings, with_vocals=True, profile=FOUNDATION_PROFILE)
        (self.root/'separation/models/model.onnx').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'model changed'):
            analyze_timeline(self.source, self.settings, with_vocals=True, profile=FOUNDATION_PROFILE)
        self.assertEqual(len(self.worker_calls), 1)
        with self.assertRaises(ValueError):
            analyze_timeline(self.source, self.settings, profile='unknown')

    def test_registered_pair_uses_catalog_hashes_and_keeps_order(self):
        other = self.root/'second.wav'
        sf.write(other, np.ones((12000,2), dtype=np.float32)*.1, 1000, subtype='FLOAT')
        catalog = [{'id': 'a', 'path': str(self.source), 'content_hash':sha256_file(self.source)},
                   {'id': 'b', 'path': str(other), 'content_hash':sha256_file(other)}]
        workflow = SimpleNamespace(settings=self.settings, storage=SimpleNamespace(root=self.root), catalog=lambda internal: catalog)
        result = analyze_registered_pair(workflow, ['b', 'a'])
        self.assertEqual([row['catalog_id'] for row in result['sources']], ['b', 'a'])
        self.assertEqual(result['sources'][0]['evidence']['reference']['source_sha256'], sha256_file(other))
        with self.assertRaises(ValueError):
            analyze_registered_pair(workflow, ['a','not registered'])
        other.write_bytes(b'changed original')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            analyze_registered_pair(workflow, ['a','b'])

    def test_missing_vocal_provenance_cannot_be_persisted(self):
        keys = analyze_timeline(self.source, self.settings, with_vocals=True, profile=FOUNDATION_PROFILE)
        store = TimelineStore(self.root)
        data = store.get(**keys)['prediction']
        data['vocal_chunks'] = []
        with self.assertRaisesRegex(ValueError, 'provenance'):
            store.save(self.source, data, data['config'])

    def test_verified_separation_hashes_model_config_and_stems(self):
        source = self.root/'context.wav'
        sf.write(source, np.ones((44100,2), dtype=np.float32)*1.2, 44100, subtype='FLOAT')
        class Separator:
            calls = 0
            def __init__(self, model_dir): pass
            def separate(self, samples):
                Separator.calls += 1
                return samples*.9, samples*.1
        manifest = separate_verified(source, self.root/'separation/models', self.root/'stems', separator_factory=Separator)
        again = separate_verified(source, self.root/'separation/models', self.root/'stems', separator_factory=Separator)
        self.assertEqual(again, manifest)
        self.assertEqual(Separator.calls, 1)
        self.assertEqual(sf.info(manifest['vocals']).subtype, 'FLOAT')
        Path(manifest['vocals']).write_bytes(b'corrupt cached evidence')
        with self.assertRaisesRegex(ValueError, 'stem changed'):
            separate_verified(source, self.root/'separation/models', self.root/'stems', separator_factory=Separator)
        self.assertEqual(Separator.calls, 1)


if __name__ == '__main__':
    unittest.main()
