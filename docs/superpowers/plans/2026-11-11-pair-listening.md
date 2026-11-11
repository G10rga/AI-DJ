# Pair listening and preference learning

Owner approved the one-pair comparison milestone on 2026-11-11.

1. Reuse contextual proposals, waveform checks, stem renderer and loudness matching.
   A persistent `pair_audition` job selects two registered library sources, resolves
   missing musical timelines in the worker, proposes up to 12 candidates and renders
   two distinct alternatives. Pin existing timeline revisions and source hashes.
   Freeze any requested preference model at submission. No arbitrary cue regression.
2. Add `/compare`: two song selectors, generate/progress/cancel/retry, matched A/B
   audio with same-position switching, handoff seek, A/B/tie/neither and optional
   reason. Reuse DESIGN.md. Preserve audio nodes while polling, no autoplay on load.
3. Register matched report/audio identities in the existing preference database.
   Extend ranking with contextual evidence and missing-value masks; pad legacy
   vectors without changing saved reports. Tie/neither clear the current pairwise
   winner, remain explicit history, and never imply a fabricated winner or rating.
4. Publish only complete two-audio results under the existing worker lease and
   cancellation guard. A technical failure stays visible. Feedback requires the
   exact successful comparison and current immutable bytes. Expose learning counts,
   held-out song-pair evaluation and an explicit experimental ranking opt-in.
5. Verify migration, neutral/reversed feedback, provenance/cancellation, source
   identity/media routes and browser playback. Generate a real pair with existing
   timelines. Never save listening feedback on behalf of the owner.
