# Local transition analysis

Owner approved automatic technique analysis on 2026-11-11. Human timing and
include/exclude decisions remain authoritative; technique knowledge is optional.
This authorizes inferred style supervision, not learned waveform/EQ rendering.

1. Fit nonnegative outgoing/incoming spectral power contributions in bass,
   mids and upper frequencies from the recording and aligned original spectra.
   Use bounded local offset refinement, temporal pooling and conditioning /
   reconstruction checks. Explain observable changes, abstaining on poor fits.
   Use existing 4 Hz / 32-band feature caches. This is an approximation: no exact
   mixer controls, vocal detection, effect identification or calibrated certainty.
2. Persist immutable analysis snapshots through the existing leased job worker.
   Pin saved review revisions, source/recording hashes and algorithm version.
   Single and batch buttons; progress, cancellation and retry in the review UI.
   Failed/cancelled work must not publish labels. Edits invalidate old estimates.
3. Preserve human exports. Augment training snapshots separately with supported
   inferred recipe labels, lower weight and explicit provenance. Human recipes
   take precedence. Recipe mapping requires observed behavior AND supported bar
   duration, never overlap seconds alone. Unknowns stay masked. Distinguish human
   style evaluation from agreement with automatic labels.
4. Verify source attribution with constructed mixtures, ambiguity and mismatch
   abstention; pinning, cancellation, migration and training provenance tests;
   existing review/workflow tests; real saved examples and browser controls.
   Do not alter reviews, train models or claim listening approval automatically.
