"""Timing and reconstruction checks; musical quality still needs listening."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

AVAILABLE = all(importlib.util.find_spec(name) for name in ('numpy', 'scipy', 'soundfile'))
if AVAILABLE:
    import numpy as np
    import soundfile as sf
    from backend.app.audio.mdx import stft, istft, pack_spectrum, unpack_spectrum
    from backend.app.audio.stem_mix import vocal_schedule, stem_pair_graph
    from backend.app.audio.probe import run_audio, AudioError
    from backend.app.audio.phase import check_overlap_windows
    from backend.app.config import Settings
    from scripts.synthetic_audio import write_fixture


@unittest.skipUnless(AVAILABLE, 'Install the audio dependencies')
class StemMixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = Settings.from_env()
        try:
            run_audio([cls.settings.ffmpeg, '-version'], timeout=15)
        except AudioError as exc:
            raise unittest.SkipTest(str(exc))
        parent = cls.settings.data_root/'tmp'
        parent.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(dir=parent, prefix='test-stems-')
        cls.root = Path(cls.temporary.name)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_model_stft_contract_round_trip(self):
        rng = np.random.default_rng(13)
        for size, hop, frames in ((512, 128, 32), (6144, 1024, 256)):
            samples = rng.normal(0, .1, (2, hop*(frames-1))).astype(np.float32)
            spectrum = stft(samples, size, hop)
            packed = pack_spectrum(spectrum, size//2+1)
            self.assertEqual(packed.shape, (1, 4, size//2+1, frames))
            restored = istft(unpack_spectrum(packed, size), size, hop, samples.shape[1])
            np.testing.assert_allclose(restored, samples, atol=3e-7)

    def test_vocal_entry_uses_gap_before_next_line(self):
        rate = 44100
        time = np.arange(24*rate)/rate
        paths = []
        for name, frequency, spans in [('a', 700, [(.5, 13), (17, 22)]),
                                       ('b', 1100, [(.5, 4), (9, 13), (16, 23)])]:
            active = np.zeros(len(time))
            for start, end in spans:
                active[round(start*rate):round(end*rate)] = 1
            samples = .1*np.sin(2*np.pi*frequency*time)*active
            path = self.root/f'voice-{name}.wav'
            sf.write(path, np.column_stack((samples, samples)), rate, subtype='FLOAT')
            paths.append(path)
        schedule = vocal_schedule(*paths, 8, 16, 120)
        a_end = schedule['outgoing_fade_start_seconds']+schedule['outgoing_fade_duration_seconds']
        b_start = schedule['incoming_fade_start_seconds']
        self.assertAlmostEqual(schedule['outgoing_fade_duration_seconds'], 8)
        self.assertLess(schedule['outgoing_fade_start_seconds'], 6)
        self.assertGreater(a_end, 13)
        self.assertLess(a_end, 14)
        self.assertGreater(b_start, a_end)
        self.assertAlmostEqual(b_start, 17, delta=.1)
        self.assertAlmostEqual(schedule['incoming_fade_duration_seconds'], 8)
        self.assertIn('gap', schedule['outgoing_reason'])
        self.assertIn('gap', schedule['incoming_reason'])

    def test_vocal_fades_preserve_instrumental_bed_and_tail(self):
        rate = 44100
        time = np.arange(24*rate)/rate
        signals = [(.18*np.sin(2*np.pi*55*time)+.03*np.sin(2*np.pi*400*time)+.02*np.sin(2*np.pi*4000*time)),
                   (.18*np.sin(2*np.pi*90*time)+.03*np.sin(2*np.pi*600*time)+.02*np.sin(2*np.pi*6000*time)),
                   .08*np.sin(2*np.pi*700*time),
                   .08*np.sin(2*np.pi*1100*time)+.08*np.sin(2*np.pi*3000*time)]
        command = [self.settings.ffmpeg, '-v', 'error', '-nostdin']
        for index, signal in enumerate(signals):
            path = self.root/f'stem-{index}.wav'
            sf.write(path, np.column_stack((signal, signal*.9)), rate, subtype='FLOAT')
            command += ['-i', str(path)]
        schedule = {'outgoing_fade_start_seconds': 13, 'outgoing_fade_duration_seconds': 1,
                    'incoming_fade_start_local_seconds': 8, 'incoming_fade_duration_seconds': 1}
        graph, _ = stem_pair_graph((1, 1), 24, 24, 16, 120, 0, schedule)
        output = self.root/'mixed.f32'
        run_audio(command+['-filter_complex', graph, '-map', '[out]', '-f', 'f32le', str(output)])
        samples = np.fromfile(output, dtype='<f4').reshape(-1, 2)
        self.assertAlmostEqual(len(samples)/rate, 32, delta=.002)
        def amplitude(start, frequency):
            segment = samples[round(start*rate):round((start+1)*rate), 0]
            return float(2*abs(np.mean(segment*np.exp(-2j*np.pi*frequency*np.arange(rate)/rate))))
        self.assertGreater(amplitude(10, 700), .07)
        self.assertLess(amplitude(10, 1100), .001)
        self.assertLess(amplitude(14.1, 700), .001)
        self.assertLess(amplitude(14.1, 1100), .001)
        self.assertGreater(amplitude(14.1, 55), .14)
        self.assertGreater(amplitude(18, 1100), .07)
        self.assertLess(amplitude(18, 700), .001)
        self.assertGreater(amplitude(28, 90), .14)
        self.assertGreater(amplitude(28, 1100), .07)
        # Longer vocal fades must remain gradual, and incoming brightness must
        # open over time without fading the instrumental bass underneath.
        gradual = {'outgoing_fade_start_seconds': 8, 'outgoing_fade_duration_seconds': 8,
                   'incoming_fade_start_local_seconds': 10, 'incoming_fade_duration_seconds': 8,
                   'outgoing_curve': 'qsin', 'incoming_curve': 'hsin',
                   'vocal_eq': {'split_hz': 1800}}
        graph, _ = stem_pair_graph((1, 1), 24, 24, 16, 120, 0, gradual, blend_profile='long_groove')
        output = self.root/'gradual-mixed.f32'
        run_audio(command+['-filter_complex', graph, '-map', '[out]', '-f', 'f32le', str(output)])
        samples = np.fromfile(output, dtype='<f4').reshape(-1, 2)
        self.assertGreater(amplitude(11, 700), .05)
        self.assertGreater(amplitude(15, 700), .003)
        self.assertLess(amplitude(15, 700), .025)
        self.assertGreater(amplitude(14.1, 55), .14)
        # The long profile starts trading instrumental mids before the short
        # profile would, while the outgoing groove is still established.
        self.assertGreater(amplitude(13, 600), .0015)
        self.assertGreater(amplitude(13, 400), .02)
        self.assertGreater(amplitude(20, 600), .025)
        self.assertLess(amplitude(17, 700), .001)
        early = amplitude(19, 3000)/amplitude(19, 1100)
        late = amplitude(27, 3000)/amplitude(27, 1100)
        self.assertLess(early, .4)
        self.assertGreater(late, .9)
        self.assertGreater(amplitude(28, 90), .14)

    def test_overlapping_or_invalid_vocal_fades_rejected(self):
        schedule = {'outgoing_fade_start_seconds': 13, 'outgoing_fade_duration_seconds': 4,
                    'incoming_fade_start_local_seconds': 8, 'incoming_fade_duration_seconds': 1}
        with self.assertRaises(ValueError):
            stem_pair_graph((1, 1), 24, 24, 16, 120, 0, schedule)
        schedule['outgoing_fade_start_seconds'] = float('nan')
        with self.assertRaises(ValueError):
            stem_pair_graph((1, 1), 24, 24, 16, 120, 0, schedule)

    def test_window_checks_detect_late_beat_slip(self):
        reference = self.root/'window-reference.wav'
        shifted = self.root/'window-shifted.wav'
        write_fixture(reference, bpm=120, seconds=24)
        samples, rate = sf.read(reference, dtype='float32', always_2d=True)
        edited = samples.copy()
        boundary, delay = 12*rate, round(.1*rate)
        edited[boundary:] = samples[boundary-delay:len(samples)-delay]
        sf.write(shifted, edited, rate, subtype='PCM_16')
        checks = check_overlap_windows(reference, reference, 0, 24, 120, window=8)
        self.assertEqual(len(checks), 3)
        # An early-only check accepts this file; a later window must reject it.
        early = check_overlap_windows(reference, shifted, 0, 8, 120, window=8)
        self.assertEqual(len(early), 1)
        with self.assertRaises(ValueError):
            check_overlap_windows(reference, shifted, 0, 24, 120, window=8)
