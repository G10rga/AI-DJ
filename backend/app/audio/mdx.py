"""Optional local UVR MDX ONNX inference; no training or remote audio service.

Model metadata: https://github.com/TRvlvr/application_data
Model distribution: https://github.com/TRvlvr/model_repo
Transforms follow the model's centered, unnormalized Hann STFT contract.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.fft import rfft, irfft

VERSION = 'mdx-local-1'


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def stft(samples, n_fft, hop):
    window = np.hanning(n_fft + 1)[:-1].astype(np.float32)
    padded = np.pad(samples, ((0, 0), (n_fft//2, n_fft//2)), mode='reflect')
    frames = np.lib.stride_tricks.sliding_window_view(padded, n_fft, axis=-1)[:, ::hop]
    return rfft(frames * window, axis=-1).transpose(0, 2, 1)


def istft(spectrum, n_fft, hop, length):
    window = np.hanning(n_fft + 1)[:-1].astype(np.float32)
    frames = irfft(spectrum.transpose(0, 2, 1), n=n_fft, axis=-1) * window
    output = np.zeros((spectrum.shape[0], n_fft + hop*(frames.shape[1]-1)), dtype=np.float32)
    weights = np.zeros(output.shape[1], dtype=np.float32)
    for index in range(frames.shape[1]):
        offset = index * hop
        output[:, offset:offset+n_fft] += frames[:, index]
        weights[offset:offset+n_fft] += window**2
    output /= np.maximum(weights, 1e-10)
    return output[:, n_fft//2:n_fft//2+length]


def pack_spectrum(spectrum, bins):
    selected = spectrum[:, :bins]
    return np.stack((selected.real, selected.imag), axis=1).reshape(1, 4, bins, selected.shape[-1]).astype(np.float32)


def unpack_spectrum(packed, n_fft):
    components = packed.reshape(2, 2, packed.shape[-2], packed.shape[-1])
    spectrum = components[:, 0] + 1j * components[:, 1]
    return np.pad(spectrum, ((0, 0), (0, n_fft//2+1-spectrum.shape[1]), (0, 0)))


class MDXSeparator:
    def __init__(self, model_dir):
        import onnxruntime as ort
        model_dir = Path(model_dir)
        self.metadata = json.loads((model_dir / 'selected_model.json').read_text(encoding='utf-8'))
        path = model_dir / self.metadata['filename']
        if sha256_file(path) != self.metadata['sha256']:
            raise ValueError('Separation model hash differs from its recorded metadata')
        parameters = self.metadata['parameters']
        if parameters['primary_stem'] != 'Instrumental':
            raise ValueError('This adapter requires an instrumental-output MDX model')
        self.n_fft = int(parameters['mdx_n_fft_scale_set'])
        self.bins = int(parameters['mdx_dim_f_set'])
        self.frames = 2**int(parameters['mdx_dim_t_set'])
        self.compensate = float(parameters['compensate'])
        self.hop = 1024
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        providers=['CPUExecutionProvider']
        if 'DmlExecutionProvider' in ort.get_available_providers():
            options.enable_mem_pattern=False
            options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
            providers=['DmlExecutionProvider','CPUExecutionProvider']
        self.session = ort.InferenceSession(str(path), sess_options=options, providers=providers)
        shape = self.session.get_inputs()[0].shape
        if shape[1:] != [4, self.bins, self.frames]:
            raise ValueError('Model shape does not match the recorded STFT configuration')

    def separate(self, samples, progress=print):
        if samples.ndim != 2 or samples.shape[0] != 2 or samples.shape[1] > 44100 * 180:
            raise ValueError('Separate one stereo excerpt of at most 180 seconds at a time')
        if not np.all(np.isfinite(samples)):
            raise ValueError('Invalid source samples')
        length = samples.shape[1]
        chunk_size = self.hop * (self.frames - 1)
        trim = self.n_fft // 2
        valid = chunk_size - 2*trim
        stride = valid // 2
        padded = np.pad(samples, ((0, 0), (trim, chunk_size)))
        output = np.zeros((2, length + valid), dtype=np.float32)
        weights = np.zeros(length + valid, dtype=np.float32)
        blend = np.hanning(valid + 2)[1:-1].astype(np.float32)
        starts = range(0, length, stride)
        for index, start in enumerate(starts):
            chunk = padded[:, start:start+chunk_size]
            spectrum = stft(chunk, self.n_fft, self.hop)
            packed = pack_spectrum(spectrum, self.bins)
            packed[:, :, :3] = 0
            predicted = self.session.run(None, {self.session.get_inputs()[0].name: packed})[0]
            instrumental = istft(unpack_spectrum(predicted, self.n_fft), self.n_fft, self.hop, chunk_size)
            instrumental = instrumental[:, trim:trim+valid] * self.compensate
            if not np.all(np.isfinite(instrumental)):
                raise ValueError('Model produced invalid samples')
            output[:, start:start+valid] += instrumental * blend
            weights[start:start+valid] += blend
            progress(f'Separation chunk {index+1}/{len(starts)}', flush=True)
        instrumental = output[:, :length] / np.maximum(weights[:length], 1e-12)
        # Subtraction preserves source timing and exact mixture reconstruction.
        vocals = samples - instrumental
        return instrumental, vocals
