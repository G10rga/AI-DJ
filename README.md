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

Current limits: analysis accepts tracks from 2 seconds to 20 minutes, tempo changes are limited to 6% per track, and phrase candidates are low-confidence heuristics. BPM alternatives expose half/double-time ambiguity without pretending it is resolved. Harmonic chroma features are cached; named key estimation is deferred. The prototype offers linear smooth crossfades and boundary fades; EQ/bass-swap recipes belong to the next renderer milestone. Synthetic checks establish timing, pitch, and decoding behavior, not musical quality. Real house tracks must be auditioned before claiming good automatic transitions.
