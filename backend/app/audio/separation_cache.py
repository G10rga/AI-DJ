"""Verified, separately versioned MDX cache for transition-foundation evidence."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import soundfile as sf

from .mdx import MDXSeparator, VERSION as MDX_VERSION, sha256_file

VERSION = 'verified-mdx-cache-1'


def configuration(model_dir):
    model_dir = Path(model_dir)
    metadata = json.loads((model_dir/'selected_model.json').read_text(encoding='utf-8'))
    if sha256_file(model_dir/metadata['filename']) != metadata['sha256']:
        raise ValueError('Separation model hash mismatch')
    installed = {d.metadata['Name'].lower(): d.version for d in importlib.metadata.distributions()}
    packages = {p: installed[p] for p in ('onnxruntime', 'onnxruntime-directml', 'numpy', 'scipy', 'soundfile')
                if p in installed}
    return {'version': VERSION, 'mdx_version': MDX_VERSION, 'model': metadata, 'packages': packages,
            'adapter_sha256': sha256_file(Path(__file__).with_name('mdx.py')),
            'cache_sha256': sha256_file(__file__)}


def validate_manifest(manifest, source_hash, config):
    if manifest.get('source_sha256') != source_hash or manifest.get('configuration') != config:
        raise ValueError('Separation cache identity mismatch')
    for name in ('instrumental', 'vocals'):
        path = Path(manifest[name])
        if not path.exists() or sha256_file(path) != manifest['stem_sha256'][name]:
            raise ValueError('Cached separation stem changed')
        info = sf.info(path)
        if (info.frames != manifest['frames'] or info.channels != 2
                or info.samplerate != 44100 or info.subtype != 'FLOAT'):
            raise ValueError('Cached separation stem format mismatch')
    return manifest


def separate_verified(source, model_dir, cache_root, *, separator_factory=MDXSeparator):
    source, cache_root = Path(source), Path(cache_root)
    config = configuration(model_dir)
    source_hash = sha256_file(source)
    key = hashlib.sha256(json.dumps([source_hash, config], sort_keys=True).encode()).hexdigest()
    directory = cache_root/VERSION/key
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory/'manifest.json'
    if manifest_path.exists():
        return validate_manifest(json.loads(manifest_path.read_text(encoding='utf-8')), source_hash, config)
    samples, rate = sf.read(source, dtype='float32', always_2d=True)
    if rate != 44100 or samples.shape[1] != 2 or not 0 < len(samples) <= 180*rate or not np.isfinite(samples).all():
        raise ValueError('Expected finite stereo 44100 Hz context of at most 180s')
    instrumental, vocals = separator_factory(model_dir).separate(samples.T)
    if (instrumental.shape != samples.T.shape or vocals.shape != samples.T.shape
            or not np.isfinite(instrumental).all() or not np.isfinite(vocals).all()):
        raise ValueError('Invalid separated stems')
    error = float(np.max(abs(instrumental+vocals-samples.T)))
    if error > 1e-5 or sha256_file(source) != source_hash:
        raise ValueError('Separated stems do not reconstruct the unchanged source')
    manifest = {'version': VERSION, 'configuration': config, 'model': config['model'],
                'source_sha256': source_hash, 'sample_rate': rate, 'frames': len(samples),
                'reconstruction_error': error, 'stem_sha256': {}}
    with TemporaryDirectory(dir=directory, prefix='attempt-') as work:
        for name, data in (('instrumental', instrumental), ('vocals', vocals)):
            staged = Path(work)/(name+'.wav')
            sf.write(staged, data.T, rate, subtype='FLOAT')
            destination = directory/(name+'.wav')
            staged.replace(destination)
            manifest[name] = str(destination)
            manifest['stem_sha256'][name] = sha256_file(destination)
        staged = Path(work)/'manifest.json'
        staged.write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding='utf-8')
        staged.replace(manifest_path)
    return validate_manifest(manifest, source_hash, config)
