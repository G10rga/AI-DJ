"""Run with the optional D: separation environment; keep stems out of Git."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import soundfile as sf
from backend.app.audio.mdx import MDXSeparator, VERSION, sha256_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--cache-root', type=Path, required=True)
    parser.add_argument('--result-file', type=Path, required=True)
    args = parser.parse_args()
    metadata = json.loads((args.model_dir/'selected_model.json').read_text(encoding='utf-8'))
    source_hash = sha256_file(args.source)
    key = hashlib.sha256(f'{VERSION}:{source_hash}:{metadata["sha256"]}'.encode()).hexdigest()
    directory = args.cache_root / key
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory/'manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if all(Path(manifest[name]).exists() for name in ('instrumental', 'vocals')):
            print('Using cached vocal/instrumental separation', flush=True)
            args.result_file.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            return
    samples, rate = sf.read(args.source, dtype='float32', always_2d=True)
    if rate != 44100 or samples.shape[1] != 2:
        raise ValueError('Prepare stereo 44.1 kHz PCM before separation')
    separator = MDXSeparator(args.model_dir)
    instrumental, vocals = separator.separate(samples.T)
    error = float(np.max(abs(instrumental + vocals - samples.T)))
    if error > 1e-5:
        raise ValueError('Separated stems do not reconstruct their source')
    manifest = {'version': VERSION, 'source_sha256': source_hash, 'model': metadata,
                'sample_rate': rate, 'frames': len(samples), 'reconstruction_error': error}
    for name, data in [('instrumental', instrumental), ('vocals', vocals)]:
        destination = directory / (name+'.wav')
        temporary = directory / (name+'.part.wav')
        sf.write(temporary, data.T, rate, subtype='FLOAT')
        temporary.replace(destination)
        manifest[name] = str(destination)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    args.result_file.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'Separation ready; reconstruction error {error:.3g}', flush=True)


if __name__ == '__main__':
    main()
