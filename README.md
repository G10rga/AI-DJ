# AI DJ Set Maker

Personal web app: upload ~30+ house tracks → one continuous DJ-like set with adaptive transitions. Develop and run locally on the owner’s PC first; Ubuntu hosting comes later.

**Status:** Local foundation and two-track audio prototype implemented; 10 tests passing. Full-set planning, EQ recipes, background jobs, and the web app are next. Real-music listening evaluation is still pending.

## Docs

| File | Purpose |
|------|---------|
| [docs/superpowers/specs/2026-10-30-ai-dj-set-design.md](docs/superpowers/specs/2026-10-30-ai-dj-set-design.md) | Product/tech design (source of truth for decisions) |
| [HANDOFF.md](HANDOFF.md) | Takeover brief for the next agent/human |
| [Implementation plan](docs/superpowers/plans/2026-11-06-ai-dj-set-implementation.md) | Ordered implementation milestones and validation |
| [AGENTS.md](AGENTS.md) | Standing instructions for AI agents in this repo |

## Quick summary

- **Audience:** Owner first (personal tool)
- **Genre:** House
- **Backend:** Python (FastAPI + async workers recommended)
- **ML (v1):** Unsupervised — track **order** + **transition style** only
- **DSP:** Analysis, beatmatching, EQ/crossfade render
- **UI:** Upload → build → play → swap weak transition → re-render → download
- **Not v1:** Stems/markers/DJ exports, learned blend audio, multi-user polish

## Owner decisions (2026-11-06)

These answers are recorded in the design and handoff:

1. DJ-style excerpts with selected mix-in/out points.
2. Include every valid uploaded track, including poor musical fits; report invalid inputs.
3. Local PC development first. Later server: 4 GB RAM, third-generation Intel Core i3, 200+ GB storage.
4. Local PC only for now; remote hosting and authentication are deferred.

The revised design is approved. Follow the implementation plan, starting with local tool checks and audio feasibility.

## Repo layout (current)

```
ai-dj-set/
  docs/superpowers/specs/   # design
  .superpowers/             # brainstorm mockups (local only; gitignored)
  HANDOFF.md / AGENTS.md / README.md
```

## Local development

The foundation uses Python 3.12+ and the standard library. Audio analysis additionally uses librosa, NumPy, and SciPy; verified locally with Python 3.14.0 and SQLite 3.50.4. Install the tested audio dependency snapshot with `python -m pip install --no-cache-dir -r requirements-audio.txt` inside the virtual environment. Web dependencies are not installed yet.

From the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m scripts.doctor
```

The doctor creates the ignored `data/` directories and initializes `data/app.sqlite3`. It exits with code 1 if decoding/stretch tools are missing or disk space is insufficient. It does not start a web server; that milestone is not implemented yet.

On this PC, use the local launcher to select the installed FFmpeg build and put all application data on D: without changing global environment settings:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/local.ps1
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m unittest discover -s tests -v
```

The launcher uses `D:\Tools\ffmpeg-9.0.2-essentials_build\bin` and stores uploads, analysis, temporary audio, renders, and SQLite in `D:\AI-DJ-data`. The policy flag applies only to the launched PowerShell process. Direct Python commands use the defaults below unless environment settings are supplied.

Install FFmpeg and ffprobe with the Rubber Band filter. FFmpeg's [download page](https://ffmpeg.org/download.html) links to Windows builds. The [Gyan build page](https://www.gyan.dev/ffmpeg/builds/) lists librubberband in its essentials build. Keep any local binaries in ignored `tools/`; no global PATH modification is needed:

```powershell
$env:AI_DJ_FFMPEG = 'C:\path\to\ffmpeg.exe'
$env:AI_DJ_FFPROBE = 'C:\path\to\ffprobe.exe'
python -m scripts.doctor
```

`.env.example` documents environment settings; it is not automatically loaded. The default storage root is the repository's `data/` folder. `AI_DJ_DATA_ROOT` can point to another disk. Local inspection found only about 5.9 GiB free before audio-tool installation, so use a roomier drive for large playlists. Each upload is limited to 512 MiB by configuration; operations reserve at least 2 GiB free. These limits will be enforced by the upload/render milestones.

One heavy worker and loopback binding are required. SQLite stores immutable plan revisions and uploaded-entry membership separately, so duplicate audio files can remain separate entries and a new plan cannot silently omit a track. Playback, queue execution, and render publication are not implemented yet.

For later Ubuntu setup, provide Python and an FFmpeg build with the same filter support and rerun the diagnostic. Ubuntu deployment has not yet been validated.

## Two-track prototype

From the project directory, render two real files using the local launcher. Replace the example file paths with your own:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.render_pair "D:\Music\first.mp3" "D:\Music\second.mp3"
```

The command analyzes one track at a time, caches its features, and renders stereo MP3 plus a JSON report in `D:\AI-DJ-data\renders`. It prints both paths. Defaults are up to 120 output seconds per excerpt and an 8-bar overlap when beat confidence and tempo limits permit. Otherwise it uses an unstretched short boundary fade and reports the reason. A successful fallback does not claim beatmatching.

Select source starts in seconds and, if independently known, provide verified BPM values:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.render_pair "D:\Music\first.mp3" "D:\Music\second.mp3" --a-in 60 --b-in 32 --a-bpm 124 --b-bpm 126 --seconds 120 --bars 32 --style smooth
```

`--style smooth` rejects an infeasible beatmatched blend rather than silently changing styles. `--style boundary_fade` forces a short unstretched handoff. `--analyze-only` prints analysis without rendering. Existing renders are retained; each run creates a new output.

Generate a small synthetic smoke demo with no music files required:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.demo_pair
```

The demo stores generated WAV fixtures on D: and prints its MP3/report paths. Tests generate temporary fixtures on D: and clean them up:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m unittest discover -s tests -v
```

Beatmatched `auto` renders now use the `eq_swap` recipe. It brings in upper frequencies across the overlap, trades midrange over eight beats, and swaps bass over half a beat at an outgoing beat boundary. Overlap RMS is matched conservatively. The mix is written as unclipped float PCM, scanned, and encoded with a fixed gain reserving peak headroom. The mixer timeline is reset before the final fade, and decoded incoming-tail energy is compared with the prepared source to reject unexpectedly silent tails. Use `--style eq_swap` explicitly or `--style smooth` for the full-band crossfade comparison. Phase is measured on the stretched audio and corrected through the incoming cue. Ambiguous or drifting pulse estimates are rejected rather than described as successful beatmatching.

Current limits: analysis accepts tracks from 2 seconds to 20 minutes, tempo changes are limited to 6% per track, and phrase candidates are low-confidence heuristics. An 8-bar duration or beat-aligned bass swap does not establish downbeat/phrase alignment. BPM alternatives expose half/double-time ambiguity without pretending it is resolved. Harmonic chroma features are cached; named key estimation, automatic vocal-conflict avoidance, and full-set rendering are deferred. Synthetic checks establish timing, spectral handoff, pitch, and decoding behavior, not musical quality. Real house tracks must be auditioned before claiming good automatic transitions.

For sparse outro-to-intro cues, `--style lead_handoff` keeps the outgoing 180–4500 Hz lead band until its final beat and introduces the incoming lead after the outgoing excerpt ends. Incoming upper percussion can enter earlier; bass changes near the end of the overlap. This reduces simultaneous lead material. It does not identify singers, separate stems, or guarantee that a sung phrase has ended: select suitable source cues and listen. Lead handoffs match the incoming level against the outgoing solo/body section as well as the overlap, avoiding attenuation to an already quiet outro.

### ML ordering and transition planning

Fit an unsupervised model to a local collection and save a full track-order and
transition plan (the full-set renderer/UI are still separate future work):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.plan_mix "D:\G1-Drive\Dj\AfroHouse" --compare
```

Add `--preview-best` to audition up to three compatible planned joins until one
passes actual waveform validation, using the installed local vocal separator:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.plan_mix "D:\G1-Drive\Dj\AfroHouse" --compare --preview-best
```

`--preview-join 7` selects a particular one-based join. Explicit audio paths are
also accepted; repeated files remain separate uploaded entries. Invalid audio
prevents plan creation and produces an error report rather than silently dropping
inputs. Use `--method baseline` for the DSP-only ordering objective and
`--excerpt-seconds 180` to change the excerpt-duration target.

The learned layer uses 45 timbral, chroma, energy, tempo and pulse-evidence
features. It fits robust scaling, PCA and KMeans to distinct audio content, then
orders entries using learned distance plus explicit tempo/energy constraints.
A Gaussian mixture groups pair descriptors, suggesting long or short blends.
Those group labels have no inherent musical meaning: a declared difficulty rule
maps them to recipes. Small/degenerate collections explicitly fall back to simple
groups. The model does not learn human quality ratings or blend curves.

Regional low-frequency pulse analysis corrects unreliable whole-track estimates
where possible. Planning guards retain every valid entry, cap stretching at 6%,
keep source bounds and overlaps valid, and downgrade unsupported long blends to
short or flagged boundary handoffs. Pulse evidence is not downbeat detection;
approximate cue support must still pass real audio phase/drift checks. Named key,
semantic phrase and lyric-end recognition remain unfinished.

Readable model state is stored under `D:\AI-DJ-data\models`; JSON plans and
Markdown summaries go under `D:\AI-DJ-data\plans`. Plans also round-trip through
SQLite. Auditions preserve the planned common tempo and outgoing/incoming cues,
using 32-bar long-groove or eight-bar EQ recipes plus separated vocal fades.
Baseline comparisons report measurable similarities, not proven listening gains.

The ML dependency is pinned by the optional `ml` extra (`.[audio,ml]`) and already
exists in the tested local environment. Algorithm references:
[PCA](https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html),
[KMeans](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.KMeans.html),
[Gaussian mixtures](https://scikit-learn.org/stable/modules/generated/sklearn.mixture.GaussianMixture.html).

### Optional mid-song vocal handoff

Owner-authorized experiment: separate prepared excerpts into vocal and instrumental
stems locally using the pretrained `UVR-MDX-NET-Inst_HQ_3.onnx` model. Crossfade/EQ
the instrumentals independently, fade the outgoing vocal, and restore the incoming
vocal before a detected vocal entry. No tracks are uploaded and no model is trained.
Low-energy gaps in a separated vocal are heuristics, not verified lyric boundaries.
Model leakage and separation artifacts remain possible.

Vocal fades default to four bars (about eight seconds at house tempos), with
outgoing brightness closing and incoming brightness opening gradually above
1800 Hz. The fade affects the isolated vocal, not the instrumental bed. Use
`--vocal-fade-bars 2`, `4`, or `8` to tune the pace; the selected excerpts must be
long enough for the full handoff. Incoming gain now builds through a detected
vocal entry rather than restoring to full volume inside a sub-second gap.

Install the optional Python 3.12 environment, dependencies, model and caches on D:
(this leaves the application's existing virtual environment intact):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup-separation.ps1
```

Use a JSON report from an already validated beatmatched pair, preserving its
source cues and tempo alignment:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.render_stem_pair "D:\AI-DJ-data\renders\pair-EXAMPLE.json"
```

The worker processes one excerpt (maximum 180 seconds) and one model chunk at a
time on CPU, caching float stems under `D:\AI-DJ-data\separation\stems`. The output
is a stereo MP3 plus JSON report in the usual renders directory. Reports record
the model hash/configuration, source reconstruction error, independent vocal
schedule, instrumental beat alignment, headroom and decoded energy checks. The
default pair renderer continues to use EQ without separation.

For a long, gradual groove transition, first render a validated 32-bar reference
with excerpts longer than its overlap (for example `--seconds 96 --bars 32` at
120 BPM). Then pass that report to `scripts.render_stem_pair` with
`--blend-profile long_groove --vocal-fade-bars 8`. This profile extends the
instrumental midrange exchange to 16 bars (capped at half the overlap), trades
bass over four beats, and layers the upper percussion across the whole overlap.
It checks beat phase/drift in consecutive 16-second windows across long overlaps,
including after source separation, to catch late beat slips. Eight-bar vocal
fades take about 16 seconds at 120 BPM. Structural/lyric boundaries still require
listening; a long blend does not automatically make two musical sections fit.

Model sources: [UVR model repository](https://github.com/TRvlvr/model_repo) and
[UVR model metadata](https://github.com/TRvlvr/application_data).
