# Reference recording import and reviewed annotations

Owner requested this milestone on 2026-11-08 and has an hour-long recording,
its individual source songs and an ordered tracklist without timestamps.

1. Import an explicit ordered JSON manifest with exact source paths. Resolve
   paths relative to the manifest, validate all inputs before publishing, retain
   every occurrence (including repeated songs), and hash recording/source bytes.
   Store immutable import snapshots in the existing SQLite database on D:.
2. Extract bounded-chunk spectral features rather than applying the ordinary
   twenty-minute song-analysis limit to reference recordings. Suggest multiple
   tempo-aware source-window matches, retaining raw similarity and ambiguity.
   These are unreviewed anchors, not verified audible boundaries or mixer controls.
3. Export an editable annotation document. Require explicit review with source
   and recording intervals, validate bounds/order and revision conflicts, and
   append corrections without overwriting suggestions or previous annotations.
   Unknown recipe, overlap bars, vocal/energy behavior remain null. Confirmed
   observations never become pairwise preference labels automatically.
4. Expose shared services through a CLI initially. Browser annotation and durable
   worker progress follow separately. No model training/promotion in this slice.
5. Test real synthetic audio excerpts with tempo changes, unrelated audio,
   chunk boundaries, missing/mutated files, repeated sources, atomic persistence,
   annotation bounds and stale revisions. Run the existing regression suite.

Actual import/alignment and listening review depend on the owner's file paths.
All audio and derived caches stay outside Git; no commits without instruction.
