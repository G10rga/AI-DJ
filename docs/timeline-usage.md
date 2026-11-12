# Musical timeline analysis and review

For the opt-in transition-foundation analysis profile, verified float vocal
evidence and shared registered-pair service, see
[Shared transition foundation](transition-foundation.md). Legacy analysis and
the current timeline editor keep their existing prediction selection.

Use the repository at `C:\Users\user\Documents\GitHub\AI-DJ`.

```powershell
# One-time setup: separate Python 3.12 CPU environment and pinned model artifacts.
powershell -ExecutionPolicy Bypass -File scripts/setup-timeline.ps1

# Install the local web server in the existing application environment.
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m pip install -r requirements-web.txt

# Analyze a song, including optional separated-vocal activity.
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.analyze_timeline "D:\G1-Drive\Dj\AfroHouse\I Move (Lyrics).mp3" --with-vocals

# Start the editor at http://127.0.0.1:8000.
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.serve
```

The analyzer also accepts several explicit paths. Omit `--with-vocals` for faster
analysis without separation; vocal gaps then remain unknown. The optional
separator must already be set up for vocal analysis. Heavy inference runs
synchronously in the CLI; a durable worker and browser analysis progress are
still future work. Run one analysis command at a time.

The editor lists analyzed tracks, plays source audio, seeks and zooms to 30/60
seconds, and overlays a coarse one-second waveform peak envelope, energy, vocal
activity, downbeats and tentative phrase markers. Select a marker type, enter a
time or use the current playhead, add/remove markers, then save corrections.
Adding a downbeat adds a coincident beat when needed. Removing a beat removes a
coincident downbeat to preserve consistency. Original estimates remain available
through **Use original estimates**, which creates a new revision only when saved.
Unsaved edits can be discarded. A stale save asks for a reload; controls lock
during an in-flight save. Confidence is uncalibrated, not a quality score.

## Records and reproducibility

SQLite version 3 adds immutable timelines, track associations and append-only
corrections without changing old plans or the feedback database. Cache keys
include audio hash, model files/revisions, package versions, adapter/configuration
and vocal-separation mode. The library shows the latest analysis per track;
older predictions and their correction histories remain retained in SQLite and
addressable by their timeline IDs. Corrections apply to a specific analysis ID.

Beat This uses 30-second cores with four seconds of overlapping context; seams
are not assumed correct merely because their times are monotonic. MERT stays
frozen and produces time-pooled 768-dimensional vectors in five-second windows.
The loader strictly matches all checkpoint tensors, adapting the positional
weight-normalization names required by modern PyTorch. Missing/unexpected weights
fail instead of leaving layers randomly initialized.

Model environments, artifacts, decoded scratch audio, separation stems and model
caches stay under the configured D: data root. The application environment and
small web assets remain in the repository. Runtime inference is local/offline.
Official Beat This checkpoint hosting had an expired certificate during setup;
the fallback is a pinned Hugging Face reupload, verified against SHA-256
`8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331`.
MERT is pinned to revision `12af15fef9d0ac838c3f475bfbbf26d2060dd4f5`.

## Verification and current limits

Real inference on **I Move (Lyrics).mp3** (177.70 seconds) produced 354 beats,
89 downbeats, 88 candidate four-beat bars, 36 MERT windows, 178 DSP bins,
356 vocal-activity bins and three section-change candidates. Two strict-loader
runs completed; the invalid automatic-loader run was
stopped before registering a timeline. These counts are model output, not
human-approved annotations. The optional nnAudio warning is irrelevant to this
checkpoint because its CQT frontend is disabled.

The editor was inspected at 1440, 768 and 390 pixels. Automated browser checks
used an isolated SQLite fixture; production corrections stayed at revision zero.
Tests exercise cache identities, migrations, interval/marker validation, revision
conflicts, preservation of estimates, audio ranges, changed sources and chunk
coverage. The inference cache was exercised on the actual library track.

Manual AfroHouse annotation accuracy/listening evaluation is still pending.
Sections are conservative change candidates, not verse/chorus or drop labels.
Transient density and vocal RMS are proxies and may include bleed. Timelines
are not yet used by the transition planner; context-aware candidate generation
is the next saved-plan step. Full-set rendering still uses its existing planner.

Official interface references: [Beat This](https://github.com/CPJKU/beat_this),
[MERT-95M](https://huggingface.co/m-a-p/MERT-v1-95M).
