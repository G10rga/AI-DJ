# Vocal-preserving planner and shared renderer

Milestone 2 supplies the experimental backend for Generate and Compare. Both
use the same proposals, continuous set geometry, sample envelopes, float renderer
and independent timing gate. Default/legacy jobs are unchanged. Public UI
selection, durable review state, corrections/resume and media integration are
milestone 3; this milestone does not claim those flows are available yet.

## Interfaces and execution

- `planning.vocal_preserving.propose_pair` returns at most twelve pinned
  candidates and structured review items. `plan_set` preserves supplied source
  order (including repeated originals as separate entries), selects compatible
  adjacent joins, and returns a plan or `needs_review`.
- `improved_transitions.generate` and `compare` consume pinned foundation
  records and original paths. `records_for_sources` obtains those records from
  registered source snapshots through the isolated foundation workers.
- `scripts.workflow_job.execute` and `pair_comparisons.generate_pair` dispatch
  explicit internal payloads with `pipeline: improved-transitions-1` to the same
  `improved_transitions.execute_job`. No default or public request schema changed.
- Results are `validated` with artifact paths and exact plans, or `needs_review`
  with codes, reasons, join/source indices, evidence and correction actions.
  Technical success of a job container is distinct from a validated plan; M3
  will add the durable workflow state and review/resume UX.

Backend validation can be run explicitly with registered catalog IDs, while no
other heavy job is running:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.render_improved OUTGOING_ID INCOMING_ID
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.render_improved OUTGOING_ID INCOMING_ID --compare
```

Generate accepts additional IDs for continuous sets. `--seconds` is a per-song
play-length preference, default 72. These commands save validation reports under
`analysis` and only technically validated MP3s under `renders`. They do not
change defaults, save owner votes, train or promote models, or run effects.

## Hard constraints and ranking

Recipes are `plain_crossfade` and `protected_vocal`. Both mix continuous master
audio in float, without separated stems in the audible output. Eight bars is
the default; sixteen requires observed sixteen-bar support on both sources,
compatible local tempo and additional real source context.

All observed bar spans across each song are searched for suitable outgoing and
incoming lower-vocal entry passages; no experiment filenames or cue times are
embedded in the planner. A lower-vocal passage is not a semantic intro/phrase
label. Evidence, compatibility and the requested length determine ranking, so
the chosen incoming region may occur later in the song. Listening acceptance
and cue corrections remain necessary for musical judgment.

The protected recipe holds the outgoing source at its fixed preparation gain
through the first half of the overlap. Incoming rises from zero to 25% across
that half, then rises to full gain as outgoing fades over the second half.
The plain recipe performs a linear exchange over the entire overlap. Both
require known quieter evidence for the complete outgoing fade plus its preceding
two source seconds, and for the entire audible incoming overlap. A quiet future
bar cannot justify cutting through active earlier audio. Unknown/gapped/legacy
RMS-only evidence cannot count as silence.

Candidates retain original/model/timeline/correction hashes, requested hints,
applied cues/recipe/bars, source tempo mappings, guard coverage, vocal safety
margin, structure support and energy/harmonic evidence. Ranking prefers eight
bars, then safety margin, structure, energy/harmonic compatibility and proximity
to the requested play preference. A bounded shortlist is conservative: it may
request review where additional human corrections could permit another join.

One fixed target tempo is used across the set, with one stretch ratio per song.
Dynamic selection considers adjacent candidates together. A middle song has one
source-in/source-out progression, its incoming automation finishes before the
next join, and at least four seconds of solo context separates adjacent joins.
Conflicts request review instead of skipping/duplicating source audio. A final
quieter ending is also required, rather than blindly cutting at a time limit.

Optional model predictions are preferences within these same constraints and a
32-second cue neighborhood. Requested/applied values are both retained. Only
explicitly supported recipe proposals are accepted; incompatible legacy model
styles, unavailable selected IDs or unsafe proposals request review. No recipe
is substituted after a failed selected render. New preference-learning features
are intentionally unavailable until milestone 5, so comparisons are ineligible
for legacy preference training.

## Audio and validation

`vocal_rendering` prepares each entire source interval once with real context
and constant gain, using milestone 1's stereo float service. It reads continuous
prepared samples in bounded blocks. `audio.vocal_automation.relative_gain` is
the single sample-based envelope implementation for both operations. Protected
middle-source plateaus start after their own incoming join, keeping automation
from conflicting. Only the final encoder quantizes audio.

`scripts.transition_timing_worker` runs in the existing isolated timeline
runtime and verifies the pinned Beat This checkpoint. It independently detects
the actual stretched sources and decoded encoded output, checks original-source
time mapping, prepared-source agreement and encoded overlap agreement for both
beats and downbeats. The full overlap and early/late halves are all checked;
complete regular bars and adjacent solo neighborhoods are also required.
Reports pin prepared/encoded hashes, exact plan ID and timing-worker hash.

Local matching retains neighbors within the declared tolerance on either side
of a query boundary. Every core marker is still accountable in both directions;
no unmatched core markers are discarded and tolerances remain 25ms for beats
and 70ms for downbeats. This avoids false mismatches when two valid detections
straddle an arbitrary half-window edge. Missing/irregular/half-tempo/bar-phase
and drift errors still fail the gate.

The renderer also checks finite stereo output, duration, overlap dropouts,
sample peak, measured true peak and source hashes before publication. Cancellation
and lease checks run between stages and before publication. A failed candidate
never falls back. Compare withholds the whole pair if either selected alternative
fails, excludes explicitly rejected candidate IDs, and requires listening levels
within 0.3 LUFS. All output files have fresh names; existing playable results and
reviewed artifacts are not overwritten.

## Verification on 2026-11-12

Full regression suite: **193 tests, 187 passed, six isolated-runtime skips**.
The added local-edge regression and existing planner/timing tests then passed
in a final **15-test run**. Tests cover both recipes, sixteen-bar context, full
vocal guards, coverage gaps, model constraints, stale selections/revisions,
continuous three-song geometry, sample envelope continuity, float block mixing,
real encoding, cancellation, no partial comparison publication, and both existing
job dispatch entry points. Changed Python modules compile and diff checks pass.

Real At Night → Stupidisco validation used full foundation analyses, not the old
research timestamps. The general planner selected original cues 68.14898s /
240.06000s and an eight-bar overlap. This is a distinct unreviewed example from
the earlier owner-reviewed 136s/intro experiment, not an inferred taste verdict.

- Generate report:
  `D:/AI-DJ-data/analysis/improved-validation-71fd89adf85f4dcb9458f748c6543a1f.json`.
  Protected handoff, 135.34s stereo, -20.00 LUFS, -8.15 dBTP; all 30 independent
  whole/early/late beat/downbeat checks and solo/bar gates passed. Native prepared
  peaks 1.200/1.408 survived in float before fixed gain staging.
- Compare report:
  `D:/AI-DJ-data/analysis/improved-validation-493301e77ce44d309d4fa3e79e0f3400.json`.
  Protected and plain recipes share the same cues and duration in this test;
  both passed all 30 timing checks. Levels -20.00/-19.99 LUFS, peaks
  -8.15/-8.11 dBTP. No feedback or preference examples were created.
- Safe abstention report:
  `D:/AI-DJ-data/analysis/improved-validation-4ce850fc39254709a09db45207f79887.json`.
  Edge of Desire → It's Not Right But It's Okay produced `no_safe_candidate`
  with actionable review items and no audio output.

The first timing pilot was withheld due to the local query-edge issue described
above. After fixing and testing the validator, the exact same selected candidate
and source intervals passed; there was no cue/recipe fallback. The earlier
failed validation report is retained. Listening acceptance remains null for all
new artifacts. Old reviewed audio, screening evidence and rejected effects remain
preserved. A real multi-song listening acceptance set is milestone 4.
