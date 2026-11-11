# Open-source DJ experiments

## One corrected crossfade — 2026-11-12

After the rejected batch, owner approved correcting At Night → Stupidisco only.
[Listen to the new stereo preview](http://127.0.0.1:8007/corrected-at-night-stupidisco-f0096cf999294ce7b45e2b70dfba792b/corrected.mp3).
It is 60 seconds, with handoff at 30 seconds and an eight-bar linear crossfade
from 22.38–37.62 seconds. Listening acceptance is pending.

Full-original beat/downbeat analysis found regular eight-bar spans near the old
cues. Fit tempo across the full observed beat sequence rather than taking a
median of quantized timestamps. New cue positions align their predicted bar
starts. Each source has real context before and after the crop; preparation
stays float32 through gain staging to avoid clipping mastered/stretched peaks.

The exact prepared sources passed beat/bar matching, regular bar support and
separate checks on each half of the overlap. Encoded solo sections preserve their
source timing. These checks support timing, not musical taste or phrase/vocal
compatibility. This is a research preview; app defaults and owner votes remain
unchanged. Details are in its report.json. An earlier unshared PCM16 pilot is
marked superseded and is excluded from this listening request.

Reproduce analysis and a fresh isolated revision from the project root:

```powershell
& D:\AI-DJ-data\timeline\venv\Scripts\python.exe -m scripts.analyze_pair_beats
& D:\AI-DJ-data\timeline\venv\Scripts\python.exe -m scripts.correct_one_crossfade
```

Each correction writes a new attempt and publishes only if the timing and final
audio checks pass. Existing reviewed audio is preserved.

## Rejected follow-up batch — 2026-11-12

Owner rejected all nine previews in the three-pair follow-up and reported that
many sound off beat. This supersedes the batch's earlier ready-for-listening
status; it does not revoke the separate positive Move/Say What feedback.
Immutable reviews in the session and each pair folder pin this exact statement
and audio hashes. No individual file was assigned a specific timing diagnosis
on the owner's behalf.

The initial checks established decodability, duration, loudness and peak safety.
They did **not** independently validate beats, bar starts or musical quality.
The legacy 70–130Hz pulse matcher still passes the rejected prepared sources.
No saved beat/downbeat model timelines existed for these six sources.

An independent pinned Beat This audit of the exact prepared waveforms flags:

- At Night/Stupidisco: ~40ms median beat offset; predicted bar starts disagree.
- Too Much For Me/Dreamer: predicted beats agree within the 25ms test tolerance,
  while predicted bar starts disagree and include irregular predictions.
- Sauti/Fire Fire: predicted beats agree within that tolerance, while predicted
  bar starts disagree and one source's bar predictions are irregular.

These model predictions support further timing investigation; they are not
human-verified beat/downbeat truth. Automatic cue shifts would be premature.
Audit evidence is under the batch's `timing-audit/` folder. No corrected audio
has been claimed or promoted.

The research runner now requires independent beat and bar agreement, supported
by at least three complete regular 4/4 bars on each prepared source. Unknown or
mismatched evidence blocks new owner-preview rendering. The author example
remains explicitly an unaligned smoke test. Reviewed audio folders cannot be
overwritten. This adds a research publication gate; the production app renderer
still requires a separate timing fix and listening validation.

These experiments evaluate transition interpretation and a pretrained generator
without changing owner reviews, preference votes or active models. Downloads,
the separate runtime, audio and reports live under
`D:/AI-DJ-data/experiments/open-dj`, outside Git.

## Measured recognition baseline

The frozen `transition-magnitude-context-3` interpreter was evaluated on the
official UnmixDB set222 archive, verified against Zenodo's published MD5.
Only the upstream good-mix subset with available audio was included:

- 11 mixes, 22 linear-fade transitions, **only two distinct ordered source pairs**.
- Correct gradual blends: **1/22 (4.5%)**.
- Predictions: 20 unknown, one gradual blend, one incorrect EQ handoff.
- Coverage: 2/22 (9.1%); accuracy among recognized examples: 1/2.

Source identities and cue timing were supplied from official labels. This tests
interpretation, **not transition discovery**. Repeated synthetic examples from
one playlist cannot establish accuracy on human DJ sets or other techniques.
No thresholds were tuned on these evaluation examples. The weak baseline is
retained, rather than using these results as new training labels.

Full measurements: `reports/unmixdb-baseline.json` and `.md` under the experiment
root, including transformations, hashes, per-example predictions and exclusions.

## Listen to the generator

The author's pinned DJtransGAN minmax checkpoint loaded all 122 state keys
strictly with PyTorch's tensor-only loader. The adapter removes eager imports of
unused frontends, plotting and legacy preprocessing. It keeps the selected
torchlibrosa architecture and verifies executable source against the pinned
archive. Original source files are untouched. Missing or changed weights fail.

Author example preflight passed, then the existing **I Move (Lyrics) → F Say What**
comparison was used. Each preview is 60 seconds, with handoff at 30 seconds and
overlap from 14–46 seconds. All three are mono, matched around -21.33 LUFS,
without clipping or detected 100ms near-silent blocks:

- `djtransgan.mp3`: pretrained learned EQ/fader controls.
- `linear.mp3`: the exact same prepared inputs with a simple linear crossfade.
- `existing-app.mp3`: matching window from the existing controlled/stem audition.

Files are in `auditions/owner-pair-9f3958001f11492f8df9200868c44877/` under the
experiment root. Each folder has `report.json`, `controls.json` and a readable
`README.md`. Start listening around 10 seconds, where the overlap approaches.
The existing app comparator also differs in source separation; the linear
comparator is the controlled test of learned controls.

Owner listened and explicitly reported: **DJtransGAN and the linear crossfade
are both good and both better than the existing app audition on this pair**.
No preference between DJtransGAN and linear was stated; this is not a tie vote.
The exact statement and two preferences are saved under the audition folder's
`listening-reviews/`, pinned to the audio hashes and report. This is research
evidence, separate from the app ranker whose features do not faithfully represent
these new generator controls. It does not establish results on other song pairs.

The model
is mono; this is our preparation adapter, not exact replication of the author's
madmom pipeline. The published example uses explicit 16-second overlap without
beat correction and is only a smoke test. Nothing has been promoted, and no
owner listening choices have been manufactured. The explicit choice above is
recorded without default promotion or changing existing app votes.

For browser playback, serve just the audition directory locally:

```powershell
cd C:\Users\user\Documents\GitHub\AI-DJ
.venv\Scripts\python.exe -m http.server 8007 --bind 127.0.0.1 --directory D:\AI-DJ-data\experiments\open-dj\auditions
```

Open `http://127.0.0.1:8007/owner-pair-9f3958001f11492f8df9200868c44877/`.
This isolated file server is separate from `/compare`; it does not save votes.

## Reproduce

### Three additional song pairs

The follow-up uses six different songs from three already published test mixes:
At Night → Stupidisco, Too Much For Me → Dreamer, and Sauti → Fire Fire. Cues,
tempo ratios and overlap come from each render's **actual applied plan**, not
a fresh prediction. The source files and published baseline are pinned before
inference. Unsupported PCM delays or insufficient context fail visibly.

Run with the separate research interpreter and FFmpeg environment below:

```powershell
& D:\AI-DJ-data\experiments\open-dj\runtime\Scripts\python.exe -m scripts.benchmark_listening_batch --test-jobs 6fe842b8e47940d3a67914b7740a46d6 340b3ca2f93b4bee8f38c6405fcbe1ea c89d1ffe53ca4586b878432ca9a89b8b
```

The batch saves a session manifest and listening sheet under
`auditions/listening-batch-<id>/`; individual reports/audio are under
`auditions/test-pair-<job-id>/`. Numbering remains **1 existing app, 2 DJtransGAN,
3 simple crossfade**. Listen around 20–40 seconds of each 60-second mono preview.
No new votes are written and no method is promoted by running this command.
Pairs share no source songs within this batch. Repeat generation refuses to
overwrite a pair folder containing saved listening reviews.

The obsolete app copies on 8000/8002/8003/8004 were stopped after their exact
processes were verified. Current app is 8005; audition files use the existing
8007 file server. The follow-up does not open another port.

### Setup and individual runs

Run from the repository root to avoid unrelated modules in the home directory.
The bootstrap requires the existing Python 3.12 timeline CPU environment with
torch/torchaudio 2.6.0+cpu. It reads its packages through a `.pth` file, installing
additional pinned dependencies only into the separate research venv.

```powershell
cd C:\Users\user\Documents\GitHub\AI-DJ
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.setup_dj_benchmarks
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.benchmark_unmixdb
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.setup_djtransgan

$env:AI_DJ_FFMPEG = 'D:\Tools\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe'
$env:AI_DJ_FFPROBE = 'D:\Tools\ffmpeg-9.0.2-essentials_build\bin\ffprobe.exe'
& D:\AI-DJ-data\experiments\open-dj\runtime\Scripts\python.exe -m scripts.benchmark_djtransgan --example
& D:\AI-DJ-data\experiments\open-dj\runtime\Scripts\python.exe -m scripts.benchmark_djtransgan --comparison-job 9f3958001f11492f8df9200868c44877
```

The second command accepts another successfully published comparison job. Its
frozen source plan must have a positive overlap below 60 seconds and 30 seconds
of listening context on either side of its handoff. It verifies originals and
baseline hashes before rendering. Repeated runs replace only that experiment's
artifacts; owner jobs and their audio remain unchanged.

Provenance and licenses:

- [DJtransGAN (MIT)](https://github.com/ChenPaulYu/DJtransGAN), commit
  `64228931f3b4514f289fbbbc0e5675adb57aeb88`.
- [UnmixDB creation code](https://github.com/Ircam-RnD/unmixdb-creation), commit
  `abc606a30d5f5b01df589bef5345a73c79528907`.
- [Official UnmixDB dataset](https://zenodo.org/records/1422385): retain dataset
  attribution and included license links if sharing audio.
- `sources.json` records archives, checksums and URLs; `runtime/setup.json`
  records the shared base versions and pinned added requirements. Each inference
  report records loaded weights, adapter changes, runtime versions, source audio,
  timing, output hashes and technical checks. The checkpoint SHA256 is a locally
  observed hash of the author's download, not a publisher-signed checksum.

Next evidence to collect: owner listening on several distinct song pairs,
additional source-disjoint recognition data and separately held-out validation.
The pretrained generator is a comparator, not a transition-type teacher.
