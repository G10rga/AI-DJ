# Handoff — AI DJ Set Maker

**Project path:** `C:\Users\user\Documents\GitHub\AI-DJ`
**Date of handoff:** 2026-11-06  
**Prior context:** Design approved. Foundation, validated two-track/stem renderers, and milestone 3 unsupervised library planning are implemented. Owner approved the long Move → Say What reference blend. Twenty-nine tests pass. Actual ML-selected pair preview validated; musical listening is pending. Full-set audio rendering and the web app remain unfinished.

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
- [x] Owner accepted the long Move → Say What reference blend
- [x] Milestone 3 ML ordering/style planner, library run, persisted plan and automatic audition
- [ ] Owner listening evaluation of the ML-selected audition and complete playlist

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
4. Review the newest ML plan/audition below; distinguish unsupervised similarity from human-rated transition quality.
5. Implement bounded-memory full-set rendering/worker integration next, then the minimal local interface. Preserve waveform validation and every uploaded member.

## Current prototype (2026-11-06)

- **First owner preference recorded:** Owner explicitly said “in this case B” for the first Move → Say What A/B audition. Recorded winner `1ce8b05dba5ae6aa` (8s vocal fades) over `e80d704469d06426` (16s), preserving the song-pair-specific qualification. Retrained ranker and verified B ranks above A. Production dataset now has **1 comparison / 1 song pair**, so experimental weights exist but learned automatic selection remains disabled; no held-out accuracy is available yet. Do not generalize this into a universal preference for shorter fades. `feedback/first-audition.json` marked rated.

- **Preference-learning extension:** Owner explicitly requested learning/improvement from listening feedback. Added `planning/preferences.py`, `scripts/feedback.py`, and plan `2026-11-07-preference-learning.md`. Local SQLite stores immutable hashed render candidates plus append-only explicit ratings/preferences. Pairwise logistic ranking learns feature differences within the same ordered song pair; repeated votes are deduplicated and reversals update training direction. Ratings induce only within-pair comparisons; explicit comparisons take precedence. No prior chat remarks or synthetic labels have been entered as owner feedback.
- The first comparison fits experimental weights/rankings. Learned render selection is opt-in (`render_stem_pair --learned-settings`) and requires at least six usable comparisons across three source song pairs. JSON model state includes leave-one-song-pair-out validation, not randomly split mirrored examples. Readiness is a cold-start guard, not proven quality. Supported candidate knobs are vocal fade bars and instrumental profile; it does not synthesize audio or learn waveform curves. Existing full-set/library defaults are unchanged.
- **First real A/B session ready, unrated:** Move → Say What, same source cues/120 BPM/32-bar instrumental bed. A = 16-second vocal fades: `D:\AI-DJ-data\renders\stem-pair-a390cc7ba4b54ac6b1b4541de8ac6113.mp3`, candidate `e80d704469d06426`. B = 8-second vocal fades: `D:\AI-DJ-data\renders\stem-pair-32748fe18b064829ac30f33400cd27dd.mp3`, candidate `1ce8b05dba5ae6aa`. Both 128s, vocal treatment best heard 0:40–1:40. Registered in `D:\AI-DJ-data\feedback`, but production feedback count is ZERO; never claim the personal model has already learned from the owner. Next explicit A/B answer should be recorded with `scripts.feedback prefer WINNER LOSER`, which retrains immediately. Six new preference tests cover actual ranking changes, cold start, persistence, grouped validation and contradictory/duplicate votes; all 35 total tests pass. No commits/pushes.

- **Ten-track set completed (2026-11-07):** Owner requested a mix of ten AfroHouse songs. Added the local ten-track experiment `scripts/render_set.py` (fixed selected catalog, not yet a general queue/UI renderer). Uses ML order, prepares/corrects excerpts, separates locally, schedules independent incoming/outgoing vocal envelopes, shapes EQ, and adds blockwise into a disk-backed float master before static-headroom MP3 encoding.
- **Full mix:** `D:\AI-DJ-data\renders\set-10-130e567fbe894b4291982b457e8c0f4f.mp3`, **18:46.01**, with adjacent `.txt` timestamped tracklist and `.json` report. All 10 selected tracks included. Nine joins validated on original prepared audio and again on separated instrumentals: 3 long 32-bar joins and 6 eight-bar joins; no unbeatmatched fallback remains. One edge-of-file cue needed a small positive PCM delay (modulo a beat), masked by the outgoing track. Full decode peak 0.799, no invalid samples/clipping/unexpected silent windows. All 29 existing tests pass. Listening acceptance pending.
- Local GPU acceleration was validated against CPU on real model inputs (relative RMS difference 7.8e-7). Optional DirectML runtime `onnxruntime-directml==1.24.4` installed in `D:\AI-DJ-data\separation\gpu-venv`, sharing CPU dependency packages through a `.pth` file. `mdx.py` uses DirectML only when available, with sequential execution/memory patterns disabled; standard CPU environment stays unchanged. The ten-track script prefers the optional GPU worker and otherwise uses CPU. Work/checkpoints are under `D:\AI-DJ-data\tmp\set-10-130e567fbe894b4291982b457e8c0f4f`; cached model/stems remain on D:. No commits or pushes.

- **ML implementation (completed 2026-11-07):** Owner accepted the long reference and requested ML. Implemented `backend/app/planning/{learning,order,rhythm,excerpts,planner}.py` and `scripts/plan_mix.py`. Version 3 DSP analysis includes MFCC and spectral statistics. Local kick scans produce regional tempo/cue evidence (e.g. Yamore corrected from the old ~162 BPM tracker estimate to measured 120 BPM); this is not semantic phrase/downbeat detection.
- Learned model fits 45 features with RobustScaler/PCA/KMeans on distinct content hashes, then orders every entry with learned distance and tempo/energy constraints. Gaussian mixture pair groups suggest long/short recipes; declared physical-difficulty mapping and DSP guards determine feasible blends. It does not learn human listening quality or generate blend curves. Duplicates remain separate entries without reweighting model training. Single/degenerate/missing-feature cases are explicit; invalid input batches do not produce reduced playlists.
- Ran on all 16 audio files in `D:\G1-Drive\Dj\AfroHouse` (non-audio PDF excluded). Four track clusters; pair mixture converged. ML order differs from the deterministic baseline. Plan has 3 long, 11 short, and 1 flagged boundary handoff (BODY → set me free; insufficient regional pulse support). All 16 entries retained, source/overlap bounds valid, stretch limited to 6%, SQLite round-trip verified.
- **Plan and readable summary:** `D:\AI-DJ-data\plans\mix-f465a206f55445d1b62997a9159edb47.json` and adjacent `.md`. **Model:** `D:\AI-DJ-data\models\library-8ad2dd20eb6a878dee1436e898981cc1e3d7d563f67e542994137402ba475dd4.json`. Models are readable JSON state, not pickles. Full-set audio has not been rendered.
- **Automatic audition:** ML-selected join 7, Ma Tnsani → Si Ai. Output `D:\AI-DJ-data\renders\stem-pair-f7696b1faa7d44d1ac51e1b51f749ec2.mp3`, 76.60 seconds; instrumental overlap starts at 7.66s and lasts 61.28s. Planned common run tempo is preserved by the new optional `target_bpm` argument to pair rendering. Four separated-instrument timing windows passed; encoded peak 0.815 and no silent windows. Original sources/cues come from the plan. Vocal/lyric placement remains heuristic; owner listening pending.
- CLI: `powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.plan_mix "D:\G1-Drive\Dj\AfroHouse" --compare --preview-best`. `--preview-join N` selects a one-based join. Plans/models/summaries are on D: and core plans persist to SQLite. Style edits preserve order/revision, reject invalid geometry and require refreshed validation before converting flagged boundary joins to beatmatching. All 29 tests pass, including learned model state, deterministic ordering, duplicate/missing/outlier handling, bounds, persistence, bad inputs and audio regressions. No new commits or pushes.

- **Latest request/result:** Owner requested a long, patient beat transition for Move → Say What. Added `--blend-profile long_groove`: upper percussion layers throughout the overlap, instrumental mids trade over up to 16 bars, and bass trades over four beats. Original profile remains the default. Long overlaps now check pulse phase/drift in consecutive 16-second windows, including the separated instrumentals, so early alignment cannot hide a late beat slip. Eighteen tests checked successfully, including a new synthetic late-slip regression and a spectral check of the extended midrange blend.
- **Newest long preview:** `D:\AI-DJ-data\renders\stem-pair-a390cc7ba4b54ac6b1b4541de8ac6113.mp3`, 128 seconds, 120 BPM. Move source 32.2–128.2s into Say What 0.16–96.16s. Overlap 32–96s: 32 bars/64 seconds. Instrumental midrange handoff lasts 32 seconds; bass swap near 64s over two seconds. Vocal fades/EQ use eight bars/16 seconds: outgoing 41.38–57.38s, incoming 80.65–96.65s. The full overlap passed four local timing windows before/after separation; encoded preview has no clipping or silent windows. Source reconstruction within 3e-8. Owner listening pending; no new commits or pushes.

- **Newest two-song listening preview:** owner requested another pair from the same AfroHouse folder. Selected `I Move (Lyrics).mp3` → `F Say What.mp3`, both stable near 120 BPM. Output `D:\AI-DJ-data\renders\stem-pair-d035fc1d5c2341adaaa55b31ef371474.mp3`, 80 seconds. Source cues Move 48.20–96.20s and Say What 16.16–64.16s; instrumental overlap 32–48s. Long vocal fade-out 33.38–41.38s, incoming vocal fade/EQ opening 44–52s. Outgoing fade ends in a detected low-energy gap; incoming has no suitable detected entry gap, so uses an explicitly reported gradual fallback. Actual local ML separation, reconstructed stems and full encoded output validated; owner listening pending. No product code changed for this pair.

- **Newest feedback/revision:** Owner found the stem vocal fade-out much too fast and requested vocal fade-in/EQ-in. Replaced the 4-beat (~2s) outgoing fade and sub-second incoming restoration with configurable 2/4/8-bar fades (default 4 bars, ~7.9s). Outgoing vocal uses a gradual quarter-sine gain curve and closing high band; incoming vocal builds from its detected entry with a half-sine gain curve and opening high band above 1800 Hz. The instrumental bed, source cues and beat alignment are unchanged. `--vocal-fade-bars` controls this in `scripts/render_stem_pair.py`.
- **Latest preview:** `D:\AI-DJ-data\renders\stem-pair-8c407a83f6704c9eb87617121d2b65fd.mp3`, duration 79.01s. Sauti vocal fades 29.63–37.53s; Famax vocal builds/brightens 38.96–46.86s. Fully decoded peak 0.820, no silent windows, separated-instrumental beat offset under 1 ms and measured drift under 2 ms. All 17 tests pass, including added assertions for gradual gain ramps, incoming high/low vocal spectral change, and sustained instrumental bass during the fade. Owner listening pending; no new commits.

- **Latest owner extension:** Rejected the outro/intro lead handoff for killing energy; explicitly requested mid-song mixing with the second vocal removed initially, fading the first vocal and then introducing the second. Internal pretrained local stem separation is now authorized (AGENTS/design updated); no learned blend curves, training, or public stem export.
- Optional separation environment is `D:\AI-DJ-data\separation\venv` (Python 3.12); main Python 3.14 application environment is unchanged. `requirements-separation.txt` pins the small CPU ONNX runtime dependencies. `scripts/setup-separation.ps1` reproduces setup and downloads the public `UVR-MDX-NET-Inst_HQ_3.onnx` model plus UVR metadata onto D:. User audio stays local.
- `backend/app/audio/mdx.py` runs the pretrained instrumental model on one centered-STFT stereo chunk at a time, with 50% overlap. The complementary vocal is source minus instrumental, preserving reconstruction and timing. Float stems are cached under `D:\AI-DJ-data\separation\stems` by source/model/version hash. Model artifacts and audio are outside the repository.
- `scripts/render_stem_pair.py` takes a validated pair JSON report, preserves its source cues and tempo, checks separated-instrumental beats, and blends instrumentals independently from vocals. Vocal gap timing uses energy in the separated vocal; no semantic lyric/phrase detection. Fallback outgoing vocal fade is explicit when there is no suitable gap. Voices receive the same crossover phase response as the instrumental bed to preserve consistent reconstruction outside the handoff.
- **Newest preview:** `D:\AI-DJ-data\renders\stem-pair-818b4c5e26364ee187d1e02d55393135.mp3` (79.01s), using the earlier main-song Sauti/Famax cues from `pair-a21d69bda3d547c8a5dbfc353cda47e2.json`. Instrumental overlap 31.61–47.41s; Sauti vocal fades 35.56–37.53s; Famax vocal gain restores 38.63–38.93s before a detected entry. Bass swap near 39.51s. The groove stays underneath; separation bleed/artifacts remain possible. Owner listening pending.
- All 17 tests pass, including model STFT packing/round-trip, gap scheduling, separate vocal gain timing, instrumental continuity during the vocal gap, and post-EOF tail. Actual separated stems reconstruct their inputs within 3e-8. No new commits or pushes.

- Real-pair listening: owner rejected the short fallback and then reported doubled beats in the initial BPM-matched smooth preview. BPM matching alone did not align pulse phase.
- Owner also rejected the circular-mean pulse alignment preview: its small reported error was misleading because nearby syncopations suppressed kick events and biased phase. That metric did not establish audible beatmatching.
- Smooth renders now retain attacks 80 ms apart, fit a narrow recurring attack train in 70–130 Hz after stretching, and require at least 70% beat coverage and attack error p90 below 15 ms. Reports include matched event timestamps. Cue correction still rejects drift over 25 ms or residual phase offset over 12 ms. This remains a heuristic, not a downbeat/phrase detector. Twelve tests pass, including louder syncopations near kicks, deliberate phase offset, and drift detection.
- Latest local listening preview: `D:\AI-DJ-data\renders\pair-b01cece390a8426f98894a71882fe882.mp3`. Transition at 14.95–29.89 seconds. The incoming cue moved about 163 ms earlier in output time relative to the rejected preview, delaying its attacks to the outgoing kick train. First measured corresponding attacks are 0.6625/0.6645 seconds into overlap. Owner acceptance pending. Local source cue/tempo settings are in the adjacent JSON report. Changes are not committed.
- Owner accepted beat matching in that preview but said the musical result was far from a true DJ transition. Implemented `eq_swap` for matched `auto` renders (explicit `smooth` retains the comparison): 180/1800 Hz crossover, upper-band overlap, eight-beat midrange trade, and half-beat bass swap anchored to the outgoing pulse grid. Overlap RMS is conservatively matched; a latency-compensated safety limiter reserves headroom. This is still a pair prototype; automatic downbeats/phrases and vocal conflict handling are unfinished.
- New EQ comparison: `D:\AI-DJ-data\renders\pair-879f4ee96b3241569eebdbb581615b8c.mp3`, transition 14.95–29.89 seconds, bass swap 22.62 seconds. Incoming source starts near 0.054 seconds to retain its first kick rather than starting one beat into the intro. Phrase alignment is explicitly unverified. Thirteen tests pass, including decoded spectral checks for bass ownership, shorter midrange overlap, percussion coexistence, duration, and headroom; owner listening is pending. See `docs/testing/transition-evaluation.md`.
- Owner found that preview much cleaner. Subsequent Sauti → Famax preview was beatmatched but musically rejected: it interrupted Sauti's rise and became entirely silent after roughly 32 seconds despite a 47-second file duration. Decode and duration checks had missed this bug.
- The mixer now resets timestamps before its final fade. Removed the dynamic limiter in favor of an unclipped float-PCM intermediate, blockwise peak scan, and fixed headroom gain. A decoded incoming-tail check compares against the prepared source and rejects unexpected disappearance after outgoing EOF. Regression checks now measure actual bass/mid energy after outgoing EOF; all 13 tests pass. The original attribution to the limiter alone was incomplete: tail regression also required the timeline reset.
- Latest Sauti → Famax revision: `D:\AI-DJ-data\renders\pair-a21d69bda3d547c8a5dbfc353cda47e2.mp3`, duration 79.01 seconds, blend 31.61–47.41 seconds, bass swap 40.00 seconds. Manually selected established grooves using energy profiles: Sauti source 94.52–141.73 seconds, Famax source about 111.52–159.12 seconds. Sauti's main groove plays for 16 bars before the blend, avoiding the previously interrupted rise. Fully decoded output has peak 0.787 and remains audible through its incoming tail. Cue selection is still manual; this does not establish automatic phrase planning. Owner listening pending. No new commits.
- Owner then rejected the main-groove revision because vocal lines overlapped and were interrupted. Added explicit `lead_handoff` (default `auto` still uses `eq_swap`): incoming 180–4500 Hz lead stays muted until outgoing EOF, outgoing lead fades only over its final beat, and incoming lead fades in afterward. Incoming bass changes near the end; upper percussion may enter earlier. This is band scheduling, not vocal recognition or stem isolation. Outgoing solo/body RMS is used to avoid matching incoming level to an already quiet outro. Nearest-beat rounding also fixes the prior one-beat bias when measured phase wraps close to one full period.
- Latest vocal-overlap comparison: `D:\AI-DJ-data\renders\pair-722ae79ceca8444fbb43d1787c733e90.mp3`, 79.01 seconds. Sauti source 299.11–346.32 (outro) into Famax source 16.31–63.91 (intro). Overlap 31.61–47.41 seconds; bass swap 46.91; incoming lead starts 47.41 after outgoing ends. These sections have much lower centered lead-band activity than the rejected main grooves, but absence of singing and phrase ends are not automatically verified. All 13 tests pass, now including decoded lead-band non-overlap before/after EOF. Full decode peak 0.788; incoming tail stays audible. Owner listening pending. No new commits.

- `scripts/render_pair.py`: analyze two paths, choose/override source cue points and BPM, render stereo MP3 plus a JSON report. Use via `scripts/local.ps1 -m scripts.render_pair ...`.
- `scripts/demo_pair.py`: reproducible synthetic 120/124 BPM stereo demo. Last verified output: `D:\AI-DJ-data\renders\pair-725f05f6d16548afbab7eb7750b167ab.mp3`, duration 28.260s, overlap 15.740s.
- Audio dependencies installed in the project virtual environment; `requirements-audio.txt` snapshots the tested versions. Downloads/temp/cache use D: through the launcher/install command; the virtual environment itself remains on C:.
- Tempo is refined from fitted beat times to avoid frame-lag quantization. Confidence is a heuristic, not calibrated probability. Half/double-time alternatives remain explicit.
- Analysis caches content/version/config on disk, currently independent of the SQLite analysis table; worker integration remains future work.
- Phrase starts are tentative; named key detection is deferred in favor of chroma features. Pair EQ/bass-swap is now implemented; no full-set ordering, queue execution, or UI yet.
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
