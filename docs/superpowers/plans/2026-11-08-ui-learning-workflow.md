# Owner-operated reviewed learning and test mixes

Owner requested UI buttons for learning and test mixes, without chat/CLI help.
Implement the end-to-end local workflow, extending the existing visual system.

1. Persist general workflow jobs and model registry in SQLite schema 7. Freeze
   included completed review revisions and registered source hashes at enqueue.
   Excluded/pending rows never become examples or preference negatives. Deduplicate
   active requests. One background subprocess at a time, heartbeat/lease, visible
   progress/log tail, cancellation, retry and stale-job interruption recovery.
2. Train a small CPU PyTorch supervised cue/overlap model from included decisions;
   mask unknown style labels. Audio descriptors are frozen spectral summaries.
   Preserve source-identity holdouts where possible, train-only scaling and mean
   baselines. With insufficient disjoint examples, say evaluation unavailable.
   Single-reference runs remain experimental; no automatic model promotion.
3. UI test jobs explicitly select an experimental model and an ordered source
   list. Feed predictions into source-bounded mix planning, retain every selected
   song, and use shared rendering/independent waveform checks. Record requested
   predictions and actual applied settings; fail clearly if model geometry or
   phase cannot be validated. Baseline generation remains a separate button.
   Do not silently change a selected model recipe after validation failure.
4. Add /learning with readiness, Train button, trained model/version/results,
   ordered song selection, Generate test mix / Generate baseline, persistent job
   status, cancellation/retry and native playback/download. Link it from review
   and shared navigation. Browser requests use IDs, not filesystem paths.
5. Start/resume the worker with the local server. Test persistence, source/review
   pinning, cancellation/restart/failed publication, masking/leakage, prediction,
   actual synthetic renders and real browser operations in isolated data.
   Run one actual owner-data training and test render through the job services,
   preserving the owner's reviews. No invented listening labels or promotion.

Scope excludes generative audio and learned waveform/EQ curves. UI operation
does not depend on finishing every reference review; partial timing drafts remain
excluded. Future A/B promotion requirements continue to apply.
