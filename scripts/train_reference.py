"""Train an experimental positive-only context model from an imported reference."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from backend.app.config import Settings, PROJECT_ROOT
from backend.app.references import ReferenceStore
from backend.app.timelines import canonical
from backend.app.planning.reference_learning import build_dataset, split_dataset, VERSION
from scripts.setup_timeline import sha256


def train_reference(reference_id, settings, *, epochs=300, seed=11):
    runtime = settings.data_root/('timeline/venv/Scripts/python.exe' if os.name == 'nt' else 'timeline/venv/bin/python')
    if not runtime.is_file():
        raise ValueError('Set up the isolated timeline PyTorch runtime first')
    store = ReferenceStore(settings)
    dataset = build_dataset(store, reference_id)
    split = split_dataset(dataset)
    print(json.dumps({'located_occurrences': len(dataset['occurrences']), 'examples': len(dataset['rows']),
                      'train_pairs': len({dataset['rows'][i]['pair_position'] for i in split['train']}),
                      'evaluation_pairs': len({dataset['rows'][i]['pair_position'] for i in split['evaluation']}),
                      'excluded_occurrences': dataset['excluded_occurrences']}), flush=True)
    code = PROJECT_ROOT/'backend/app/planning/reference_learning.py'
    identity = hashlib.sha256(canonical({'dataset': dataset, 'version': VERSION, 'epochs': epochs,
                                         'seed': seed, 'implementation_hash': sha256(code)}).encode()).hexdigest()
    destination = store.storage.root/'models'/('reference-context-'+identity)
    if destination.exists():
        # Keep immutable existing runs intact.
        raise ValueError('This exact training run already exists: '+str(destination))
    with tempfile.TemporaryDirectory(dir=store.storage.root/'models', prefix='training-') as temporary:
        staging = Path(temporary)
        request = staging/'request.json'
        request.write_text(canonical(dataset), encoding='utf-8')
        output = staging/'model'
        result = subprocess.run([str(runtime), '-m', 'scripts.reference_training_worker', 'train', str(request),
                                 str(output), '--epochs', str(epochs), '--seed', str(seed)],
                                cwd=PROJECT_ROOT, capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=1800)
        if result.returncode:
            raise RuntimeError('Training worker failed: '+result.stderr[-4000:])
        report = json.loads((output/'report.json').read_text(encoding='utf-8'))
        if report['status'] != 'experimental' or report['active'] or not all(
                sha256(output/name) == digest for name, digest in report['artifacts'].items()):
            raise ValueError('Training worker produced invalid artifacts')
        # A complete run becomes visible together. Failed jobs publish nothing.
        output.rename(destination)
    return {'model_path': str(destination), 'report': report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference_id')
    parser.add_argument('--epochs', type=int, default=300)
    parser.add_argument('--seed', type=int, default=11)
    args = parser.parse_args()
    result = train_reference(args.reference_id, Settings.from_env(), epochs=args.epochs, seed=args.seed)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
