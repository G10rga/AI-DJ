"""CPU-only pretrained musical analysis in the isolated timeline environment."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import numpy as np
import soundfile as sf
import torch
from beat_this.inference import Audio2Beats
from backend.app.audio.probe import run_audio
from backend.app.audio.timeline_features import chunk_windows, merge_markers, feature_bins, section_candidates
from backend.app.timelines import VERSION, validate_timeline, derive_bars
from scripts.setup_timeline import sha256
from backend.app.audio.analysis_evidence import PROFILE, VERSION as EVIDENCE_VERSION, vocal_bins, build_evidence


def decode(source, output, start, end, rate, ffmpeg):
    run_audio([ffmpeg, '-v', 'error', '-nostdin', '-ss', str(start), '-t', str(end-start),
               '-i', str(source), '-vn', '-ac', '1', '-ar', str(rate), '-c:a', 'pcm_f32le', str(output)])
    samples, _ = sf.read(output, dtype='float32')
    if not np.all(np.isfinite(samples)):
        raise ValueError('Source contains invalid samples')
    return samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request', type=Path)
    parser.add_argument('result', type=Path)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding='utf-8'))
    root = Path(request['root'])
    os.environ['HF_HOME'] = str(root/'hf-cache')
    os.environ['HF_MODULES_CACHE'] = str(root/'hf-cache/modules')
    os.environ['TORCH_HOME'] = str(root/'torch-cache')
    os.environ['HF_HUB_OFFLINE'] = '1'
    from transformers import AutoConfig, AutoModel, Wav2Vec2FeatureExtractor
    config = request['config']
    foundation = config.get('analysis_profile') == PROFILE
    models = root/'models'
    for group, base in (('mert', models/'mert'), ('beat_this', models)):
        for name, digest in config['models'][group]['files'].items():
            if sha256(base/name) != digest:
                raise ValueError('Model file changed: '+name)
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    tracker = Audio2Beats(checkpoint_path=str(models/'final0.ckpt'), device='cpu', dbn=False)
    model_config = AutoConfig.from_pretrained(str(models/'mert'), trust_remote_code=True, local_files_only=True)
    model = AutoModel.from_config(model_config, trust_remote_code=True)
    weights = torch.load(models/'mert/pytorch_model.bin', map_location='cpu', weights_only=True)
    # PyTorch migrated weight_norm g/v to parametrizations. The tensors are
    # identical, but Transformers 4.38 silently skips these old names otherwise.
    weights = {name.replace('pos_conv_embed.conv.weight_g', 'pos_conv_embed.conv.parametrizations.weight.original0')
                   .replace('pos_conv_embed.conv.weight_v', 'pos_conv_embed.conv.parametrizations.weight.original1'): value
               for name, value in weights.items()}
    model.load_state_dict(weights, strict=True)
    del weights
    model.eval()
    model.requires_grad_(False)
    processor = Wav2Vec2FeatureExtractor.from_pretrained(str(models/'mert'), local_files_only=True)
    duration = request['duration']
    beat_chunks, down_chunks, features, embeddings, vocals = [], [], [], [], []
    vocal_chunks, analysis_chunks = [], []
    with tempfile.TemporaryDirectory(dir=request['tmp_root'], prefix='timeline-worker-') as work:
        work = Path(work)
        for index, (start, end, left, right) in enumerate(chunk_windows(duration, config['core_seconds'], config['context_seconds'])):
            print(f'Timeline {start:.0f}-{end:.0f}s / {duration:.0f}s', flush=True)
            samples = decode(request['source'], work/f'context-{index}.wav', left, right, 24000, request['ffmpeg'])
            with torch.inference_mode():
                beats, downs = tracker(samples, 24000)
            beat_chunks.append([float(t)+left for t in beats if start <= float(t)+left < end])
            down_chunks.append([float(t)+left for t in downs if start <= float(t)+left < end])
            if foundation:
                analysis_chunks.append({'index': index, 'core_interval': [start, end], 'context_interval': [left, right],
                    'beats': [float(t)+left for t in beats], 'downbeats': [float(t)+left for t in downs]})
            core = samples[round((start-left)*24000):round((end-left)*24000)]
            features.extend(feature_bins(core, 24000, start))
            for offset in range(0, len(core), 5*24000):
                piece = core[offset:offset+5*24000]
                if len(piece) < 2400:
                    continue
                # Pad sub-second tails for the convolutional frontend; retain real interval bounds.
                model_piece = np.pad(piece, (0, max(0, 24000-len(piece))))
                inputs = processor(model_piece, sampling_rate=24000, return_tensors='pt')
                with torch.inference_mode():
                    vector = model(**inputs).last_hidden_state.mean(dim=1)[0].cpu().numpy()
                embeddings.append({'start': start+offset/24000, 'end': min(end, start+(offset+len(piece))/24000),
                                   'vector': vector.astype(float).tolist()})
            if request.get('with_vocals'):
                from backend.app.config import Settings
                from backend.app.storage import Storage
                from backend.app.rendering import separate_local
                stereo = work/f'stereo-{index}.wav'
                run_audio([request['ffmpeg'], '-v', 'error', '-nostdin', '-ss', str(left), '-t', str(right-left),
                           '-i', request['source'], '-ac', '2', '-ar', '44100', '-c:a',
                           'pcm_f32le' if foundation else 'pcm_s16le', str(stereo)])
                settings = Settings(data_root=Path(request['data_root']), ffmpeg=request['ffmpeg'])
                manifest = separate_local(stereo, work/f'stems-{index}.json', settings, Storage(settings.data_root), verified=foundation)
                if foundation:
                    if (manifest['source_sha256'] != sha256(stereo) or manifest['model'] != config['separator']
                            or manifest['configuration']['packages'] != config['separator_packages']
                            or manifest['configuration']['adapter_sha256'] != config['separator_adapter_sha256']
                            or manifest['configuration']['cache_sha256'] != config['separator_cache_sha256']):
                        raise ValueError('Separator returned mismatched source/model/runtime provenance')
                    for name in ('instrumental', 'vocals'):
                        if sha256(Path(manifest[name])) != manifest['stem_sha256'][name]:
                            raise ValueError('Separated stem changed before activity analysis')
                    master, rate = sf.read(stereo, dtype='float32', always_2d=True)
                    vocal, vocal_rate = sf.read(manifest['vocals'], dtype='float32', always_2d=True)
                    if rate != vocal_rate or len(master) != manifest['frames']:
                        raise ValueError('Separation timing mismatch')
                    vocals.extend(vocal_bins(vocal, master, rate, left, start, end, chunk_index=index))
                    vocal_chunks.append({'index': index, 'core_interval': [start, end],
                        'source_offset_seconds': left, 'context_source_interval': [left, left+len(master)/rate],
                        'original_sha256': request['content_hash'], 'context_sha256': manifest['source_sha256'],
                        'stem_sha256': manifest['stem_sha256'], 'configuration': manifest['configuration'],
                        'sample_rate': rate, 'frames': len(master), 'reconstruction_error': manifest['reconstruction_error']})
                else:
                    with sf.SoundFile(manifest['vocals']) as audio:
                        for t in np.arange(start, end, .5):
                            audio.seek(round((float(t)-left)*audio.samplerate))
                            block = audio.read(round(min(.5, end-float(t))*audio.samplerate), dtype='float32', always_2d=True)
                            vocals.append({'start': float(t), 'end': min(end, float(t)+.5), 'rms': float(np.sqrt(np.mean(block**2)))})
    beats = merge_markers(beat_chunks)
    downs = merge_markers(down_chunks)
    downs = sorted(set(min(beats, key=lambda b: abs(b-t)) for t in downs if beats and min(abs(b-t) for b in beats) <= .05))
    layer = lambda times, provenance: {'times': times, 'confidence': None, 'provenance': provenance}
    if foundation:
        vocal_status = {'available': bool(vocals), 'ratio_limit': .15, 'master_rms_floor': 1e-6,
                        'provenance': 'Verified MDX float stems / original master; per-bin coverage; leakage possible',
                        'phrase_completion': 'unknown'}
    elif vocals:
        levels = np.array([v['rms'] for v in vocals])
        threshold = max(.008, float(np.percentile(levels, 80))*.2)
        for row in vocals:
            row['active'] = row['rms'] >= threshold
        vocal_status = {'available': True, 'threshold_rms': threshold, 'provenance': 'MDX separated-vocal RMS; leakage possible'}
    else:
        vocal_status = {'available': False, 'reason': 'Vocal separation was not requested; vocal gaps are unknown'}
    result = {'version': VERSION, 'content_hash': request['content_hash'], 'duration_seconds': duration,
              'beats': layer(beats, 'Beat This final0; 30s cores with 4s context'),
              'downbeats': layer(downs, 'Beat This final0; matched to detected beats within 50ms'),
              'phrase_boundaries': layer(downs[::8], 'Every eighth predicted downbeat; tentative 8-bar phrase grid'),
              'features': features, 'embeddings': embeddings, 'vocal_activity': vocals, 'vocal_status': vocal_status,
              'feature_provenance': '1s waveform RMS/peak, 30-180Hz bass RMS, onset-count proxy, FFT chroma',
              'config': config, 'sections': section_candidates(embeddings, features, downs),
              'warnings': ['Confidence is uncalibrated; null means unknown, not zero.',
                           'Beat chunk seams and 4/4 assumptions require review; phrases are candidates.',
                           'Energy/transient/chroma evidence does not identify lyrics, drums or named sections.']}
    result['bars'] = derive_bars(result)
    if foundation:
        result['vocal_chunks'] = vocal_chunks
        result['analysis_chunks'] = analysis_chunks
        result['analysis_evidence'] = build_evidence(result)
    validate_timeline(result)
    if sha256(request['source']) != request['content_hash']:
        raise ValueError('Source changed during timeline analysis')
    args.result.write_text(json.dumps(result, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    main()
