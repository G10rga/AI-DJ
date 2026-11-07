# Context-aware DJ mixing and learning workflow

## 1. Goal and agreed defaults

Build a local browser app where you select songs, generate a continuous mix, and review alternatives only for weak transitions. The system should choose **where to mix, which recipe to use, and how to control vocals and energy** based on the musical sections involved.

- Personal AfroHouse tool, running locally on Windows; audio, models and caches stay on D:.
- Include every selected valid track. Report invalid files explicitly.
- Use your A/B feedback plus annotated reference DJ mixes **with their original source tracks**.
- Preserve existing audio and feedback. The one recorded preference remains one song-pair-specific example.
- No automatic claims of DJ-level quality. Musical acceptance requires listening on previously unseen songs.

## 2. Build musical timelines before changing the decision model

Replace whole-track summaries as the main decision input with a versioned timeline containing:

- Beats, downbeats, bars and candidate phrase boundaries.
- Vocal activity, gaps and overlap risk, derived from separated vocals.
- Energy curves, rising/falling energy, drum density, bass presence and transient peaks.
- Harmonic compatibility and section-level audio embeddings.
- Confidence and provenance for every prediction; human corrections override estimates.

Use frozen **MERT-95M embeddings** for musical context and **Beat This** for pretrained beat/downbeat estimates. Preserve the existing waveform checks as independent verification. Their published implementations provide the starting points, not ready-made DJ judgment. [MERT](https://github.com/yizhilll/MERT), [Beat This](https://github.com/CPJKU/beat_this).

Derive initial section boundaries from repeated musical patterns, embedding changes and energy changes. Label buildup/drop candidates conservatively; do not invent verse/chorus labels. Provide timeline correction tools in the UI.

Run model inference in a separate Python environment, one bounded audio chunk at a time. Retain the validated DirectML vocal separator; use CPU execution for new PyTorch models initially rather than assume AMD acceleration works. Cache by audio hash, model version and configuration.

## 3. Generate choices, then learn which choices work

### Candidate generation

For each adjacent pair, evaluate several cue combinations around reliable bar and section boundaries—not just different fade lengths at one fixed location.

Support these recipes initially:

- **32-bar groove blend:** gradual percussion and EQ exchange, one dominant bass line, independent vocal handoff.
- **16-bar controlled blend:** the same controls over a shorter compatible section.
- **8-bar EQ handoff:** for sections where prolonged musical overlap is undesirable.
- **Phrase-aligned cut:** a short click-free exchange at an eligible boundary; never triggered by an energy spike alone.

Screen candidates for source bounds, overlapping incoming/outgoing regions, excessive stretching, beat drift, vocal collisions and energy collapse. Disqualify technical failures before ranking. Generate at most 12 valid plans per pair; render the best two distinct alternatives for uncertain joins.

### Learning architecture

Use PyTorch for a small contextual ranking network:

- Inputs: frozen audio embeddings around both cue points, musical timeline features, candidate settings and context–setting interactions.
- Architecture: projected audio context plus normalized structured features, followed by a small regularized scoring network.
- Training objective: pairwise preference loss from explicit A/B judgments.
- Keep the current logistic ranker and deterministic planner as baselines.

Reference mixes supply examples of **what was done in a musical context**. Confirmed annotations train a separate transition-style prediction head. They do not automatically prove that the reference choice is better than every alternative.

Keep embeddings frozen initially. Do not fine-tune the large audio model or generate waveform/EQ curves in this release.

### Reference-set workflow

Import a DJ recording and its source tracks. Suggest source-to-mix alignments using audio similarity and tempo-aware alignment, then require review of:

- Track identities and transition intervals.
- Cue positions and overlap bars.
- Recipe category and observed vocal/energy behavior.

Store unknown controls as unknown. Do not infer exact mixer settings from a finished recording or treat unobserved alternatives as negative examples.

## 4. Connect everything through one application pipeline

Replace the fixed ten-song experiment and separate pair scripts with shared services:

**Library → timeline analysis → order → cue/recipe candidates → ranking → validation → render → feedback.**

Use FastAPI, SQLite, one durable background worker, and a server-rendered browser UI with lightweight JavaScript. Keep CLI commands as wrappers around these same services.

The UI includes:

- Library selection/import and analysis progress.
- Waveform timelines with bar, vocal and energy overlays.
- Proposed track order and editable transitions.
- Full-set playback, seeking, download and timestamped tracklist.
- Loudness-matched A/B playback with synchronized comparison points.
- Feedback choices: A, B, tie, neither, plus optional reasons.
- Reference-mix annotation and model-status screens.

Expose versioned interfaces for tracks/timelines, mixes/plans, jobs, candidates, feedback, reference annotations and model versions. Use IDs in browser requests; resolve audio paths internally.

Add versioned records for timelines, candidate plans, rendered auditions, reference alignments, annotations and model evaluations. Snapshot the complete plan and model version for each render. Preserve existing feedback and retain the last playable render during failures or retries.

Automatically render a conservative draft. Queue technically valid but musically uncertain joins for A/B review; choosing an alternative updates the plan and triggers a new render. Never silently drop a track or claim an unvalidated handoff is beatmatched.

## 5. Validation, promotion and delivery order

### Testing and acceptance

- **Analysis:** check downbeat/bar placement, vocal gaps and energy events against manually corrected AfroHouse examples.
- **Audio:** retain clipping, silence, stereo, duration, stretch-limit and full-overlap phase checks. Test every rendered transition and the complete set.
- **Planning:** test buildup preservation, vocal collisions, uncertain boundaries, short songs, duplicates and tempo outliers.
- **Learning:** hold out complete reference sets and source-track identities. Do not let the same song leak across training and evaluation through different pairs.
- **Application:** test import → mix → review → feedback → retrain → regenerate, including cancellation, worker restart and failed rerenders.
- **Listening:** compare against the existing planner on unseen pairs, with loudness-matched playback. Track beat stability, vocal handling, energy continuity and overall preference separately.

Replace the current “six comparisons means ready” behavior with **experimental, evaluated and active model states**. Experimental rankings may appear immediately; they must not silently replace the active model.

For initial promotion, require at least 100 explicit comparisons spanning 20 song pairs, evaluation on at least 20 comparisons covering five unseen pairs, better preference performance than the baseline, and your listening approval. These are initial evaluation requirements—not a guarantee that the model will be good. Keep rollback to the previous model.

### Implementation sequence

1. **Unify rendering and persistence:** remove fixed-song assumptions and establish immutable candidate/render records.
2. **Add musical timelines and correction UI:** verify pretrained inference and section evidence on the existing library.
3. **Build contextual candidate generation:** validate all four recipes and render comparable auditions.
4. **Add reference import and annotation:** establish a reviewed training collection.
5. **Train contextual ranking and style prediction:** compare with the existing baselines without automatic deployment.
6. **Complete the listening workflow:** weak-join review, feedback collection, evaluated model promotion and full-set regeneration.

The first usable release must complete this workflow even with little training data. It should expose uncertainty and collect useful feedback while the conservative planner remains available.
