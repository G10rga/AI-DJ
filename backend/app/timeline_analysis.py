"""Application service for immutable analysis through the isolated model workers."""
import json
import os
from pathlib import Path
import subprocess
from backend.app.audio.probe import probe
from backend.app.config import Settings, PROJECT_ROOT
from backend.app.storage import Storage
from backend.app.timelines import TimelineStore, VERSION
from scripts.setup_timeline import sha256
from backend.app.audio.analysis_evidence import VERSION as EVIDENCE_VERSION

LEGACY_PROFILE = 'legacy'
FOUNDATION_PROFILE = 'transition-foundation-1'


def separator_runtime(root):
    candidates = [root/'gpu-venv/Scripts/python.exe', root/'venv/Scripts/python.exe', root/'venv/bin/python']
    runtime = next((p for p in candidates if p.exists()), None)
    if runtime is None:
        raise ValueError('Set up the isolated separator runtime first')
    return runtime


def runtime_packages(runtime, packages):
    command = ('import json,importlib.metadata as m; names=' + repr(packages) +
               '; installed={d.metadata["Name"].lower():d.version for d in m.distributions()}; '
               'print(json.dumps({p:installed[p.lower()] for p in names if p.lower() in installed}))')
    return json.loads(subprocess.check_output([str(runtime), '-c', command], text=True, timeout=60))


def analyze_timeline(source, settings, *, with_vocals=False, profile=LEGACY_PROFILE, expected_content_hash=None):
    if profile not in (LEGACY_PROFILE, FOUNDATION_PROFILE):
        raise ValueError('Unknown analysis profile')
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
    if profile == FOUNDATION_PROFILE:
        config.update(analysis_profile=profile, evidence_version=EVIDENCE_VERSION,
                      adapter_version='cpu-models-3-float-relative-vocals',
                      vocal_bin_seconds=.5, quieter_ratio_limit=.15, master_rms_floor=1e-6)
        modules = ['scripts/timeline_worker.py', 'backend/app/audio/analysis_evidence.py',
                   'backend/app/audio/timeline_features.py', 'backend/app/audio/bar_evidence.py']
        config['implementation'] = {name: sha256(PROJECT_ROOT/name) for name in modules}
        config['ffmpeg_build'] = subprocess.check_output([settings.ffmpeg, '-version'], text=True, timeout=30).splitlines()[0]
        if with_vocals:
            base = storage.root/'separation'
            model = config['separator']
            if sha256(base/'models'/model['filename']) != model['sha256']:
                raise ValueError('Separation model changed')
            config['separator_packages'] = runtime_packages(separator_runtime(base),
                ['onnxruntime', 'onnxruntime-directml', 'numpy', 'scipy', 'soundfile'])
            config['separator_adapter_sha256'] = sha256(PROJECT_ROOT/'backend/app/audio/mdx.py')
            config['separator_cache_sha256'] = sha256(PROJECT_ROOT/'backend/app/audio/separation_cache.py')
    digest = sha256(source)
    if expected_content_hash is not None and digest != expected_content_hash:
        raise ValueError('Registered source changed before analysis')
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
    if prediction.get('config') != config or prediction.get('content_hash') != digest:
        raise ValueError('Worker returned evidence for a different source/configuration')
    return store.save(source, prediction, config)


def analyze_registered_pair(workflow, track_ids, *, with_vocals=True):
    """Foundation for any ordered catalog pair; planning/rendering are later steps."""
    from backend.app.audio.analysis_evidence import foundation_evidence
    if not isinstance(track_ids, (list, tuple)) or len(track_ids) != 2:
        raise ValueError('Choose two registered songs')
    catalog = {row['id']: row for row in workflow.catalog(internal=True)}
    if any(identity not in catalog for identity in track_ids):
        raise ValueError('A selected song is no longer registered')
    sources = [catalog[identity] for identity in track_ids]
    for source in sources:
        if sha256(Path(source['path'])) != source['content_hash']:
            raise ValueError('Registered source changed')
    records = []
    store = TimelineStore(workflow.storage.root)
    for source in sources:
        keys = analyze_timeline(source['path'], workflow.settings, with_vocals=with_vocals,
                                profile=FOUNDATION_PROFILE, expected_content_hash=source['content_hash'])
        record = store.get(**keys)
        if record['prediction']['content_hash'] != source['content_hash']:
            raise ValueError('Registered source changed during analysis')
        records.append({'catalog_id': source['id'], 'timeline': record,
                        'evidence': foundation_evidence(record)})
    return {'version': EVIDENCE_VERSION, 'sources': records}
