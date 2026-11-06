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
        self.assertTrue(Path(report["report"]).exists())
        self.assertAlmostEqual(report["audio"]["duration"], report["expected_seconds"], delta=0.15)
        # Full decode validates the compressed deliverable and its peak headroom.
        decoded = self.root / "pair.f32"
        run_audio([self.settings.ffmpeg, "-v", "error", "-i", report["output"], "-f", "f32le", str(decoded)])
        samples = np.fromfile(decoded, dtype="<f4")
        self.assertTrue(np.all(np.isfinite(samples)))
        self.assertLess(float(np.max(np.abs(samples))), 1)
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


if __name__ == "__main__":
    unittest.main()
