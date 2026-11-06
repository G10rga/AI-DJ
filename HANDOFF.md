# Handoff — AI DJ Set Maker

**Project path:** `C:\Users\user\Documents\GitHub\AI-DJ`
**Date of handoff:** 2026-11-06  
**Prior context:** Design approved. Local foundation and milestone 2 two-track prototype implemented. Ten tests pass, including real FFmpeg decode/render, pitch preservation, tempo/beat timing, silence, and fallback checks. Real-music listening is pending; full-set planning and the web app are not implemented yet.

## What this is

A personal house-music DJ set builder (rave.dj-like): user uploads their own tracks; the system produces one playable mixed set with DJ-like transitions. Develop and run locally on the owner’s PC first; Ubuntu hosting is deferred.

## Done so far

- [x] Product brainstorm with owner
- [x] Written design: `docs/superpowers/specs/2026-10-30-ai-dj-set-design.md`
- [x] Builder review of design → 4 open questions (below)
- [x] Owner answers open questions; decisions written into design
- [x] Design approved by owner on 2026-11-06
- [x] Implementation plan: `docs/superpowers/plans/2026-11-06-ai-dj-set-implementation.md`
- [x] Milestone 1 foundation and five automated tests
- [x] Local launcher verified: FFmpeg/ffprobe 9.0.2 and Rubber Band filter available; data initialized on D: with about 299 GiB free
- [x] Audio analysis and two-track prototype (synthetic checks complete)
- [ ] Owner listening evaluation with real house tracks

## Hard gate

**Do not scaffold, install deps, or write product code until the owner approves the design** (after open questions are resolved and folded into the design doc). Exploring and updating docs is fine.

## Owner decisions (locked)

| Topic | Decision |
|-------|----------|
| Audience | Personal tool first |
| Genre | House |
| Scale | ~30+ tracks → one set |
| Worst failure | Weak transitions |
| Transitions | Adaptive: ~8-bar EQ/cut when beats lock; ~32-bar smooth when needed |
| ML v1 | Unsupervised: **order + transition style only** |
| Deeper “how blend sounds” ML | Future feature |
| Input | User uploads files |
| Output | Single playable file (+ in-app play); no stems/markers/Serato export |
| Post-mix | Swap transition style + re-render |
| Hosting | Local PC first; Ubuntu hosting later |
| Track length | DJ-style excerpts with selected mix-in/out points |
| Coverage | Include all valid uploads; never drop poor musical fits |
| Later server | 4 GB RAM, third-generation Intel Core i3, 200+ GB storage |
| Access | Local PC only for now; loopback access |
| Backend | Python |
| UI flow | Upload → auto mix → swap weak transitions → play/download (confirmed) |

## Pipeline (agreed mental model)

1. **Analyze (DSP)** — BPM, beat grid, key, energy, phrase/structure hints  
2. **Unsupervised ML** — embeddings/clustering → order; pair difficulty → style (8-bar vs 32-bar, etc.)  
3. **Transition plan (rules + scores)** — bar-aligned recipes  
4. **Render (DSP)** — stretch, EQ/crossfade, one file  
5. **Editor** — swap style → re-render  

## Owner answers (2026-11-06)

1. DJ-style excerpts; exact duration remains a builder tuning decision.
2. Include all tracks. Report invalid inputs rather than silently omitting them.
3. Later server: 4 GB RAM, third-generation Intel Core i3, 200+ GB storage. Develop on the local PC first; PC resources are not specified.
4. Local PC only for now. Public hosting and authentication decisions are deferred.

No original owner questions remain open. The revised design is approved as of 2026-11-06.

## Suggested next steps for the taking-over agent

1. Read `docs/superpowers/specs/2026-10-30-ai-dj-set-design.md` and this file.  
2. Read `docs/superpowers/plans/2026-11-06-ai-dj-set-implementation.md`.
3. Run `powershell -ExecutionPolicy Bypass -File scripts/local.ps1` to check installed audio tools. Owner installed FFmpeg at `D:\Tools\ffmpeg-9.0.2-essentials_build`; the launcher keeps all application data in `D:\AI-DJ-data` because C: has limited free space.
4. Prove two-track transition quality before building the complete interface.
5. Implement the remaining milestones locally; prioritize transition quality and bounded memory for later Ubuntu hosting.

## Current prototype (2026-11-06)

- `scripts/render_pair.py`: analyze two paths, choose/override source cue points and BPM, render stereo MP3 plus a JSON report. Use via `scripts/local.ps1 -m scripts.render_pair ...`.
- `scripts/demo_pair.py`: reproducible synthetic 120/124 BPM stereo demo. Last verified output: `D:\AI-DJ-data\renders\pair-725f05f6d16548afbab7eb7750b167ab.mp3`, duration 28.260s, overlap 15.740s.
- Audio dependencies installed in the project virtual environment; `requirements-audio.txt` snapshots the tested versions. Downloads/temp/cache use D: through the launcher/install command; the virtual environment itself remains on C:.
- Tempo is refined from fitted beat times to avoid frame-lag quantization. Confidence is a heuristic, not calibrated probability. Half/double-time alternatives remain explicit.
- Analysis caches content/version/config on disk, currently independent of the SQLite analysis table; worker integration remains future work.
- Phrase starts are tentative; named key detection is deferred in favor of chroma features. No EQ/bass-swap recipe, full-set ordering, queue execution, or UI yet.
- A 6% maximum change per track and low-confidence fallback preserve all inputs rather than forcing unsuitable beatmatching. `--style smooth` fails clearly when infeasible.
- Follow README for real-track commands. Next: listen to owner-selected house pairs, then implement milestone 3 planning and milestone 4 recipes. Do not infer musical quality from synthetic test success.

## Stack defaults (builder may refine)

- FastAPI backend, Redis/RQ or Celery (or similar) for jobs  
- Simple web UI (React or server-rendered — builder choice)  
- Analysis: Essentia / librosa / similar  
- Time-stretch: Rubber Band / similar  
- Files on disk; async jobs with progress  

## Notes / landmines

- Initialized a repository in this project folder on 2026-11-06 at the owner's request to push to a new GitHub repository. Use the project repository; do not modify any parent repository. Owner explicitly requires no AI commit attribution or co-author trailers.
- `.superpowers/` holds local brainstorm HTML; keep gitignored.  
- Transition quality is the product; order/energy matter less than joins that don’t flinch.
