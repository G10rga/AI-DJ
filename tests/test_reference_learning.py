"""Observed-context learning must avoid identity leakage and invented DJ labels."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import numpy as np
from backend.app.planning.reference_learning import (
    descriptor, build_dataset, split_dataset, prepare_arrays, train, predict, load_model)


def fixture():
    rng = np.random.default_rng(12)
    occurrences = [{'position': i, 'source_hash': str(i)} for i in range(16)]
    rows = []
    # Smooth positive observed successor relation, with no preference negatives.
    contexts = rng.normal(size=(16, 64)).astype(np.float32)
    for i in range(15):
        for augmentation in range(2):
            a, b = contexts[i], contexts[i+1]
            rows.append({'pair_position': i, 'source_hashes': [str(i), str(i+1)],
                         'x': np.concatenate((a, a+.01*augmentation)).tolist(), 'y': b.tolist(),
                         'recording_centers': [i*40+augmentation*8, (i+1)*40+augmentation*8]})
    return {'reference_id': 'test-reference', 'alignment_id': 'test-alignment',
            'occurrences': occurrences, 'rows': rows}


class ReferenceLearningTests(unittest.TestCase):
    def test_descriptor_rejects_bad_data_and_removes_gain_offset(self):
        rng = np.random.default_rng(3)
        values = rng.normal(size=(64, 32))
        self.assertTrue(np.allclose(descriptor(values, 8), descriptor(values+9, 8)))
        for values, center in ((np.zeros((20, 32)), 8), (np.zeros((64, 31)), 8),
                               (np.full((64, 32), np.nan), 8), (np.zeros((64, 32)), -1)):
            with self.assertRaises(ValueError):
                descriptor(values, center)

    def test_all_windows_and_repeated_source_identity_stay_in_one_split(self):
        dataset = fixture()
        # The same track reappears late in the reference.
        dataset['occurrences'][2]['source_hash'] = '14'
        for row in dataset['rows']:
            row['source_hashes'] = ['14' if h == '2' else h for h in row['source_hashes']]
        split = split_dataset(dataset)
        self.assertFalse(set(split['train_source_hashes']) & set(split['evaluation_source_hashes']))
        self.assertNotIn('14', split['train_source_hashes'])
        membership = {}
        for name in ('train', 'evaluation', 'excluded'):
            for index in split[name]:
                pair = dataset['rows'][index]['pair_position']
                self.assertIn(membership.setdefault(pair, name), (name,))
        self.assertEqual(sum(len(split[n]) for n in ('train', 'evaluation', 'excluded')), len(dataset['rows']))

    def test_recording_overlap_embargo_drops_entire_pair(self):
        dataset = fixture()
        dataset['rows'][0]['recording_centers'] = [12*40, 13*40]
        split = split_dataset(dataset)
        self.assertNotIn(0, split['train'])
        self.assertNotIn(1, split['train'])

    def test_scalers_never_fit_evaluation_data(self):
        dataset = fixture()
        split = split_dataset(dataset)
        _, _, _, original = prepare_arrays(dataset, split)
        changed = deepcopy(dataset)
        for i in split['evaluation']:
            changed['rows'][i]['x'] = [1e6]*128
            changed['rows'][i]['y'] = [1e6]*64
        _, _, _, after = prepare_arrays(changed, split)
        self.assertEqual(original, after)
        changed['rows'][0]['y'][0] = float('inf')
        with self.assertRaises(ValueError):
            prepare_arrays(changed, split)

    def test_unresolved_occurrences_are_not_bridged_or_made_style_labels(self):
        rng = np.random.default_rng(2)
        anchors = [{'source_seconds': 10, 'mix_seconds': 20, 'window_seconds': 16,
                    'scale': 1., 'similarity': .9}]
        hypothesis = {'similarity': .9, 'supporting_windows': 2, 'anchors': anchors}
        store = Mock()
        store.get.return_value = {
            'import': {'recording': {'content_hash': 'recording'},
                       'tracks': [{'sources': [{'content_hash': str(i)}]} for i in range(3)]},
            'alignments': [{'id': 'alignment', 'ordered_suggestions': [
                {'source_hash': '0', 'hypothesis_index': 0}, None,
                {'source_hash': '2', 'hypothesis_index': 0}],
                'tracks': [{'alternatives': [{'source_hash': str(i), 'hypotheses': [hypothesis]}]} for i in range(3)]}]}
        store._features.return_value = rng.normal(size=(300, 32))
        result = build_dataset(store, 'reference')
        self.assertEqual(result['rows'], [])
        self.assertEqual(result['reviewed_style_examples'], 0)
        self.assertEqual(result['preference_examples_created'], 0)
        self.assertEqual(result['excluded_occurrences'][0]['position'], 1)


@unittest.skipUnless(importlib.util.find_spec('torch'), 'Run these checks in the isolated PyTorch runtime')
class ReferenceTrainingTests(unittest.TestCase):
    def test_training_checkpoint_predictions_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = train(fixture(), root/'first', epochs=12)
            second = train(fixture(), root/'second', epochs=12)
            self.assertEqual(first['metrics'], second['metrics'])
            self.assertEqual(first['status'], 'experimental')
            self.assertFalse(first['active'])
            self.assertFalse(first['listening_approval'])
            self.assertEqual(first['reviewed_style_examples'], 0)
            prediction = predict(root/'first', np.zeros(64))
            self.assertTrue(np.isfinite(prediction['predicted_successor_descriptor']).all())
            self.assertEqual(prediction['recording_context'], 'source fallback')
            with self.assertRaises(ValueError):
                predict(root/'first', np.full(64, np.nan))
            checkpoint = root/'first'/'checkpoint.pt'
            checkpoint.write_bytes(checkpoint.read_bytes()+b'changed')
            with self.assertRaisesRegex(ValueError, 'artifact changed'):
                load_model(root/'first')


if __name__ == '__main__':
    unittest.main()
