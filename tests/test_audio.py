"""Real DSP/subprocess checks with generated audio; no copyrighted fixtures."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
import wave

AUDIO_AVAILABLE = importlib.util.find_spec("numpy") is not None and importlib.util.find_spec("librosa") is not None
if AUDIO_AVAILABLE:
    import numpy as np
    from backend.app.audio.analyze import analyze
    from backend.app.audio.pair import render_pair
    from backend.app.audio.probe import AudioError, probe, run_audio
    from backend.app.audio.stretch import prepare_excerpt, tempo_ratio
    from backend.app.audio.phase import pulse_grid, compare_grids
    from backend.app.audio.recipes import eq_swap_graph
    from backend.app.planning.rhythm import analyze_rhythm
    from backend.app.config import Settings
    from backend.app.storage import Storage
    from scripts.synthetic_audio import write_fixture


@unittest.skipUnless(AUDIO_AVAILABLE, "Install the audio extra to run DSP tests")
class AudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = Settings.from_env()
        try:
            run_audio([cls.settings.ffmpeg, "-version"], timeout=15)
            run_audio([cls.settings.ffprobe, "-version"], timeout=15)
        except AudioError as exc:
            raise unittest.SkipTest(str(exc))
        parent = cls.settings.data_root / "tmp"
        parent.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(dir=parent, prefix="test-audio-")
        cls.root = Path(cls.temporary.name)
        cls.storage = Storage(cls.root / "storage")
        cls.storage.initialize()
        cls.a, cls.b = cls.root / "a.wav", cls.root / "b.wav"
        write_fixture(cls.a)
        write_fixture(cls.b, bpm=124, tone=330)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_probe_and_corrupt_input(self):
        info = probe(self.a, self.settings)
        self.assertAlmostEqual(info.duration, 24, places=3)
        self.assertEqual(info.channels, 2)
        bad = self.root / "bad.mp3"
        bad.write_bytes(b"not audio")
        with self.assertRaises(AudioError):
            probe(bad, self.settings)

    def test_click_tempo_grid_and_cache(self):
        result = analyze(self.a, self.settings, self.storage)
        self.assertAlmostEqual(result["bpm"], 120, delta=2)
        beats = np.asarray(result["beats_seconds"])
        self.assertGreater(len(beats), 30)
        # Every estimated beat should fall near the known half-second fixture grid.
        errors = np.abs((beats - 0.5 + 0.25) % 0.5 - 0.25)
        self.assertLess(float(np.median(errors)), 0.05)
        self.assertEqual(result, analyze(self.a, self.settings, self.storage))
        self.assertTrue(result["warnings"])
        misleading = {**result, 'bpm': 160.0}
        regional = analyze_rhythm(self.a, misleading, self.settings, self.storage)
        self.assertTrue(regional['reliable'])
        self.assertAlmostEqual(regional['bpm'], 120, delta=.15)

    def test_silence_does_not_invent_tempo(self):
        silence = self.root / "silence.wav"
        with wave.open(str(silence), "wb") as audio:
            audio.setparams((1, 2, 44100, 0, "NONE", "not compressed"))
            audio.writeframes(b"\x00\x00" * 44100 * 3)
        result = analyze(silence, self.settings, self.storage)
        self.assertIsNone(result["bpm"])
        self.assertEqual(result["beats_seconds"], [])

    def test_stretch_preserves_pitch_duration_and_stereo(self):
        source = self.root / "tone.wav"
        write_fixture(source, seconds=5, tone=440, clicks=False)
        for target in (115.2, 124.8):
            output = self.root / f"tone-{target}.wav"
            prepare_excerpt(source, output, 0.5, 4.5, 120, target, self.settings)
            info = probe(output, self.settings)
            self.assertAlmostEqual(info.duration, 4 * 120 / target, delta=0.003)
            self.assertEqual(info.channels, 2)
            with wave.open(str(output), "rb") as audio:
                samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").reshape(-1, 2)
            left = samples[4410:-4410, 0].astype(float)
            spectrum = np.abs(np.fft.rfft(left * np.hanning(len(left))))
            frequency = np.fft.rfftfreq(len(left), 1 / 44100)[np.argmax(spectrum)]
            self.assertAlmostEqual(frequency, 440, delta=2)
            self.assertFalse(np.array_equal(samples[:, 0], samples[:, 1]))
        with self.assertRaises(ValueError):
            tempo_ratio(120, 140)

    def test_pair_render_and_tempo_fallback(self):
        results = (analyze(self.a, self.settings, self.storage), analyze(self.b, self.settings, self.storage))
        report = render_pair((self.a, self.b), results, self.settings, self.storage,
                             starts=(0.5, 0.5), seconds=22, bpms=(120, 124), style="smooth")
        self.assertEqual(report["style"], "smooth")
        self.assertEqual(report["audio"]["channels"], 2)
        self.assertLessEqual(abs(report['pulse_alignment']['incoming_delay_seconds']), .012)
        self.assertLessEqual(abs(report['pulse_alignment']['drift_seconds']), .025)
        self.assertTrue(Path(report["report"]).exists())
        self.assertAlmostEqual(report["audio"]["duration"], report["expected_seconds"], delta=0.15)
        # Full decode validates the compressed deliverable and its peak headroom.
        decoded = self.root / "pair.f32"
        run_audio([self.settings.ffmpeg, "-v", "error", "-i", report["output"], "-f", "f32le", str(decoded)])
        samples = np.fromfile(decoded, dtype="<f4")
        self.assertTrue(np.all(np.isfinite(samples)))
        self.assertLess(float(np.max(np.abs(samples))), 1)
        eq_report = render_pair((self.a, self.b), results, self.settings, self.storage,
                                starts=(.5, .5), seconds=22, bpms=(120, 124), style='eq_swap', target_bpm=121)
        self.assertEqual(eq_report['style'], 'eq_swap')
        self.assertEqual(eq_report['target_bpm'], 121)
        recipe = eq_report['recipe']
        levels = [level * gain for level, gain in zip(recipe['overlap_rms_before_gain'], recipe['track_gains'])]
        self.assertAlmostEqual(*levels, places=7)
        self.assertLessEqual(recipe['mixed_pcm_peak'] * recipe['post_mix_gain'], .820001)
        self.assertGreater(eq_report['incoming_tail_check']['decoded_rms'], .02)
        fallback = render_pair((self.a, self.b), results, self.settings, self.storage,
                               starts=(0.5, 0.5), seconds=3, bpms=(90, 140))
        self.assertEqual(fallback["style"], "boundary_fade")
        self.assertIsNone(fallback["target_bpm"])
        with self.assertRaises(ValueError):
            render_pair((self.a, self.b), results, self.settings, self.storage,
                        starts=(25, 0), bpms=(120, 124))
        with self.assertRaises(ValueError):
            render_pair((self.a, self.b), results, self.settings, self.storage,
                        seconds=3, bpms=(120, 124), style="smooth")
        for invalid_target in (float('nan'), 0, 160):
            with self.assertRaises(ValueError):
                render_pair((self.a, self.b), results, self.settings, self.storage,
                            seconds=22, bpms=(120, 124), style='eq_swap', target_bpm=invalid_target)

    def test_pulse_measurement_detects_offset_and_drift(self):
        reference = self.root / 'phase-reference.wav'
        shifted = self.root / 'phase-shifted.wav'
        prepare_excerpt(self.a, reference, 1, 11, 120, 120, self.settings)
        prepare_excerpt(self.a, shifted, 1.1, 11.1, 120, 120, self.settings)
        first = pulse_grid(reference, 0, 10, .5)
        second = pulse_grid(shifted, 0, 10, .5)
        measured = compare_grids(first, second, 10)
        self.assertAlmostEqual(measured['incoming_delay_seconds'], .1, delta=.01)
        self.assertLess(abs(measured['drift_seconds']), .01)
        fast = self.root / 'phase-fast.wav'
        prepare_excerpt(self.a, fast, 1, 11.1, 120, 121.2, self.settings)
        drifting = compare_grids(first, pulse_grid(fast, 0, 10, .5), 10)
        self.assertGreater(abs(drifting['drift_seconds']), .07)

    def test_pulse_measurement_keeps_kicks_near_louder_syncopation(self):
        rate, seconds = 44100, 16
        kick = np.arange(round(.04 * rate)) / rate
        pulse = np.exp(-kick * 100) * np.cos(2*np.pi*80*kick)
        clean = np.zeros(rate * seconds)
        busy = np.zeros_like(clean)
        for index, beat in enumerate(np.arange(.5, seconds - .5, .5)):
            position = round(beat * rate)
            clean[position:position+len(pulse)] += .3 * pulse
            busy[position:position+len(pulse)] += .3 * pulse
            # Stronger nearby notes must not suppress the actual kick events.
            position = round((beat + (.12 if index % 2 else -.12)) * rate)
            busy[position:position+len(pulse)] += .5 * pulse
        paths = [self.root / 'clean-kicks.wav', self.root / 'syncopated-kicks.wav']
        for path, samples in zip(paths, (clean, busy)):
            with wave.open(str(path), 'wb') as audio:
                audio.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
                audio.writeframes((samples * 32767).astype('<i2').tobytes())
        grids = [pulse_grid(path, 0, seconds, .5) for path in paths]
        comparison = compare_grids(*grids, seconds)
        self.assertLess(abs(comparison['incoming_delay_seconds']), .01)
        self.assertLess(abs(comparison['drift_seconds']), .01)

    def test_eq_swap_preserves_bass_ownership_and_percussion_overlap(self):
        rate, seconds = 44100, 24
        time = np.arange(seconds * rate) / rate
        sources = []
        for index, frequencies in enumerate(((55, 700, 4000), (90, 1100, 6000))):
            samples = sum(level * np.sin(2*np.pi*frequency*time)
                          for level, frequency in zip((.18, .05, .02), frequencies))
            path = self.root / f'eq-source-{index}.wav'
            stereo = np.column_stack((samples, samples * .9))
            with wave.open(str(path), 'wb') as audio:
                audio.setparams((2, 2, rate, 0, 'NONE', 'not compressed'))
                audio.writeframes((stereo * 32767).astype('<i2').tobytes())
            sources.append(path)
        graph, recipe = eq_swap_graph((1, 1), 24, 24, 16, 120)
        output = self.root / 'eq-result.wav'
        run_audio([self.settings.ffmpeg, '-v', 'error', '-nostdin', '-i', str(sources[0]),
                   '-i', str(sources[1]), '-filter_complex', graph, '-map', '[out]',
                   '-c:a', 'pcm_s16le', str(output)])
        with wave.open(str(output), 'rb') as audio:
            self.assertEqual(audio.getnchannels(), 2)
            self.assertAlmostEqual(audio.getnframes()/rate, 32, delta=.01)
            samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').reshape(-1, 2) / 32768
        def amplitude(start, frequency):
            segment = samples[start*rate:(start+1)*rate, 0]
            return 2 * abs(np.mean(segment * np.exp(-2j*np.pi*frequency*np.arange(rate)/rate)))
        # Bass changes owner, rather than two low ends fading for all 16 seconds.
        self.assertGreater(amplitude(12, 55), .14)
        self.assertLess(amplitude(12, 90), .02)
        self.assertGreater(amplitude(20, 90), .14)
        self.assertLess(amplitude(20, 55), .01)
        # Percussion from both sources can coexist before the bass swap.
        self.assertGreater(amplitude(12, 4000), .01)
        self.assertGreater(amplitude(12, 6000), .005)
        self.assertGreater(amplitude(12, 700), .035)
        self.assertLess(amplitude(12, 1100), .01)
        self.assertGreater(amplitude(20, 1100), .035)
        self.assertLess(amplitude(20, 700), .01)
        # Incoming track must continue after the outgoing source reaches EOF.
        self.assertGreater(amplitude(28, 90), .14)
        self.assertGreater(amplitude(28, 1100), .035)
        self.assertLess(float(np.max(abs(samples))), .91)
        self.assertAlmostEqual(recipe['bass_swap_at_seconds'], 16)
        # Protecting the lead delays incoming melody until outgoing EOF.
        graph, protected = eq_swap_graph((1, 1), 24, 24, 16, 120, protect_lead=True)
        output = self.root / 'lead-handoff.wav'
        run_audio([self.settings.ffmpeg, '-v', 'error', '-nostdin', '-i', str(sources[0]),
                   '-i', str(sources[1]), '-filter_complex', graph, '-map', '[out]',
                   '-c:a', 'pcm_s16le', str(output)])
        with wave.open(str(output), 'rb') as audio:
            samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').reshape(-1, 2) / 32768
        self.assertGreater(amplitude(20, 700), .035)
        self.assertGreater(amplitude(22, 700), .035)
        self.assertLess(amplitude(20, 1100), .003)
        self.assertLess(amplitude(23, 1100), .003)
        self.assertGreater(amplitude(25, 1100), .035)
        self.assertLess(amplitude(25, 700), .003)
        self.assertGreater(amplitude(28, 90), .14)
        self.assertEqual(protected['outgoing_lead_ends_at_seconds'], 24)
        self.assertEqual(protected['incoming_lead_starts_at_seconds'], 24)
        self.assertEqual(protected['vocal_detection'], 'not_performed')


if __name__ == "__main__":
    unittest.main()
