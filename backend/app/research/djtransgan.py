"""Isolated, strict adapter for the pinned author's pretrained DJtransGAN.

No app database writes, training, recipe fallback, or production activation.
Imports torch only in the separate research runtime.
"""
import json
from pathlib import Path
import shutil
import sys
import hashlib
import zipfile

from scripts.setup_dj_benchmarks import digest, SOURCES

CHECKPOINT_SHA256 = '495987d70bd873fb94838b3af705be85d368a6639659f2ffcc2b05a9740e8fd2'
CHECKPOINT_URL = 'https://drive.google.com/uc?id=1L1TXWY7YOJEaozrFr4MqOZ5aXwJ0_o31'
VERSION = 'djtransgan-research-1'

FRONTEND_UTILS = '''from torchaudio.transforms import AmplitudeToDB, MelScale
from djtransgan.config import settings
from djtransgan.frontend.torchlibrosa import TorchlibrosaSTFT

def get_amp2db_func(power=1):
    return AmplitudeToDB(stype=['amplitude', 'power'][int(power)-1])

def get_stft_func(**kwargs):
    if kwargs.pop('stft_type', 'torchlibrosa') != 'torchlibrosa':
        raise ValueError('Research adapter supports only checkpoint torchlibrosa frontend')
    return TorchlibrosaSTFT(**kwargs)

def get_mel_func():
    return MelScale(n_mels=settings.N_MELS, n_stft=settings.N_FFT//2+1, sample_rate=settings.SR)
'''


def prepare_adapter(root):
    root = Path(root)
    manifest = json.loads((root/'sources.json').read_text(encoding='utf-8'))
    source = manifest['sources']['djtransgan']
    if source['commit'] != SOURCES['djtransgan'][1]:
        raise ValueError('Unexpected DJtransGAN source revision')
    original = Path(source['directory'])/'djtransgan'
    archive = root/'downloads'/('djtransgan-'+source['commit']+'.zip')
    if digest(archive) != source['archive_sha256']:
        raise ValueError('Pinned source archive changed')
    # Verify executable source against the archived commit before importing it.
    with zipfile.ZipFile(archive) as zipped:
        for path in original.rglob('*.py'):
            member = Path(source['directory']).name+'/djtransgan/'+path.relative_to(original).as_posix()
            if hashlib.sha256(zipped.read(member)).hexdigest() != digest(path):
                raise ValueError('Extracted model source changed: '+str(path))
    destination = root/'compat'/VERSION/'djtransgan'
    # Refresh the isolated copy; never alter the pinned original.
    shutil.copytree(original, destination, dirs_exist_ok=True)
    changes = {
        'utils/__init__.py': 'from djtransgan.utils.utils import *\n',
        'frontend/__init__.py': 'from djtransgan.frontend.torchlibrosa import *\nfrom djtransgan.frontend.utils import *\n',
        'frontend/utils.py': FRONTEND_UTILS,
    }
    hashes = {}
    for relative, content in changes.items():
        target = destination/relative
        target.write_text(content, encoding='utf-8')
        hashes[relative] = {'original_sha256': digest(original/relative), 'adapted_sha256': digest(target)}
    provenance = {'adapter_version': VERSION, 'source': source, 'changes': hashes,
                  'reason': 'Remove eager imports of unused frontends, plotting and preprocessing; selected architecture unchanged',
                  'implementation_sha256': digest(__file__)}
    (destination.parent/'adapter.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
    sys.path.insert(0, str(destination.parent))
    return provenance


def verify_checkpoint(root):
    checkpoint = Path(root)/'checkpoints/djtransgan_minmax.pt'
    if digest(checkpoint) != CHECKPOINT_SHA256:
        raise ValueError('Pretrained checkpoint SHA256 mismatch')
    return checkpoint


def load_model(root):
    checkpoint = verify_checkpoint(root)
    import torch
    torch.set_num_threads(2)
    state = torch.load(checkpoint, map_location='cpu', weights_only=True)
    if not isinstance(state, dict) or not state or any(not isinstance(k, str) or not isinstance(v, torch.Tensor) for k,v in state.items()):
        raise ValueError('Checkpoint must contain a tensor-only state dictionary')
    if any(not torch.isfinite(v).all() for v in state.values()):
        raise ValueError('Checkpoint contains nonfinite tensors')
    provenance = prepare_adapter(root)
    from djtransgan.model import get_generator
    torch.manual_seed(0)
    model = get_generator()
    model.load_state_dict(state, strict=True)
    model.eval()
    provenance['checkpoint'] = {'url': CHECKPOINT_URL, 'sha256': CHECKPOINT_SHA256,
                                'hash_origin': 'locally observed author download; not publisher-signed',
                                'state_keys': len(state), 'strict': True, 'weights_only': True}
    return model, provenance
