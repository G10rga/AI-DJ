# AI DJ Set — implementation plan

Date: 2026-11-06
Design: [Approved design](../specs/2026-10-30-ai-dj-set-design.md)
Status: Milestone 1 foundation and milestone 2 two-track prototype implemented; ten tests pass. FFmpeg/ffprobe 9.0.2 and Rubber Band validated with actual renders. Synthetic tests verify timing, pitch, stereo, silence, corrupt audio, and fallback behavior. Real-music listening remains required. Named key estimation is deferred; chroma features are retained. Application data uses D: through `scripts/local.ps1`. Next: real-pair evaluation, then milestone 3 planning.

## Scope and approach

Build locally on Windows first, with portable paths and subprocess handling for later Ubuntu use. Include every valid uploaded track as a DJ-style excerpt. Deliver upload → analysis → automatic order and transition plan → render → play/download → swap transition → re-render. Exclude public hosting, login, drag-reordering, stems, and learned audio blending.

Proposed stack: Python, FastAPI, SQLite, local file storage, a separate single worker process, and a small server-rendered interface with browser JavaScript. A durable SQLite job queue avoids requiring Redis locally. Verify supported Python/package versions, Windows installation, and native audio tools against official documentation before pinning dependencies. Candidate DSP tools: FFmpeg/ffprobe, librosa, NumPy/SciPy, and Rubber Band. Confirm a working pitch-preserving stretch path before committing to the renderer.

Prioritize the audio pipeline before the full interface. A working web workflow does not establish that transitions sound good.

## 1. Establish the local runtime and data contracts

Files: `pyproject.toml`, `.env.example`, `backend/app/config.py`, `backend/app/models.py`, `backend/app/storage.py`, `backend/app/db.py`, `scripts/doctor.py`.

- Inspect local Python, CPU/RAM, FFmpeg, and stretching support. Document a reproducible Windows setup and later Ubuntu prerequisites. Do not assume local PC resources match the later server.
- Configure loopback binding, storage root, disk limits, and one heavy job at a time. Pass subprocess arguments as lists and use managed temporary directories.
- Store track identity/hash, original metadata, analysis version/confidence, mix membership, plan revisions, jobs/progress/errors, and render revisions in SQLite.
- Define explicit seconds, beat/bar indices, sample rate, and output timeline units. Persist transition source points, target tempo, overlap length, recipe, and warnings.
- Keep uploads, analysis cache, temporary audio, and completed renders separate under ignored local data directories. Never use client filenames as storage paths.

Validation: runtime diagnostic identifies missing tools; database round-trip preserves a plan and its revision; storage paths stay inside the configured root.

## 2. Build analysis and a two-track audio prototype

Files: `backend/app/audio/probe.py`, `backend/app/audio/analyze.py`, `backend/app/audio/structure.py`, `backend/app/audio/stretch.py`, `scripts/render_pair.py`.

- Probe actual audio streams, duration, and channels. Report corrupt/unsupported inputs. Initial format targets: MP3, WAV, FLAC, and M4A, subject to verified decoder support.
- Analyze one track at a time using a lower-rate mono representation; retain original audio for stereo output. Cache by content hash, analysis version, and configuration.
- Estimate tempo, beats, energy, chroma/key, and coarse candidate mixing regions. Track uncertainty and consider half/double-time alternatives. Do not equate detected beats with proven downbeats or phrases.
- Rank candidate phrase starts using repeated structure and energy changes. Use explicit low-confidence warnings when phase or structure is uncertain.
- Render a pair from explicit cue points using pitch-preserving stretching. Check the stretch ratio and reject artifact-prone matching in favor of a shorter, warned handoff.

Validation: synthetic click tracks check beat timing, tempo ambiguity, and stretch duration. User-provided house tracks are required for listening checks; keep them outside Git. Listen for drift, groove damage, clicks, and phrase alignment before scaling up.

## 3. Plan excerpts, order, and transition styles

Files: `backend/app/planning/features.py`, `backend/app/planning/order.py`, `backend/app/planning/excerpts.py`, `backend/app/planning/transitions.py`.

- Implement a deterministic tempo/key/energy baseline for comparison.
- Implement unsupervised feature scaling and nearest-neighbor similarity over rhythmic, timbral, harmonic, and energy features. Combine similarity with pair feasibility and an energy objective; use deterministic seeds/tie breaks. No labeled training data or learned blend curves.
- Return every valid track exactly once. Handle one track, duplicates as separate uploaded entries, short tracks, tempo outliers, and missing key estimates explicitly.
- Select phrase-aware excerpts, initially targeting roughly 2–4 minutes as a tunable builder default rather than a user requirement. Keep source bounds valid and ensure adjacent overlaps cannot consume an entire excerpt.
- Plan 8-bar EQ/cut and 32-bar smooth transitions where feasible. Evaluate both regional compatibility and analysis confidence: a difficult pair must not automatically receive a longer overlap.
- Set an initial configurable maximum tempo change of 6%, then tune through listening. Use a short boundary fade/cut without forced beatmatching for incompatible or unreliable pairs; mark it for review rather than dropping either track.
- Changing a transition style preserves track order and invalidates the render revision. Recompute cue geometry as needed; reject infeasible choices with a clear reason.

Validation: property/invariant tests check membership, source bounds, finite tempos, deterministic plans, and non-overlapping incoming/outgoing regions. Compare baseline and feature-based plans using the same listening playlist.

## 4. Render complete sets with bounded memory

Files: `backend/app/audio/recipes.py`, `backend/app/audio/render.py`, `backend/app/audio/encode.py`.

- Implement deterministic EQ/bass handoff and smooth crossfade recipes with controlled gain and click-free boundaries.
- Process excerpts and transition regions incrementally using temporary files or streamed blocks. Never load all decoded tracks or the entire set into RAM.
- Preserve stereo, use a consistent output sample rate, and prevent clipping with measured gain/headroom. Initial deliverable: one browser-playable MP3; use temporary PCM only where required.
- Publish a completed render atomically after validation; retain the previous playable revision when a new render fails. Full re-render is acceptable for v1.
- Clean temporary data on success/failure; preserve source uploads and the current playable output. Check free space before expensive work and give an actionable error when insufficient.

Validation: decode the finished file, verify expected duration from excerpt/overlap geometry, scan for clipping/nonfinite samples, and check channel consistency. Measure peak process memory and disk use on a 30+ track run; initial worker target is below 2 GB RAM for the later 4 GB host. Report measured runtime without promising real-time rendering.

## 5. Add durable jobs and the local API

Files: `backend/app/main.py`, `backend/app/api.py`, `backend/app/jobs.py`, `backend/app/worker.py`.

- Stream uploads to disk, enforce configured limits, probe files, and return per-file errors. Never silently proceed with a reduced set after a failed upload; require correction or explicit removal of the failed entry.
- Add mix creation/status, current plan, transition changes, render requests, and audio download/playback endpoints. Support browser audio seeking through range requests.
- Run analysis/planning/rendering in a separate worker. Claim jobs transactionally, persist progress, detect abandoned jobs on restart, and provide a safe retry path.
- Snapshot plan revisions for each render. Coalesce or serialize duplicate render requests and prevent stale jobs from replacing the newest requested result.
- Keep filesystem access behind IDs and bind to loopback. Public deployment and authentication remain deferred.

Validation: integration tests cover partial upload failures, malformed audio, worker interruption/retry, revision races, failed re-render retention, and seeking. Confirm heavy work leaves status requests responsive.

## 6. Build the minimal local interface

Files: `backend/app/templates/`, `backend/app/static/`.

- Apply relevant frontend skills when implementation reaches this stage.
- Provide multiple-file upload, per-file errors, stage/progress, ordered excerpts, transition labels and warnings, a style selector, re-render action, player, and download.
- Retain the last playable result during rendering; clearly show when it corresponds to an older plan revision.
- Provide keyboard-accessible controls and readable failure/retry states. No mockup companion or complex deck UI.

Validation: browser exercise of upload → render → seek/play/download → change style → re-render, including reload during a job, failed input, and failed render.

## 7. Evaluate and document the first usable release

Files: `README.md`, `docs/testing/transition-evaluation.md`, `HANDOFF.md`.

- Use a private 30+ track house playlist spanning clean intros/outros, vocals, sparse sections, short tracks, and tempo/key outliers. Record file hashes and settings without committing audio.
- Score every join for beat stability, phrase alignment, tonal/vocal conflict, loudness continuity, and artifacts. Record baseline versus unsupervised ordering results and every fallback.
- Initial listening target: at least 80% of joins acceptable without editing, with weak joins reviewable and alternative styles available where feasible. Treat this as a proposed engineering target; owner listening remains the product acceptance criterion.
- Confirm every valid upload appears, revision changes work without re-uploading, and errors leave a usable recovery path.
- Document installation, local startup/shutdown, tool checks, storage/cleanup, limitations, memory/runtime measurements, and later Ubuntu portability checks. Do not configure remote hosting yet.

## Execution order and completion

Execute milestones sequentially. Resolve native-tool compatibility in milestone 1 and audio feasibility in milestone 2 before investing in the interface. Update the handoff with completed work and measured limitations after each milestone. Use synthetic fixtures for automated audio checks and private real music for listening; neither is a substitute for the other. No commits unless the owner asks.
