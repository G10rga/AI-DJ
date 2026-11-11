# Agent instructions — ai-dj-set

## Deterministic loop effects preview (2026-11-12)

Owner rejected loop/filter/delay v1: outgoing vocal cutoff and abrupt incoming
entry. It is disabled in the research runner. Preserve the rejection and do not
rerun or promote that recipe. Any replacement needs an actual phrase-aware plan;
a low-vocal destination bar does not prove the ongoing vocal phrase has ended,
and a click-safe 5ms ramp does not constitute a gradual musical entrance.

Owner explicitly approved one loop → filter → beat-synced delay → bar-boundary
release experiment using Pedalboard on the corrected At Night / Stupidisco pair.
Plan: `docs/superpowers/plans/2026-11-12-loop-filter-delay.md`. Preserve corrected
baseline and all reviewed artifacts, timing gates, float/stereo processing,
isolated dependency runtime and exact effect-control provenance. No automatic
default activation, new training labels or generative-waveform model scope.

## External benchmarks (2026-11-11)

Owner approved UnmixDB evaluation and isolated pretrained DJtransGAN inference.
This is an explicit exception for an experimental learned fader/EQ generator,
not default mixer promotion or training new learned curves. Follow
`docs/superpowers/plans/2026-11-11-open-dj-benchmarks.md`. Preserve owner labels
and runtimes; require verified artifacts and strict tensor-only model loading.

## Pair listening (2026-11-11)

Owner approved contextual matched A/B auditions and listening-based preference
learning. `/compare` owns generate/cancel/retry/play/switch/A/B/tie/neither.
See `docs/pair-listening.md`. Preserve neutral decisions, legacy feedback,
source/timeline/model provenance and the explicit experimental ranking opt-in.
Neither excludes only those explicitly rejected candidate IDs for that ordered
pair. Never save test votes in owner data or claim technical checks prove taste.

## Automatic transition analysis (2026-11-11)

Owner approved local technique inference from reference transitions and originals.
See `docs/transition-analysis.md` and the 2026-11-11 implementation plan. Automatic
style estimates are distinct from human reviews, pinned to exact revisions and
hashes, abstaining on uncertain fits. Supported high-evidence estimates may fill
unknown training styles at lower weight; human labels take precedence. Do not
rewrite saved reviews or treat automatic-label agreement as human accuracy.
This extends style supervision only, not learned waveform/EQ rendering.

## Read first

1. [HANDOFF.md](HANDOFF.md) — current state and open questions  
2. [docs/superpowers/specs/2026-10-30-ai-dj-set-design.md](docs/superpowers/specs/2026-10-30-ai-dj-set-design.md) — design  

## Rules

- Prefer chat over HTML mockup companions unless the owner asks for visuals.  
- **No product code** until design is approved and open questions in HANDOFF are answered and written into the design.  
- After approval: write an implementation plan before large builds.  
- Optimize for **transition quality** on house music; ML in v1 is order + transition style only.  
- Deeper “learned blend sound” ML is explicitly future — do not sneak it into v1.  
- Owner authorized an optional pretrained local vocal/instrumental separator on 2026-11-06 to mix mid-song with independent vocal fades. This is an explicit exception for source separation, not permission to train or generate learned blend curves. See `docs/superpowers/plans/2026-11-06-vocal-stem-transition.md`.
- Personal tool on owner’s Ubuntu + domain; skip multi-user/billing polish.  
- Owner authorized feedback-driven candidate preference learning on 2026-11-07. Learn settings rankings from explicit ratings/comparisons; no fabricated owner labels, generative blend audio or learned waveform curves. See `docs/superpowers/plans/2026-11-07-preference-learning.md`.

## Resumed context-aware workflow (2026-11-07)

The owner requested resuming the Plan mode design in
`docs/superpowers/plans/2026-11-07-context-aware-workflow.md`.
Implement in its stated order, starting with shared rendering and persistence.
The newer plan extends the earlier order/style-only scope to musical timelines,
frozen embeddings, reviewed reference annotations and contextual ranking.
Generative audio and learned waveform/EQ curves remain outside scope.
Use `docs/superpowers/plans/2026-11-07-rendering-foundation.md` for the first
implementation slice. Do not treat synthetic technical checks as listening approval.

Step 2 implementation/usage: `docs/superpowers/plans/2026-11-07-musical-timelines.md`
and `docs/timeline-usage.md`. UI design authority is now `DESIGN.md` with tokens in
`.impeccable/design.json`; keep the local timeline editor consistent with it.
New model adapters must load checkpoints strictly and preserve model provenance.

Step 3: `docs/contextual-transitions.md` and
`docs/superpowers/plans/2026-11-07-contextual-candidates.md`. Contextual proposal
scores are heuristic, not a trained owner-preference model. Preserve immutable
candidate snapshots and requested/applied settings. Never silently change the
recipe of a selected contextual join after a technical failure.

Step 4 CLI foundation: `docs/reference-import.md` and
`docs/superpowers/plans/2026-11-08-reference-import.md`. Reference imports retain
the supplied order and repeated occurrences. Alignment anchors are unreviewed
proposals; only explicit human annotations may become observed-style examples.
Keep unknown controls null and never treat unobserved alternatives as negatives.

Owner explicitly requested training on HouseMixN3 on 2026-11-08. The implemented
experiment uses positive-only automatic successor context, not fabricated style
or preference labels. See `docs/reference-learning.md`. Its held-out result loses
to the mean baseline; keep it experimental/inactive and preserve the evaluation.

## Commits

Owner requested click-based training and test generation on 2026-11-08.
`/learning` now owns that workflow; see `docs/ui-learning.md` and
`docs/superpowers/plans/2026-11-08-ui-learning-workflow.md`. Schema 7 stores
persistent jobs, worker leases and experimental decision-model versions.
Train only pinned latest completed/included human reviews; pending/excluded
rows are neither examples nor negatives. Preserve unknown style masks, strict
checkpoint/hash provenance, source-disjoint evaluation and the mean baseline.
This supervised cue/overlap model differs from the earlier successor experiment.
Models apply only to requested test jobs, never automatic active promotion.
Keep cancellation/publication guards, exact ordered source entries and requested/
applied cue provenance. A nearby rhythm-supported cue search is bounded to 32s;
the frozen model recipe must fail visibly rather than silently fall back.
Normal train/test/cancel/retry/play/download operations must remain available in
the UI without chat or CLI. Preserve actual owner reviews and playable results.

Reference transition listening review: `docs/reference-review.md`. Draft/search
ranges are unreviewed estimates. Only saved, explicitly included human reviews
export as cue/style observations; saving does not automatically train a model.
Preserve independent per-join revisions and keep unknown controls unlabeled.

Only commit when the owner asks. Do not commit secrets or large audio fixtures.
