"""Positive-only observed-successor context learning; never preference/style labels."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from backend.app.timelines import canonical

VERSION = 'reference-successor-context-1'
DESCRIPTOR = {'version': 'centered-log-spectrum-1', 'bands': 32, 'step_seconds': .25,
              'window_seconds': 8, 'fields': ['mean', 'std']}


def descriptor(features, center, seconds=8):
    features = np.asarray(features)
    if features.ndim != 2 or features.shape[1] != 32 or not np.isfinite(features).all():
        raise ValueError('Expected finite 32-band reference features')
    start = int(round((center-seconds/2)/.25))
    count = int(round(seconds/.25))
    if start < 0 or start+count > len(features):
        raise ValueError('Context window falls outside available audio')
    window = features[start:start+count].astype(np.float64)
    # Remove frame-wide gain; this descriptor is timbre/dynamics, not an EQ curve.
    window -= window.mean(axis=1, keepdims=True)
    return np.concatenate((window.mean(axis=0), window.std(axis=0))).tolist()


def build_dataset(store, reference_id, *, min_similarity=.5, max_windows=4):
    reference = store.get(reference_id)
    if not reference['alignments']:
        raise ValueError('Reference has no alignment')
    alignment = reference['alignments'][-1]
    choices = alignment.get('ordered_suggestions')
    if not choices or len(choices) != len(reference['import']['tracks']):
        raise ValueError('Reference needs ordered alignment suggestions')
    recording = store._features(reference['import']['recording'])
    contexts, exclusions = {}, []
    for position, (original, track, choice) in enumerate(zip(reference['import']['tracks'], alignment['tracks'], choices)):
        if choice is None:
            exclusions.append({'position': position, 'reason': 'unresolved alignment'})
            continue
        alternative = next(a for a in track['alternatives'] if a['source_hash'] == choice['source_hash'])
        hypothesis = alternative['hypotheses'][choice['hypothesis_index']]
        if hypothesis['similarity'] < min_similarity or hypothesis['supporting_windows'] < hypothesis.get('minimum_supporting_windows', 2):
            exclusions.append({'position': position, 'reason': 'insufficient alignment evidence'})
            continue
        source = next(s for s in original['sources'] if s['content_hash'] == choice['source_hash'])
        features = store._features(source)
        anchors = sorted(hypothesis['anchors'], key=lambda a: (-a['similarity'], a['source_seconds']))
        windows = []
        for anchor in anchors:
            if anchor['similarity'] < min_similarity:
                continue
            source_center = anchor['source_seconds']+anchor['window_seconds']/2
            mix_center = anchor['mix_seconds']+anchor['window_seconds']*anchor['scale']/2
            # Distinct augmentation windows, not copies of the same snippet.
            if any(abs(source_center-w['source_center']) < 8 for w in windows):
                continue
            try:
                windows.append({'source': descriptor(features, source_center),
                                'recording': descriptor(recording, mix_center),
                                'source_center': source_center, 'mix_center': mix_center,
                                'similarity': anchor['similarity']})
            except ValueError:
                continue
            if len(windows) == max_windows:
                break
        if not windows:
            exclusions.append({'position': position, 'reason': 'no bounded supported context windows'})
            continue
        contexts[position] = {'source_hash': source['content_hash'], 'windows': windows}
    rows = []
    for position in range(len(choices)-1):
        # An unresolved song is never silently bridged.
        if position not in contexts or position+1 not in contexts:
            continue
        a, b = contexts[position], contexts[position+1]
        count = max(len(a['windows']), len(b['windows']))
        for i in range(count):
            first = a['windows'][min(i, len(a['windows'])-1)]
            second = b['windows'][min(i, len(b['windows'])-1)]
            rows.append({'pair_position': position, 'source_hashes': [a['source_hash'], b['source_hash']],
                         'x': first['source']+first['recording'], 'y': second['source'],
                         'source_centers': [first['source_center'], second['source_center']],
                         'recording_centers': [first['mix_center'], second['mix_center']],
                         'alignment_similarities': [first['similarity'], second['similarity']],
                         'supervision': 'automatic unreviewed observed successor; not a preference'})
    return {'version': VERSION, 'reference_id': reference_id, 'alignment_id': alignment['id'],
            'recording_hash': reference['import']['recording']['content_hash'],
            'descriptor': DESCRIPTOR, 'min_similarity': min_similarity, 'max_windows_per_pair': max_windows,
            'occurrences': [{'position': i, 'source_hash': c['source_hash']} for i, c in sorted(contexts.items())],
            'rows': rows, 'excluded_occurrences': exclusions,
            'label_provenance': 'Owner-provided order plus automatic source-to-recording anchors; no reviewed transition controls',
            'reviewed_style_examples': 0, 'preference_examples_created': 0}


def split_dataset(dataset, *, holdout_fraction=.25):
    """Source-identity holdout; exclude boundary pairs and recording-window overlap."""
    occurrences = dataset['occurrences']
    if not 0 < holdout_fraction < .5 or len(occurrences) < 8:
        raise ValueError('Need at least eight located occurrences and a valid holdout fraction')
    tail = occurrences[-max(3, math.ceil(len(occurrences)*holdout_fraction)):]
    held = {row['source_hash'] for row in tail}
    train, evaluation, excluded = [], [], []
    for i, row in enumerate(dataset['rows']):
        membership = [digest in held for digest in row['source_hashes']]
        if all(membership):
            evaluation.append(i)
        elif not any(membership):
            train.append(i)
        else:
            excluded.append(i)
    # Keep every augmentation of a pair together. Embargo train recording windows
    # touching any evaluation window, including the target's matched passage.
    evaluation_centers = [t for i in evaluation for t in dataset['rows'][i]['recording_centers']]
    contaminated = {dataset['rows'][i]['pair_position'] for i in train
                    if any(abs(t-e) < 16 for t in dataset['rows'][i]['recording_centers'] for e in evaluation_centers)}
    safe = []
    for i in train:
        (excluded if dataset['rows'][i]['pair_position'] in contaminated else safe).append(i)
    train = safe
    train_hashes = {h for i in train for h in dataset['rows'][i]['source_hashes']}
    eval_hashes = {h for i in evaluation for h in dataset['rows'][i]['source_hashes']}
    if train_hashes & eval_hashes:
        raise ValueError('Source identities leaked across the split')
    if len({dataset['rows'][i]['pair_position'] for i in train}) < 4 or len({dataset['rows'][i]['pair_position'] for i in evaluation}) < 2:
        raise ValueError('Not enough source-disjoint observed pairs for experimental training/evaluation')
    return {'train': train, 'evaluation': evaluation, 'excluded': sorted(excluded),
            'train_source_hashes': sorted(train_hashes), 'evaluation_source_hashes': sorted(eval_hashes),
            'method': 'contiguous tail identities, cross-group edges excluded, 16-second recording embargo',
            'independent_reference_set_evaluation': False}


def prepare_arrays(dataset, split):
    x = np.asarray([r['x'] for r in dataset['rows']], dtype=np.float32)
    y = np.asarray([r['y'] for r in dataset['rows']], dtype=np.float32)
    if x.shape != (len(y), 128) or y.ndim != 2 or y.shape[1] != 64 or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('Training descriptors must be finite with known dimensions')
    train = split['train']
    statistics = {'x_mean': x[train].mean(axis=0).tolist(), 'x_scale': np.maximum(x[train].std(axis=0), .1).tolist(),
                  'y_mean': y[train].mean(axis=0).tolist(), 'y_scale': np.maximum(y[train].std(axis=0), .1).tolist()}
    normalized_x = (x-np.asarray(statistics['x_mean']))/statistics['x_scale']
    normalized_y = (y-np.asarray(statistics['y_mean']))/statistics['y_scale']
    persistence = (x[:, :64]-np.asarray(statistics['y_mean']))/statistics['y_scale']
    return normalized_x.astype(np.float32), normalized_y.astype(np.float32), persistence.astype(np.float32), statistics


def make_network(hidden=24):
    import torch
    network = torch.nn.Sequential(torch.nn.Linear(128, hidden), torch.nn.SiLU(),
                                  torch.nn.Dropout(.1), torch.nn.Linear(hidden, 64))
    torch.nn.init.zeros_(network[-1].weight)
    torch.nn.init.zeros_(network[-1].bias)
    return network


def train(dataset, destination, *, seed=11, epochs=300):
    import torch
    from importlib.metadata import version
    if type(epochs) is not int or not 1 <= epochs <= 10000:
        raise ValueError('Epochs must be between one and 10000')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    split = split_dataset(dataset)
    x, y, persistence, statistics = prepare_arrays(dataset, split)
    tensors = [torch.from_numpy(a) for a in (x, y, persistence)]
    network = make_network()
    optimizer = torch.optim.AdamW(network.parameters(), lr=.002, weight_decay=.1)
    train_indices = split['train']
    losses = []
    for epoch in range(epochs):
        network.train()
        optimizer.zero_grad()
        prediction = tensors[2][train_indices]+network(tensors[0][train_indices])
        loss = torch.nn.functional.mse_loss(prediction, tensors[1][train_indices])
        if not torch.isfinite(loss):
            raise ValueError('Non-finite training loss')
        loss.backward()
        torch.nn.utils.clip_grad_norm_(network.parameters(), 1.)
        optimizer.step()
        if epoch == 0 or (epoch+1) % 50 == 0 or epoch+1 == epochs:
            losses.append({'epoch': epoch+1, 'training_mse': float(loss.detach())})
    network.eval()
    with torch.no_grad():
        prediction = (tensors[2]+network(tensors[0])).numpy()
    metrics = {}
    for name in ('train', 'evaluation'):
        indices = split[name]
        # Weight each original transition equally, independent of augmentation count.
        pairs = sorted({dataset['rows'][i]['pair_position'] for i in indices})
        def error(values):
            return float(np.mean([np.mean((values[[i for i in indices if dataset['rows'][i]['pair_position'] == p]]-
                                           y[[i for i in indices if dataset['rows'][i]['pair_position'] == p]])**2)
                                  for p in pairs]))
        metrics[name] = {'examples': len(indices), 'observed_pairs': len(pairs),
                         'model_mse': error(prediction), 'training_mean_baseline_mse': error(np.zeros_like(y)),
                         'persistence_baseline_mse': error(persistence)}
    checkpoint = destination/'checkpoint.pt'
    torch.save(network.state_dict(), checkpoint)
    configuration = {'version': VERSION, 'hidden': 24, 'seed': seed, 'epochs': epochs,
                     'optimizer': 'AdamW', 'learning_rate': .002, 'weight_decay': .1, 'dropout': .1,
                     'statistics': statistics, 'descriptor': DESCRIPTOR,
                     'prediction': 'next source descriptor = outgoing source descriptor + learned context residual',
                     'runtime': {p: version(p) for p in ('torch', 'numpy')}}
    (destination/'config.json').write_text(canonical(configuration), encoding='utf-8')
    (destination/'dataset.json').write_text(canonical(dataset), encoding='utf-8')
    (destination/'split.json').write_text(canonical(split), encoding='utf-8')
    report = {'version': VERSION, 'status': 'experimental', 'active': False,
              'created_at': datetime.now(timezone.utc).isoformat(), 'reference_id': dataset['reference_id'],
              'alignment_id': dataset['alignment_id'], 'metrics': metrics, 'training_trace': losses,
              'reviewed_style_examples': 0, 'preference_examples_created': 0,
              'measured_generalization': 'within-reference, assigned source-identity-disjoint descriptor regression only',
              'independent_reference_set_evaluation': None, 'listening_approval': False,
              'evaluation_better_than_both_baselines': metrics['evaluation']['model_mse'] < min(
                  metrics['evaluation']['training_mean_baseline_mse'], metrics['evaluation']['persistence_baseline_mse']),
              'limitations': ['Single reference recording; no independent reference-set evaluation.',
                              'Automatic anchors are unreviewed and may contain alignment errors or other audible sources.',
                              'Source identities are split by hashes; alternate versions of the same song are not automatically detected.',
                              'Predicts successor context, not preferred alternatives, cue boundaries, recipes, EQ or waveform curves.',
                              'No listening or musical-quality acceptance; model is not promoted.']}
    from scripts.setup_timeline import sha256
    report['artifacts'] = {name: sha256(destination/name) for name in ('checkpoint.pt', 'config.json', 'dataset.json', 'split.json')}
    report['implementation_hash'] = sha256(Path(__file__))
    (destination/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report


def load_model(destination):
    import torch
    from scripts.setup_timeline import sha256
    destination = Path(destination)
    report = json.loads((destination/'report.json').read_text(encoding='utf-8'))
    if report.get('version') != VERSION or report.get('status') != 'experimental':
        raise ValueError('Unsupported reference context model')
    expected = {'checkpoint.pt', 'config.json', 'dataset.json', 'split.json'}
    if set(report['artifacts']) != expected:
        raise ValueError('Incomplete model artifact manifest')
    for name, digest in report['artifacts'].items():
        if sha256(destination/name) != digest:
            raise ValueError('Model artifact changed: '+name)
    config = json.loads((destination/'config.json').read_text(encoding='utf-8'))
    if config.get('version') != VERSION or config.get('descriptor') != DESCRIPTOR or config.get('hidden') != 24:
        raise ValueError('Unsupported model configuration')
    network = make_network(config['hidden'])
    state = torch.load(destination/'checkpoint.pt', map_location='cpu', weights_only=True)
    network.load_state_dict(state, strict=True)
    network.eval()
    return network, config, report


def predict(destination, source_descriptor, recording_descriptor=None):
    import torch
    network, config, _ = load_model(destination)
    source = np.asarray(source_descriptor, dtype=np.float32)
    recording = source if recording_descriptor is None else np.asarray(recording_descriptor, dtype=np.float32)
    if source.shape != (64,) or recording.shape != (64,) or not np.isfinite(source).all() or not np.isfinite(recording).all():
        raise ValueError('Prediction requires finite 64-value context descriptors')
    statistics = config['statistics']
    x = (np.concatenate((source, recording))-statistics['x_mean'])/statistics['x_scale']
    with torch.no_grad():
        residual = network(torch.tensor(x, dtype=torch.float32)[None]).numpy()[0]
    result = source+residual*np.asarray(statistics['y_scale'])
    if not np.isfinite(result).all():
        raise ValueError('Model produced a non-finite prediction')
    return {'predicted_successor_descriptor': result.tolist(), 'status': 'experimental',
            'recording_context': 'source fallback' if recording_descriptor is None else 'provided recording',
            'meaning': 'musical successor context; not a preference or transition recipe'}
