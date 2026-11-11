# Three-stage reference-to-DJ learning pipeline

## Owner direction

On 2026-11-11 the owner specified three distinct jobs:
1. Parse a reference mix and list its transitions.
2. Analyze each transition and describe what happens.
3. Learn those transitions and use that knowledge to make new sets.

The current matcher, spectral analyzer and cue network are baselines for these
jobs, not three finished trained models. Finishing a worker job is not recognition
or learning acceptance. Preserve every existing review and playable mix.

## 1. Transition parser: where and which sources?

Input: reference recording, registered originals, supplied order when available.
Output: ordered transition records with source occurrences, recording entry/exit,
source-to-recording timing maps, overlap/cut/gap status, evidence and uncertainty.
List unresolved transitions too. Repeats, loops, short joins and cuts must survive;
do not discard a row because it does not fit a supported render recipe.

Start from tempo-aware subsequence alignment and source-conditioned multi-pass
nonnegative matrix factorization (NMF). Source activations and timing paths can
locate entries/exits, rather than treating a change in loudness as a track change.
NMF is an unsupervised learning/optimization method; a large newly trained neural
network is not required just to satisfy the three-stage separation. If a learned
boundary refiner is added, train it from actual corrected boundary observations
and known synthetic examples, with provenance and independent evaluation.

The current affine matcher remains the comparison baseline. Evaluate entry/exit
errors and transition coverage on pinned human corrections, separately for
instant cuts, 0.5–2 second joins and longer overlaps. Preserve recording and source
time separately. Uncertain identity is distinct from uncertain boundary timing.

Research starting point: André, Fourer and Schwarz,
[DJ Mix Transcription with Multi-Pass NMF](https://arxiv.org/abs/2410.04198).
The repository URL given with the paper returned 404 during planning; do not
assume its implementation or a pretrained checkpoint is available.

## 2. Transition interpreter: what happens?

Input: audio on both sides of a parsed transition, original-song evidence and
timing-map uncertainty. It must also accept manually corrected boundaries.
Output: independently supported observations, a plain-language description and
an optional technique family. A type name is not the sole useful output.

Structured observations include duration, fade-in/out behavior, abrupt exits,
bass ownership/exchange, mid/upper entry order and energy trajectory. Vocal
observations require actual vocal evidence; effects and exact mixer controls
remain unknown unless separately validated. Multiple actions can coexist in one
transition. Do not force every real transition into the four renderer presets.

Use source-aware decomposition/control estimation for physical evidence and
evaluate a temporal behavior classifier over those features. Known rendered
transitions can train that classifier, including mixed techniques and short
joins, but synthetic provenance must remain explicit. Validate on real recordings
independently: a classifier merely reproducing its synthetic generator is not
proof of successful analysis of a real DJ mix. Use frozen audio representations
where they improve held-out results; do not train a large audio model from the
owner's few reviews.

Generate the written explanation from structured supported observations. Free
prose must not become an unverified target for model 3. Keep per-observation
confidence/masks; unknown bass behavior must not erase a valid boundary or an
independently supported incoming fade. Reconstruction error alone is not a
calibrated probability that a technique is correct.

Research starting point: Kim, Yang and Nam,
[subband reverse engineering](https://nime.org/proc/nime2021_87/index.html).
Existing `transition-magnitude-context-3` remains an uncalibrated baseline.

## 3. Contextual DJ learner: what should happen for a new pair?

Input training rows: source musical context near cues, supported stage-2
observations, human corrected timings and include/exclude decisions, plus explicit
A/B preferences where available. Keep human observations, inferred observations
and preferences as distinct sources of supervision.

Use a small contextual multi-task predictor/ranker with frozen audio embeddings
and structured timeline features. Predict cue/overlap preferences and supported
behavior/style targets; rank feasible deterministic transition candidates.
Unknown fields are masked individually. Retain cue/overlap learning even when
type is unknown. Automatic labels require the independently validated policy;
do not loosen the existing high-evidence gate merely to create training labels.

At inference, a set planner retains all selected valid songs, proposes order and
candidate cue/technique combinations, and applies the learned scores. The current
DSP renderer executes the selected frozen recipe and checks stretching, timing,
clipping, silence and publication. Describing a measured fade is distinct from
training/generating new waveform or EQ curves, which remain outside scope.

Evaluate on unseen sources and, when available, unseen reference mixes. Report
baselines, cue error, per-field supervision counts and held-out behavior accuracy.
Evaluate musical preference separately by listening. Never treat unobserved
alternatives or excluded reviews as fabricated preference negatives. No automatic
active-model promotion.

## Shared record and UI contract

Each transition retains a stable occurrence identity; parser versions,
interpreter versions and human review revisions are separate immutable records.
Pin recording/source hashes and the exact upstream records in every downstream
job/model. Re-running a stage does not overwrite human corrections or older
trained snapshots. Mark incompatible downstream results stale.

Expose the three operations independently: Parse reference, Analyze transitions,
and Train / Generate set. Show stage-specific results:
- Parser: expected/listed/located/unresolved transitions and timing coverage.
- Interpreter: inspected/described/uncertain observations and eligible labels.
- Learner: consumed human/inferred labels, masked targets, evaluation and model ID.

The owner reviews audible entry/exit and whether an example is worth imitating.
They are not required to know DJ terminology. A completed process with no useful
inference must say so plainly.

## Implementation order and acceptance

1. Freeze a read-only evaluation snapshot of the latest corrections. Include the
   known short joins and cuts. Do not modify real reviews to create test labels.
2. Establish versioned stage interfaces and evaluate parser improvements against
   the incumbent affine matcher before replacing the review queue's proposals.
3. Improve the interpreter against known audio transformations and held-out real
   examples; cover 0–2 second transitions explicitly. Add useful per-field
   observations without requiring a renderer category. Measure false labels.
4. Connect only validated observations to contextual training; verify lineage,
   stale handling, masks and held-out baseline comparisons.
5. Generate sets with the learned model on unfamiliar songs, preserve technical
   audio checks and collect actual listening feedback through the UI.

These are three separately evaluated learning tasks. Their existence is not
established by creating three classes, three buttons or three empty checkpoints.
