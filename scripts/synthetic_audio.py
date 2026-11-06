"""Deterministic, stereo synthetic fixtures for tests and manual smoke runs."""
import wave
import numpy as np


def write_fixture(path, bpm=120, seconds=24, tone=220, clicks=True):
    rate = 44100
    time = np.arange(round(seconds * rate)) / rate
    left = 0.12 * np.sin(2 * np.pi * tone * time)
    right = 0.08 * np.sin(2 * np.pi * (tone * 1.5) * time)
    if clicks:
        pulse_t = np.arange(round(0.04 * rate)) / rate
        pulse = 0.65 * np.exp(-pulse_t * 100) * np.cos(2 * np.pi * 80 * pulse_t)
        for beat in np.arange(0.5, seconds - 0.05, 60 / bpm):
            start = round(beat * rate)
            left[start:start + len(pulse)] += pulse
            right[start:start + len(pulse)] += pulse
    stereo = np.column_stack((left, right))
    with wave.open(str(path), "wb") as output:
        output.setparams((2, 2, rate, 0, "NONE", "not compressed"))
        output.writeframes((stereo * 32767).astype("<i2").tobytes())
