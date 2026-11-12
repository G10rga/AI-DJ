# Improve transition quality in the main app

Date: 2026-11-12  
Status: milestones 1–3 complete; milestone 4 timing regressions fixed; remaining source reviews and owner listening acceptance pending.
Project: `C:/Users/user/Documents/GitHub/AI-DJ`  
Local data: `D:/AI-DJ-data`

## Instructions for another session

Read `AGENTS.md`, `HANDOFF.md`, then this file. This plan is an executable work
checklist, not a shell script. Start implementation when the owner requests it;
saving this file does not activate the new mixer or start implementation.

Proceed through milestones in order. Update checkboxes and the execution log as
work completes. For each milestone, record changes, checks, remaining limitations
and listening evidence. Do not mark listening acceptance from technical tests.
Do not commit or publish externally unless the owner asks.

The working tree already contains substantial prior work. Inspect it before
editing and preserve all existing source changes, reviews, audio and model data.
Run Python commands from the repository root: the owner's home directory has an
unrelated `random.py` that can shadow Python's standard library.

## Agreed goal and decisions

Turn the improved vocal-preserving experiment into a reusable pipeline for
ordinary Generate and Compare operations, on arbitrary registered song pairs.

Owner selected:

- Main-app quality improvement is the first milestone; reference-model training
  is not the prerequisite for this release.
- Uncertain joins request correction instead of publishing a questionable set.
- Corrections are made by listening and marking outgoing vocal completion and
  incoming entry points.
- Effects are staged after the baseline passes listening validation.
- The improved pipeline is offered experimentally first and becomes the default
  only after listening tests and explicit owner approval.

Preserve selected song order. The requested play length is a preference;
preserving a vocal line takes priority. Use the existing pinned models and
isolated workers. Do not train a new large waveform model for this milestone.

## Current evidence and integration points

- Default app jobs still use the older planner/renderer. The shared experimental
  Generate/Compare backend and its visible durable review/resume workflow are
  now available through milestones 2 and 3.
- The owner said "its better" about the continuous handoff in
  `D:/AI-DJ-data/experiments/open-dj/auditions/vocal-handoff-fdc44c762ab34ca8990521d1b53addc0/`.
  Treat that as qualitative improvement, not a rating or full acceptance.
  See `docs/vocal-handoff.md` for source intervals, provenance and reproduction.
- The loop/filter/delay v1 recipe is rejected and disabled. It jumped to a future
  bar during an ongoing vocal and introduced the next song through a 5ms ramp.
  Preserve its rejection. Pedalboard itself was not rejected.
- Existing bass-pulse checks passed previews the owner found off beat. The later
  independent beat/downbeat checks detected bar mismatch or uncertainty. A
  periodic bass-pulse fit alone is insufficient validation.
- Intermediate PCM16 preparation clipped stretched/mastered peaks. Keep the new
  audible processing path floating point until final encoding.
- The current interpreter recognized only 2/22 UnmixDB examples, with 1/22
  correct. Preserve uncertainty; do not turn these estimates into confident
  teaching labels.

Relevant code:

- Main generation: `scripts/workflow_job.py`,
  `backend/app/planning/decision_plan.py`, `backend/app/rendering.py`.
- Contextual proposals and Compare: `backend/app/planning/contextual.py`,
  `backend/app/auditions.py`, `backend/app/pair_comparisons.py`.
- Useful experimental logic: `backend/app/research/steady_bars.py`,
  `backend/app/research/beat_alignment.py`,
  `backend/app/research/vocal_handoff.py`, `scripts/render_vocal_handoff.py`.
- App workflow/persistence: `backend/app/workflow.py`,
  `backend/app/workflow_manager.py`, `backend/app/db.py`, `backend/app/models.py`.
- Existing UI: `backend/app/web.py`, `backend/app/web_assets/learning.*`,
  `backend/app/web_assets/compare.*`, the timeline editor, and `DESIGN.md`.

Reuse the research logic through production services; do not shell out to a
hardcoded experiment script or copy its timestamps into the main planner.

## Milestone 1 — Shared audio and analysis foundation

- [x] Extract reusable stereo float preparation with real context around the
  stretched excerpt and constant gain staging before encoding.
- [x] Remove intermediate 16-bit conversion from the new audible rendering path.
  Keep separate PCM copies only for analysis tools that require them.
- [x] Reuse Beat This, MDX and MERT through their existing isolated workers.
  Cache evidence by original audio hash, model/configuration and analysis version.
- [x] Fit local tempo across multiple observed beats, avoiding rounded-timestamp
  median bias. Maintain consistent bar numbering across analysis chunks.
- [x] Keep distinct beat, downbeat, vocal-activity, quieter-passage and structural
  change evidence. Mark uncertain structural/phrase boundaries as candidates.
- [x] Preserve old cached predictions and human corrections; new analysis uses a
  new version/configuration and never overwrites earlier evidence.

Completion: any registered pair can use this foundation without experiment
filenames or fixed cue times. Missing evidence remains unknown. Mastered peaks
survive preparation without clipping introduced by an intermediate format.

## Milestone 2 — General vocal-preserving transition planner

- [x] Implement two initial recipes: the corrected plain crossfade and the
  protected-vocal gradual handoff.
- [x] Search supported outgoing passages and incoming intros across each song.
  Default to eight-bar overlaps; consider sixteen bars only when both songs
  provide sufficient compatible context.
- [x] Preserve continuous source playback. A middle track must have one
  consistent source-time progression through its incoming and outgoing joins.
- [x] Hold outgoing audio at its fixed preparation gain through the protected
  line and tail. Introduce the incoming intro gradually, reaching at most 25%
  gain before the outgoing fade begins.
- [x] Require quieter evidence throughout the outgoing fade and its two-second
  preceding guard. Check incoming vocal activity over its entire audible overlap.
  A quiet destination bar does not establish that the current phrase has ended.
- [x] Propose at most twelve candidates. Rank by vocal safety margin, structural
  evidence, energy/harmonic compatibility and proximity to requested play length.
- [x] Validate actual stretched sources, local overlap windows and encoded audio.
  Missing or inconsistent beat/bar/vocal evidence sends the join for review.
- [x] Make Generate and Compare use the same planner, envelopes and validation.
- [x] Keep learned cue models optional. Preserve requested/applied settings;
  model proposals cannot bypass constraints or silently change their recipe.

Completion: generation chooses cues from each pair's evidence, preserves source
continuity and produces either a validated plan or actionable review items.

Implementation and evidence: [docs/vocal-planner.md](docs/vocal-planner.md).
Both existing job entry points route explicitly pinned experimental payloads to
the shared backend. Public pipeline controls, media/review/resume persistence
and the durable `needs_review` workflow state remain milestone 3. Default jobs
remain unchanged; structured backend review results do not claim listening
acceptance or completed correction UX.

## Milestone 3 — Listening-based correction and application integration

- [x] Add **Improved transitions — experimental** as a generation/Compare option.
  Preserve the current pipeline and pin the selected pipeline in each job.
- [x] Add durable **Needs review** workflow state. Release the heavy worker while
  waiting; do not publish a questionable full set.
- [x] Show both originals with playback, waveforms and relevant timing/activity
  evidence. Reuse the current interface/design system and timeline editor.
- [x] Provide controls to mark **Outgoing line finishes here** and **Start the
  next song here**, then preview, save and resume.
- [x] Explain unresolved evidence and show requested versus applied cue changes.
  Human phrase corrections can resolve vocal uncertainty; technical timing
  failures still require correction and revalidation.
- [x] Save corrections as revisions. Resume creates a linked generation job
  using the pinned corrections, leaving the earlier job/history intact.
- [x] Preserve stale-revision checks, cancellation, worker leases, restart
  recovery and publication fencing. Serve previews through the main app.

Public interfaces and compatibility:

- [x] Add a versioned `pipeline` option to generation and comparison requests.
- [x] Extend workflow persistence with `needs_review` and a durable join-preview
  job; migrate without losing job/model relationships or existing results.
- [x] Add job transition-review read/save and resume operations.
- [x] Add a new plan version containing relative gain automation, protected
  intervals and evidence references; continue reading old plans unchanged.
- [x] Add an explicit **Make default** action. Persist the chosen default only
  after owner approval; never reinterpret earlier jobs with a newer pipeline.

Completion: all normal generate/correct/preview/resume/play/download operations
work from the app without chat commands or extra development servers.

Completed interfaces, evidence and limits: [docs/transition-review.md](docs/transition-review.md).
The current default remains legacy; no listening acceptance/default approval was
inferred. The updated main application is available at http://127.0.0.1:8005.

## Milestone 4 — Listening acceptance and default promotion

- [x] Retain the improved At Night → Stupidisco example as a regression reference.
- [ ] Freeze five unfamiliar pairs covering different vocal/rhythmic situations
  before tuning on their results. Distinguish regressions from independent tests.
- [ ] Produce loudness-matched comparisons against the plain-crossfade baseline.
- [ ] Record actual owner verdicts and specific defects. Do not treat "better"
  as a numeric rating, pairwise vote or full acceptance.
- [ ] Test a five-song continuous set for complete vocal lines, gradual entrances,
  stable rhythm, continuous middle tracks and consistent energy.
- [ ] Investigate failed examples, correct the implementation and rerun affected
  checks. If evaluation examples drive tuning, use fresh examples for subsequent
  independent quality claims.
- [ ] Obtain explicit owner approval before switching the persisted default.

Execution: five unfamiliar-to-this-pipeline pairs and a fixed five-song order are frozen
before new results. All six original jobs finished as Needs review; diagnosis
found vocal-activity constraints block all five pairs. Source-boundary listening,
matched comparisons, continuous-set playback and owner verdicts remain pending.
See [docs/listening-acceptance.md](docs/listening-acceptance.md).

Timing follow-up: fixed short-context/level-sensitive detector false positives
using a fixed 24-second analysis context and consistent input levels. Forty
targeted tests, five exact-plan real replay cases and four deliberately corrupted
audio cases passed their expected outcomes. Latest corrected short-edit preview
is playable; other source reviews/full-set listening and default approval remain
pending. Replay cases are regressions, not five new independent pair results.

Completion: the improved pipeline is usable in the main app, passes the technical
checks below and receives actual listening approval for default promotion.

## Milestone 5 — Effects, then preference learning

Start only after baseline listening acceptance. Evaluate one recipe at a time:

- [ ] **Filter blend:** a restrained sweep over an already suitable gradual handoff.
- [ ] **Echo-out:** start after outgoing vocal completion and preserve a decaying tail.
- [ ] **Instrumental loop blend:** capture a completed, immediately preceding
  instrumental bar, preserve its beat clock and introduce the next song gradually.

For each recipe:

- [ ] Require appropriate passage evidence including the actual playback point.
  Never jump to a lower-vocal future bar to justify cutting a current line.
- [ ] Retain float stereo processing, click-safe seams, stateful effect processing,
  beat-synced delay and explicit tail handling.
- [ ] Compare with a matched baseline and collect separate listening feedback.
- [ ] Keep rejected loop/filter/delay v1 disabled and old feedback immutable.

Learning follow-up:

- [ ] Extend versioned preference features to represent the new controls before
  using their comparisons for ranking. Preserve unknown masks and legacy data.
- [ ] Train/rank only from explicit eligible feedback and evaluate on held-out
  source pairs. Apply hard musical constraints before learned ranking.
- [ ] Keep reference parsing and interpretation separately evaluated. Improve
  their structured observations before admitting new automatic teaching labels.

Completion: each enabled effect recipe has its own listening evidence. Pedalboard
is an effects engine; musical placement remains the planner's responsibility.

## Required technical test scenarios

- [x] Native/stretched peaks above 0dBFS remain intact in float preparation and
  are gain-staged safely before encoding.
- [x] Quantized beat timestamps, half-beat errors, bar-phase errors, half-tempo
  mistakes, local drift and irregular/missing markers are handled explicitly.
- [x] Ongoing vocals remain protected even when a future destination bar is quiet.
- [x] Missing, gapped or uncovered activity evidence cannot count as silence.
- [x] Incoming gains rise over bars; protected outgoing intervals retain their
  planned gain. Verify sample-level envelope continuity.
- [x] Source bounds, early-intro padding and tempo mappings preserve audible
  continuity without fabricated source audio.
- [x] Adjacent joins fit within middle tracks without overlapping automation
  conflicts, source skips or duplicated playback.
- [x] Review revisions, preview/resume jobs, cancellation, restart and publication
  guards preserve the latest playable revision and immutable history.
- [x] Existing plans, models, mixes, reference reviews and preference votes remain
  readable after migrations.
- [x] Browser checks cover correction, preview, resume, playback, reload and
  revision conflicts. Test votes use isolated fixtures, not owner data.
- [x] Rejected effects cannot silently reappear through fallback or ranking.

Useful existing regression command (run from the repository root):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m unittest tests.test_vocal_handoff tests.test_loop_effects tests.test_steady_bars tests.test_beat_alignment tests.test_dj_benchmarks tests.test_transition_analysis tests.test_pair_comparisons
```

Native Pedalboard checks use the separate effects runtime:

```powershell
& D:\AI-DJ-data\experiments\open-dj\pedalboard-runtime\Scripts\python.exe -m unittest tests.test_loop_effects -v
```

Add targeted production integration/migration tests as the milestones land.
Technical success is necessary, but musical acceptance requires listening.

## Execution log

| Date | Milestone | Changes and validation | Remaining work |
|---|---|---|---|
| 2026-11-12 | Plan saved | Owner choices captured; no implementation started. | Begin milestone 1 when execution is requested. |
| 2026-11-12 | Milestone 1, first slice | Added versioned context-aware stereo float preparation and fixed gain staging; handoff runner uses the shared service. Extracted observed local bar fits with source-wide indices and conservative phase/drift checks. Real synthetic DSP tests cover peaks above full scale, tempo/pitch, stereo, bounds, explicit inaudible padding and short/nonfinite decode rejection. | Finish versioned worker/evidence integration (including relative vocal levels and coverage). Generate/Compare integration remains in later milestones. No new listening evidence or default promotion. |
| 2026-11-12 | Milestone 1 completed | Shared registered-pair analysis service, new immutable profile, verified MDX cache, float screening, source-relative vocal bins with actual coverage, distinct quiet/structural/phrase candidates and source-wide bar fits. Real Beat This/MERT/MDX validation on Edge of Desire / It's Not Right But It's Okay passed; repeat calls returned identical evidence and all 3 prior predictions were unchanged. The refactored At Night/Stupidisco runner passed prepared and encoded timing gates, retaining raw peaks 1.429/1.058 before gain and final -20 LUFS / -4.46 dBTP. See docs/transition-foundation.md for reports and limitations. | Begin milestone 2. No listening acceptance, new effects, default promotion or commits. |
| 2026-11-12 | Milestone 2 completed | Added bounded vocal-preserving proposals, two recipes, global continuous set selection, shared float envelopes/renderer, isolated original/prepared/encoded timing checks and opt-in backend job dispatch for Generate/Compare. Full suite 193 tests: 187 passed, six skips; final 15 planner/timing tests passed. Real Generate and both same-cue Compare recipes passed 30 timing checks each; an unsupported second pair returned review without audio. See docs/vocal-planner.md. | Milestone 3: public experimental option, durable needs_review, correction/preview/resume/media integration and pinned plan persistence. Listening acceptance/default promotion remain later milestones. |
| 2026-11-12 | Milestone 3 completed | Public experimental pipeline selector, durable review/preview jobs, revisioned source corrections, linked resume, version-2 saved plans, protected publication/media routes, existing Mixes/Compare playback and explicit default approval. Full suite 201 tests: 195 passed, six skips; final review and playback checks passed. Isolated real browser/audio-worker flow passed correction/preview/play/resume/reload/download/cancel/history and listening-only comparison feedback; 1440/768/390px inspection had zero failures. See docs/transition-review.md. | Milestone 4 listening acceptance and explicit owner default approval. Main app on 8005; default remains legacy-v1. No commits or owner test votes. |
| 2026-11-12 | Milestone 4 started | Retained hash-verified At Night/Stupidisco regression; froze ten distinct new-to-improved-pipeline sources in five ordered pairs and one five-song integration order. Queued five comparisons and one continuous set through the existing single worker. Immutable manifest, resumable report and no-vote/default guards added. | Model analysis, baseline comparison coverage, actual owner verdicts, corrections, full-set listening and explicit default approval remain pending. |

Implementation notes after milestone 1:

- `backend/app/audio/float_prepare.py`: reusable preparation in bounded-memory
  blocks. It hashes source/result, preserves float peaks, and never pads a short
  decode to invent audible samples. A fresh output path is required.
- `backend/app/audio/bar_evidence.py`: fits source-wide observed markers without
  assuming phrase completion. Research `stable_spans` delegates to this service
  while retaining its older leading/trailing-context defaults.
- `scripts/render_vocal_handoff.py` now delegates preparation and constant gain
  to the shared service. A fresh regression revision passed model-backed timing,
  format/peak/dropout checks; reviewed originals were retained.
- `backend/app/timeline_analysis.py` owns application analysis and
  `analyze_registered_pair`; `scripts/analyze_timeline.py` remains a compatible
  CLI wrapper. The opt-in `transition-foundation-1` profile keys new evidence by
  original hash, pinned models, runtime/configuration and analysis implementation.
  Experimental caches are explicitly selected and do not hide legacy timelines
  or human corrections. Corrections stay pinned to their original analysis ID.
- `audio/analysis_evidence.py` provides relative vocal bins, complete-interval
  queries, quiet candidates and separate structure/phrase candidates. The worker
  records actual source/context/stem provenance and source-time coverage. Missing
  evidence stays unknown. `audio/separation_cache.py` verifies hashes and model/
  parameter/runtime identity in its own namespace, preserving historical caches.
- The legacy main-app renderer still uses its existing preparation. The float
  path is now consumed by milestone 2's explicit experimental Generate/Compare
  backend and milestone 3's public controls. Default jobs remain legacy until
  explicit owner approval. Application/review checks passed; listening acceptance
  remains milestone 4.
- Validation: 77 targeted tests ran successfully (75 passed, two native
  Pedalboard tests skipped in the application runtime), including timeline
  immutability/corrections, existing rendering/publication, pair comparisons,
  independent timing and the nine new preparation/bar-evidence tests. Changed
  Python modules compile. No native effects implementation changed.
- Completion validation also passed 86 targeted tests (84 passed, two native
  effects skips) and a subsequent 34-test run covering profile selection and real
  LUFS/true-peak gain staging before MP3 encoding. Final full suite: 177 tests,
  171 passed, six isolated-runtime skips; a final nine-test foundation rerun
  passed after the catalog hash guard. Reports and limits are recorded
  in docs/transition-foundation.md. The new model evidence is not listening
  approval, semantic phrase recognition or an end-to-end main-app planner.
