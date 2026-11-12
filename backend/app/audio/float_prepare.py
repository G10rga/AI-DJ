"""Context-aware preparation for the improved pipeline; never quantize audible PCM.

Source time at output t is source_at_zero + t * tempo_ratio. Negative source
time is allowed only when the caller declares that output interval inaudible.
Legacy preparation remains unchanged until the new pipeline is selected.
"""
import math
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import soundfile as sf

from .mdx import sha256_file
from .probe import AudioError, probe, run_audio
from .stretch import tempo_ratio

VERSION = 'context-stereo-float-1'
RATE = 44100


def preparation_gain(integrated_lufs, true_peak_dbfs, *, target_lufs=-20., ceiling_dbfs=-3.):
    """One fixed gain, constrained by measured true peak; no dynamic normalization."""
    if not all(math.isfinite(v) for v in (integrated_lufs, true_peak_dbfs, target_lufs, ceiling_dbfs)):
        raise ValueError('Loudness measurements and targets must be finite')
    return min(target_lufs - integrated_lufs, ceiling_dbfs - true_peak_dbfs)


def apply_constant_gain(path, gain_db):
    """Apply gain to a float WAV with bounded memory and atomic replacement."""
    path = Path(path)
    if not math.isfinite(gain_db) or not -120 <= gain_db <= 60:
        raise ValueError('Invalid preparation gain')
    with TemporaryDirectory(dir=path.parent, prefix='float-gain-') as directory:
        staged = Path(directory) / 'gained.wav'
        with sf.SoundFile(path) as source:
            if source.subtype != 'FLOAT' or source.channels != 2 or source.samplerate != RATE:
                raise AudioError('Expected stereo 44100 Hz float WAV')
            with sf.SoundFile(staged, 'w', samplerate=RATE, channels=2, subtype='FLOAT') as output:
                for block in source.blocks(blocksize=65536, dtype='float32', always_2d=True):
                    block *= 10 ** (gain_db / 20)
                    if not np.isfinite(block).all():
                        raise AudioError('Non-finite prepared audio')
                    output.write(block)
        staged.replace(path)


def prepare_float_excerpt(source, output, source_at_zero, seconds, source_bpm,
                          target_bpm, settings, *, context_seconds=8., inaudible_before=0.):
    """Decode/stretch once with real context, then crop a continuous float stream.

    Context is in output seconds and is bounded by the actual file. No padding
    is used to repair short decodes or fabricate audible source samples.
    Output must be a fresh path, preserving prior renders and reviewed evidence.
    """
    source, output = Path(source), Path(output)
    ratio = tempo_ratio(source_bpm, target_bpm)
    if not all(math.isfinite(v) for v in (source_at_zero, seconds, context_seconds, inaudible_before)):
        raise ValueError('Non-finite preparation bounds')
    if seconds <= 0 or context_seconds < 0 or not 0 <= inaudible_before <= seconds:
        raise ValueError('Invalid preparation bounds')
    if output.exists() or source.resolve() == output.resolve():
        raise ValueError('Preparation requires a fresh output path')
    duration = probe(source, settings).duration
    source_end = source_at_zero + seconds * ratio
    if source_end > duration + 1e-7 or source_end <= 0:
        raise ValueError('Audible excerpt exceeds source bounds')
    padding_seconds = max(0., -source_at_zero / ratio)
    if padding_seconds > inaudible_before + 1e-9:
        raise ValueError('Pre-file padding must be explicitly inaudible')
    digest = sha256_file(source)
    seek = max(0., source_at_zero - context_seconds * ratio)
    decode_end = min(duration, source_end + context_seconds * ratio)
    frames = round(seconds * RATE)
    leading = round(padding_seconds * RATE)
    crop = round(max(0., source_at_zero - seek) / ratio * RATE)
    if frames <= leading:
        raise ValueError('Excerpt contains no source audio')
    with TemporaryDirectory(dir=output.parent, prefix='float-prepare-') as directory:
        stretched = Path(directory) / 'context.wav'
        run_audio([settings.ffmpeg, '-v', 'error', '-nostdin', '-ss', str(seek),
                   '-t', str(decode_end - seek), '-i', str(source), '-map', '0:a:0', '-vn',
                   '-af', f'aresample={RATE},rubberband=tempo={ratio:.10f}:pitch=1:channels=together',
                   '-ac', '2', '-ar', str(RATE), '-c:a', 'pcm_f32le', str(stretched)])
        staged = Path(directory) / 'prepared.wav'
        peak = 0.
        with sf.SoundFile(stretched) as audio:
            if audio.channels != 2 or audio.samplerate != RATE or audio.subtype != 'FLOAT':
                raise AudioError('Invalid stretched float format')
            if crop + frames - leading > len(audio):
                raise AudioError('Stretched source is shorter than the requested audible interval')
            audio.seek(crop)
            with sf.SoundFile(staged, 'w', samplerate=RATE, channels=2, subtype='FLOAT') as result:
                remaining = leading
                while remaining:
                    count = min(65536, remaining)
                    result.write(np.zeros((count, 2), dtype=np.float32))
                    remaining -= count
                remaining = frames - leading
                while remaining:
                    block = audio.read(min(65536, remaining), dtype='float32', always_2d=True)
                    if not len(block) or not np.isfinite(block).all():
                        raise AudioError('Invalid or incomplete stretched source')
                    peak = max(peak, float(np.abs(block).max()))
                    result.write(block)
                    remaining -= len(block)
        if sha256_file(source) != digest:
            raise AudioError('Source changed during preparation')
        # Do not overwrite a result that appeared while decoding.
        with output.open('xb') as destination, staged.open('rb') as prepared:
            import shutil
            shutil.copyfileobj(prepared, destination)
    return {'version': VERSION, 'source_path': str(source), 'source_sha256': digest,
            'source_at_output_zero': source_at_zero, 'tempo_ratio': ratio,
            'duration_seconds': frames / RATE, 'sample_rate': RATE, 'channels': 2,
            'source_interval': [max(0., source_at_zero), source_end],
            'decoded_source_interval': [seek, decode_end], 'context_seconds': context_seconds,
            'leading_padding_frames': leading, 'inaudible_before_seconds': inaudible_before,
            'sample_peak_before_gain': peak, 'gain_db': 0., 'prepared_sha256': sha256_file(output)}
