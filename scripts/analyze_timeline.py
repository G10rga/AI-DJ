"""Build cached musical timelines for local files, using the isolated CPU worker."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from backend.app.audio.probe import probe
from backend.app.config import Settings, PROJECT_ROOT
from backend.app.storage import Storage
from backend.app.timelines import TimelineStore, VERSION
from scripts.setup_timeline import sha256


def analyze_timeline(source, settings, *, with_vocals=False):
    source = Path(source).resolve(strict=True)
    storage = Storage(settings.data_root)
    storage.initialize()
    root = storage.root/'timeline'
    runtime = root/('venv/Scripts/python.exe' if os.name == 'nt' else 'venv/bin/python')
    if not runtime.exists() or not (root/'models/manifest.json').exists():
        raise ValueError('Run scripts/setup-timeline.ps1 before timeline inference')
    manifest = json.loads((root/'models/manifest.json').read_text(encoding='utf-8'))
    for group, base in (('mert', root/'models/mert'), ('beat_this', root/'models')):
        for name, digest in manifest[group]['files'].items():
            if sha256(base/name) != digest:
                raise ValueError('Timeline model changed: '+name)
    packages = subprocess.check_output([str(runtime), '-c',
        "import json,importlib.metadata as m; print(json.dumps({p:m.version(p) for p in ('torch','torchaudio','beat-this','transformers','numpy','scipy','einops','rotary-embedding-torch','soxr','soundfile')}))"], text=True)
    config = {'version': VERSION, 'models': manifest, 'packages': json.loads(packages),
              'adapter_version': 'cpu-models-2-strict-weight-norm',
              'core_seconds': 30, 'context_seconds': 4, 'embedding_seconds': 5, 'device': 'cpu',
              'with_vocals': with_vocals}
    if with_vocals:
        config['separator'] = json.loads((storage.root/'separation/models/selected_model.json').read_text(encoding='utf-8'))
    digest = sha256(source)
    store = TimelineStore(storage.root)
    prediction = store.find(digest, config)
    if prediction is None:
        info = probe(source, settings)
        storage.require_space(300*1024**2, settings.min_free_bytes)
        with storage.temporary_directory() as work:
            request = {'source': str(source), 'content_hash': digest, 'duration': info.duration,
                       'root': str(root), 'data_root': str(storage.root), 'tmp_root': str(storage.root/'tmp'),
                       'ffmpeg': settings.ffmpeg, 'config': config, 'with_vocals': with_vocals}
            request_path, output = work/'request.json', work/'result.json'
            request_path.write_text(json.dumps(request), encoding='utf-8')
            worker_env = dict(os.environ, HF_HOME=str(root/'hf-cache'), HF_MODULES_CACHE=str(root/'hf-cache/modules'),
                              TORCH_HOME=str(root/'torch-cache'), HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
            subprocess.run([str(runtime), '-m', 'scripts.timeline_worker', str(request_path), str(output)],
                           check=True, cwd=PROJECT_ROOT, timeout=7200, env=worker_env)
            prediction = json.loads(output.read_text(encoding='utf-8'))
    else:
        print('Using cached timeline: '+source.name, flush=True)
    return store.save(source, prediction, config)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sources', nargs='+', type=Path)
    parser.add_argument('--with-vocals', action='store_true', help='Run the validated local separator on bounded source chunks')
    args = parser.parse_args()
    settings = Settings.from_env()
    for source in args.sources:
        print(json.dumps(analyze_timeline(source, settings, with_vocals=args.with_vocals), indent=2))


if __name__ == '__main__':
    main()
