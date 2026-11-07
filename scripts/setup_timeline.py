"""Download pinned official inference artifacts; audio never leaves this machine."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
import urllib.error

MERT_REVISION = '12af15fef9d0ac838c3f475bfbbf26d2060dd4f5'
MERT_FILES = ('config.json', 'configuration_MERT.py', 'modeling_MERT.py',
              'preprocessor_config.json', 'pytorch_model.bin')
BEAT_SHA256 = '8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331'
BEAT_MIRROR = 'https://huggingface.co/oulianov/beat_this/resolve/fea475438eb3b8e509c7661a44f1ca97ffbe9829/final0.ckpt'


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def download(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        partial = path.with_name(path.name+'.part')
        with urllib.request.urlopen(url, timeout=120) as response, partial.open('wb') as out:
            while block := response.read(1024*1024):
                out.write(block)
        partial.replace(path)
    return sha256(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    models = args.root/'models'
    manifest = {'mert': {'model': 'm-a-p/MERT-v1-95M', 'revision': MERT_REVISION,
                         'pooling': 'last_hidden_state time mean; frozen; 5-second windows', 'files': {}},
                'beat_this': {'model': 'final0', 'files': {}}}
    for filename in MERT_FILES:
        print('Checking MERT '+filename, flush=True)
        manifest['mert']['files'][filename] = download(
            f'https://huggingface.co/m-a-p/MERT-v1-95M/resolve/{MERT_REVISION}/{filename}', models/'mert'/filename)
    print('Checking Beat This final0', flush=True)
    try:
        digest = download('https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt', models/'final0.ckpt')
    except urllib.error.URLError:
        print('Official checkpoint host unavailable; using pinned reupload with SHA-256 verification', flush=True)
        digest = download(BEAT_MIRROR, models/'final0.ckpt')
    if digest != BEAT_SHA256:
        raise ValueError('Beat This checkpoint does not match the pinned SHA-256')
    manifest['beat_this']['files']['final0.ckpt'] = digest
    manifest['beat_this']['download_provenance'] = {'official': 'https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt', 'pinned_mirror': BEAT_MIRROR}
    path = models/'manifest.json'
    payload = json.dumps(manifest, sort_keys=True, indent=2)
    if path.exists() and json.loads(path.read_text(encoding='utf-8')) != manifest:
        raise ValueError('Existing model manifest differs; use a new model directory instead of changing it')
    path.write_text(payload, encoding='utf-8')
    print('Timeline models ready: '+str(path), flush=True)


if __name__ == '__main__':
    main()
