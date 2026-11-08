# Extract and review reference transitions

Owner accepted extracting and reviewing the actual transitions before training
on DJ decisions. Extend the established local editor; retain its visual system.

1. Pin imported recording/source hashes and the latest immutable alignment.
   Fit source-to-recording maps conservatively from supported anchors. Measure
   short aligned spectral-similarity windows near each occurrence to propose
   entry/exit bounds. These estimates require listening, not automatic approval.
   Preserve every adjacent pair, including unresolved songs, as a review task.
2. Store immutable transition draft batches and append-only per-join reviews.
   Reviews select registered source identities, edit recording/source endpoints,
   optionally label overlap bars/style/vocals/energy, and explicitly include or
   exclude the example. Only checked, explicitly included reviews export for
   decision learning. Missing controls remain null. No invented negative pairs.
3. Add local API and browser review at /references, linked beside Mixes/Timelines.
   Reuse native recording/source players, range streaming and exclusive playback.
   Show draft vs reviewed state; provide seek/mark controls, six editable times,
   notes, learning decision and explicit timing-reviewed checkbox. Save each join
   independently with optimistic concurrency. Protect dirty work on navigation,
   saving state, failure recovery and stale revisions. No heavy extraction in GET.
4. Generate the actual 40-join batch through the CLI, start the local server and
   check the real screen plus API and browser regressions on an isolated database.
   Production human review count remains zero until the owner listens and saves.
5. Export reviewed examples for later supervised cue/style training. Do not
   retrain the earlier weak successor model or claim improved transition quality
   from unreviewed drafts. Test estimation on synthetic timed sources, persistence,
   validation, stale edits, streaming restrictions, and UI workflow/responsiveness.
