# Improve transition quality in the main app

Date: 2026-11-12  
Status: saved implementation plan; implementation has not started.  
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

- The main app still uses the older planner/renderer. Experimental scripts are
  not production integration.
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

- [ ] Extract reusable stereo float preparation with real context around the
  stretched excerpt and constant gain staging before encoding.
- [ ] Remove intermediate 16-bit conversion from the new audible rendering path.
  Keep separate PCM copies only for analysis tools that require them.
- [ ] Reuse Beat This, MDX and MERT through their existing isolated workers.
  Cache evidence by original audio hash, model/configuration and analysis version.
- [ ] Fit local tempo across multiple observed beats, avoiding rounded-timestamp
  median bias. Maintain consistent bar numbering across analysis chunks.
- [ ] Keep distinct beat, downbeat, vocal-activity, quieter-passage and structural
  change evidence. Mark uncertain structural/phrase boundaries as candidates.
- [ ] Preserve old cached predictions and human corrections; new analysis uses a
  new version/configuration and never overwrites earlier evidence.

Completion: any registered pair can use this foundation without experiment
filenames or fixed cue times. Missing evidence remains unknown. Mastered peaks
survive preparation without clipping introduced by an intermediate format.

## Milestone 2 — General vocal-preserving transition planner

- [ ] Implement two initial recipes: the corrected plain crossfade and the
  protected-vocal gradual handoff.
- [ ] Search supported outgoing passages and incoming intros across each song.
  Default to eight-bar overlaps; consider sixteen bars only when both songs
  provide sufficient compatible context.
- [ ] Preserve continuous source playback. A middle track must have one
  consistent source-time progression through its incoming and outgoing joins.
- [ ] Hold outgoing audio at its fixed preparation gain through the protected
  line and tail. Introduce the incoming intro gradually, reaching at most 25%
  gain before the outgoing fade begins.
- [ ] Require quieter evidence throughout the outgoing fade and its two-second
  preceding guard. Check incoming vocal activity over its entire audible overlap.
  A quiet destination bar does not establish that the current phrase has ended.
- [ ] Propose at most twelve candidates. Rank by vocal safety margin, structural
  evidence, energy/harmonic compatibility and proximity to requested play length.
- [ ] Validate actual stretched sources, local overlap windows and encoded audio.
  Missing or inconsistent beat/bar/vocal evidence sends the join for review.
- [ ] Make Generate and Compare use the same planner, envelopes and validation.
- [ ] Keep learned cue models optional. Preserve requested/applied settings;
  model proposals cannot bypass constraints or silently change their recipe.

Completion: generation chooses cues from each pair's evidence, preserves source
continuity and produces either a validated plan or actionable review items.

## Milestone 3 — Listening-based correction and application integration

- [ ] Add **Improved transitions — experimental** as a generation/Compare option.
  Preserve the current pipeline and pin the selected pipeline in each job.
- [ ] Add durable **Needs review** workflow state. Release the heavy worker while
  waiting; do not publish a questionable full set.
- [ ] Show both originals with playback, waveforms and relevant timing/activity
  evidence. Reuse the current interface/design system and timeline editor.
- [ ] Provide controls to mark **Outgoing line finishes here** and **Start the
  next song here**, then preview, save and resume.
- [ ] Explain unresolved evidence and show requested versus applied cue changes.
  Human phrase corrections can resolve vocal uncertainty; technical timing
  failures still require correction and revalidation.
- [ ] Save corrections as revisions. Resume creates a linked generation job
  using the pinned corrections, leaving the earlier job/history intact.
- [ ] Preserve stale-revision checks, cancellation, worker leases, restart
  recovery and publication fencing. Serve previews through the main app.

Public interfaces and compatibility:

- [ ] Add a versioned `pipeline` option to generation and comparison requests.
- [ ] Extend workflow persistence with `needs_review` and a durable join-preview
  job; migrate without losing job/model relationships or existing results.
- [ ] Add job transition-review read/save and resume operations.
- [ ] Add a new plan version containing relative gain automation, protected
  intervals and evidence references; continue reading old plans unchanged.
- [ ] Add an explicit **Make default** action. Persist the chosen default only
  after owner approval; never reinterpret earlier jobs with a newer pipeline.

Completion: all normal generate/correct/preview/resume/play/download operations
work from the app without chat commands or extra development servers.

## Milestone 4 — Listening acceptance and default promotion

- [ ] Retain the improved At Night → Stupidisco example as a regression reference.
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

- [ ] Native/stretched peaks above 0dBFS remain intact in float preparation and
  are gain-staged safely before encoding.
- [ ] Quantized beat timestamps, half-beat errors, bar-phase errors, half-tempo
  mistakes, local drift and irregular/missing markers are handled explicitly.
- [ ] Ongoing vocals remain protected even when a future destination bar is quiet.
- [ ] Missing, gapped or uncovered activity evidence cannot count as silence.
- [ ] Incoming gains rise over bars; protected outgoing intervals retain their
  planned gain. Verify sample-level envelope continuity.
- [ ] Source bounds, early-intro padding and tempo mappings preserve audible
  continuity without fabricated source audio.
- [ ] Adjacent joins fit within middle tracks without overlapping automation
  conflicts, source skips or duplicated playback.
- [ ] Review revisions, preview/resume jobs, cancellation, restart and publication
  guards preserve the latest playable revision and immutable history.
- [ ] Existing plans, models, mixes, reference reviews and preference votes remain
  readable after migrations.
- [ ] Browser checks cover correction, preview, resume, playback, reload and
  revision conflicts. Test votes use isolated fixtures, not owner data.
- [ ] Rejected effects cannot silently reappear through fallback or ranking.

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
