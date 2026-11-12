"""Real float DSP checks, including over-full-scale peaks and source boundaries."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import soundfile as sf

from backend.app.audio.float_prepare import (
    RATE, prepare_float_excerpt, preparation_gain, apply_constant_gain,
)
from backend.app.audio.probe import AudioError, run_audio
from backend.app.config import Settings


class FloatPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = Settings.from_env()
        try:
            run_audio([cls.settings.ffmpeg, '-version'])
            run_audio([cls.settings.ffprobe, '-version'])
        except AudioError as exc:
            raise unittest.SkipTest(str(exc))

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source.wav'
        t = np.arange(RATE * 8) / RATE
        # Independent channels, both including peaks beyond PCM16 range.
        self.samples = np.column_stack((1.5*np.sin(2*np.pi*440*t),
                                        1.2*np.sin(2*np.pi*660*t))).astype('float32')
        sf.write(self.source, self.samples, RATE, subtype='FLOAT')

    def prepare(self, name='prepared.wav', start=2., seconds=3., target=120., **kwargs):
        output = self.root / name
        report = prepare_float_excerpt(self.source, output, start, seconds, 120.,
                                       target, self.settings, **kwargs)
        return output, report

    def test_native_and_stretched_peaks_survive_then_receive_fixed_gain(self):
        for target in (120., 124.8):
            with self.subTest(target=target):
                output, report = self.prepare(name=f'{target}.wav', target=target)
                data, rate = sf.read(output, dtype='float32', always_2d=True)
                self.assertEqual(data.shape, (3*RATE, 2))
                self.assertEqual(rate, RATE)
                self.assertEqual(sf.info(output).subtype, 'FLOAT')
                self.assertTrue(np.isfinite(data).all())
                self.assertGreater(float(np.abs(data).max()), 1.3)
                self.assertFalse(np.array_equal(data[:, 0], data[:, 1]))
                self.assertGreater(report['sample_peak_before_gain'], 1.3)
                self.assertEqual(report['decoded_source_interval'][0], 0.)
                gain = preparation_gain(-12., 4.)
                apply_constant_gain(output, gain)
                gained, _ = sf.read(output, dtype='float32', always_2d=True)
                np.testing.assert_allclose(gained, data * 10**(gain/20), atol=2e-7)
                self.assertLess(float(np.abs(gained).max()), 1.)
                # Stretch keeps pitch, while the time mapping follows the tempo ratio.
                values = gained[RATE//2:-RATE//2, 0]
                spectrum = abs(np.fft.rfft(values*np.hanning(len(values))))
                frequency = np.fft.rfftfreq(len(values), 1/RATE)[spectrum.argmax()]
                self.assertAlmostEqual(frequency, 440., delta=2.)
                self.assertAlmostEqual(report['source_interval'][1], 2+3*target/120)

    def test_padding_is_explicit_and_only_before_source_beginning(self):
        with self.assertRaisesRegex(ValueError, 'inaudible'):
            self.prepare(start=-1.)
        output, report = self.prepare(start=-1., inaudible_before=1.)
        data, _ = sf.read(output, always_2d=True)
        self.assertTrue(np.all(data[:RATE] == 0))
        self.assertGreater(float(np.abs(data[RATE+1000:]).max()), 1.)
        self.assertEqual(report['leading_padding_frames'], RATE)
        self.assertEqual(report['source_interval'], [0., 2.])

    def test_real_loudness_gain_stages_float_peaks_safely_before_encoding(self):
        from backend.app.auditions import loudness
        output, report = self.prepare(target=124.8)
        self.assertGreater(report['sample_peak_before_gain'], 1.)
        measured = loudness(output, self.settings)
        gain = preparation_gain(measured['integrated_lufs'], measured['true_peak_dbfs'])
        apply_constant_gain(output, gain)
        encoded = self.root/'safe.mp3'
        run_audio([self.settings.ffmpeg, '-v', 'error', '-nostdin', '-i', str(output),
                   '-c:a', 'libmp3lame', '-b:a', '256k', str(encoded)])
        final = loudness(encoded, self.settings)
        self.assertLessEqual(final['true_peak_dbfs'], -1.)
        self.assertAlmostEqual(final['integrated_lufs'], -20., delta=.5)

    def test_bad_bounds_and_existing_artifacts_fail_without_overwrite(self):
        for bounds in ({'start':7.}, {'start':float('nan')}, {'seconds':0.},
                       {'context_seconds':-1.}, {'target':140.},
                       {'start':-4., 'inaudible_before':3.}):
            with self.subTest(bounds=bounds), self.assertRaises(ValueError):
                self.prepare(**bounds)
        output = self.root / 'prepared.wav'
        output.write_bytes(b'preserve reviewed artifact')
        with self.assertRaisesRegex(ValueError, 'fresh'):
            self.prepare()
        self.assertEqual(output.read_bytes(), b'preserve reviewed artifact')

    def test_short_native_decode_is_rejected_instead_of_padded(self):
        def short_decode(args):
            sf.write(args[-1], self.samples[:RATE], RATE, subtype='FLOAT')
        with patch('backend.app.audio.float_prepare.run_audio', side_effect=short_decode):
            with self.assertRaisesRegex(AudioError, 'shorter'):
                self.prepare()
        self.assertFalse((self.root/'prepared.wav').exists())

    def test_nonfinite_decoded_audio_and_measurements_fail(self):
        def invalid_decode(args):
            data = self.samples.copy()
            data[3*RATE] = np.nan
            sf.write(args[-1], data, RATE, subtype='FLOAT')
        with patch('backend.app.audio.float_prepare.run_audio', side_effect=invalid_decode):
            with self.assertRaisesRegex(AudioError, 'Invalid'):
                self.prepare()
        self.assertFalse((self.root/'prepared.wav').exists())
        for measurements in ((float('nan'), 0.), (-20., float('-inf'))):
            with self.assertRaises(ValueError):
                preparation_gain(*measurements)


if __name__ == '__main__':
    unittest.main()
