# Loop, filter and delay experiment

**Owner rejected this version. The recipe is disabled.** The outgoing song was
interrupted during a vocal part, and the incoming entry sounded like a cut.
The corrected plain crossfade retains its separate feedback.

The recipe jumped from 22.3811s of outgoing prepared playback to a bar from
30.0s while vocals were ongoing. Screening the quieter destination missed the
phrase being interrupted. Its 5ms incoming ramp avoided a sample click but
introduced the full incoming song abruptly. Beat/bar alignment and effect-tail
checks could not validate these musical decisions.

Exact feedback/audio hashes are retained in `listening-reviews/` and
`REJECTED.json`. The renderer checks `alignment/loop-filter-delay-1/recipe-status.json`
and refuses to rerun v1. No replacement audio has been claimed. The reproduction
command below now exits with the rejection reason until a separate phrase-aware
revision is designed. Original files are kept as rejected evidence.

Owner approved one Pedalboard effects preview on the corrected At Night →
Stupidisco pair. This is deterministic audio processing; no model chooses a
new waveform or fabricates listening feedback. The current app defaults remain.

Listen to the two loudness-matched 60-second stereo versions:

- [Loop/filter/delay](http://127.0.0.1:8007/loop-filter-delay-cdac3973477e4616b7866412cfc5cb6a/loop-filter-delay.mp3)
- [Corrected plain crossfade](http://127.0.0.1:8007/loop-filter-delay-cdac3973477e4616b7866412cfc5cb6a/crossfade.mp3)

The effect begins near 22.38s. One lower-vocal outgoing bar is repeated four
times. A low-pass filter sweeps from 18kHz to 600Hz, with quarter-note delay
introduced during the last two bars. Incoming audio releases at the 30s bar
boundary. The outgoing dry signal fades briefly, and the high-passed echo tail
decays by about 33.81s. Incoming audio then continues normally.

The one-bar template is selected from the already aligned outgoing material:
the MDX model predicts much lower vocal RMS in bar 4 than nearby candidates.
Only the selection uses the separator; audible audio uses the intact stereo
master. Model leakage remains possible, so this is not a guarantee of an
instrumental bar. The exact selected source time and screening scores are saved.

Implementation:

- NumPy repeats on absolute bar/sample positions. Four-millisecond seam blends
  retain bar duration, avoiding accumulated drift from overlap-shortened loops.
- Pedalboard 0.9.26 provides stateful `LowpassFilter`, `Delay` and `HighpassFilter`.
  Filter automation uses 128-frame steps. Delay runs with a constant 512-frame
  processing size after silent warmup and preserves state through its tail.
- The corrected float32 stereo preparations are hash-verified and reused.
  The repeated preparation and incoming source pass beat/bar checks; the actual
  repeated body is checked separately. The encoded mix's outgoing, loop/release
  and incoming beat regions and transition bar markers pass independent checks.
- Both comparison files receive fixed loudness-matching gains and encoded
  finite/stereo/duration/peak/dropout checks. These are technical checks, with
  listening acceptance pending. No method has been promoted.

Artifacts and reports live outside Git under
`D:/AI-DJ-data/experiments/open-dj`. `auditions/loop-filter-delay-cdac3973477e4616b7866412cfc5cb6a/report.json`
records the baseline/source hashes, loop boundaries, effect settings/control
timeline, selected-bar scores, model/runtime provenance and final audio hashes.
Only the existing local file server on 8007 is used.

## Reproduce

Run from the repository root:

```powershell
.venv\Scripts\python.exe -m scripts.setup_pedalboard
& D:\AI-DJ-data\experiments\open-dj\pedalboard-runtime\Scripts\python.exe -m scripts.render_loop_transition
```

The renderer requires the corrected baseline's preserved prepared sources and
the vocal screening manifest under `alignment/loop-filter-delay-1/`. Screening
was generated with the existing pinned MDX runtime via `scripts.separate_vocals`;
source/stem/model identities are checked before selection. Rendering creates
a fresh work/output folder and does not overwrite earlier audio or owner votes.

Setup pins the Python 3.12 Windows wheel URL and SHA256, verifies it, and installs
without dependencies into a separate `pedalboard-runtime`. Existing CPU packages
are read through `.pth`; the app, timeline and GAN runtimes are untouched.
[Pedalboard is GPLv3](https://github.com/spotify/pedalboard). Its controls and
stateful processing are described in the [official API reference](https://spotify.github.io/pedalboard/reference/pedalboard.html).
