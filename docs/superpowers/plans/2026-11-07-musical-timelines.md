# Musical timelines and correction editor

Continue step 2 of `2026-11-07-context-aware-workflow.md`.

1. Install a separate Python 3.12 CPU inference environment below the data root.
   Pin Beat This and MERT revisions, keep downloaded weights/caches on D: and
   record their hashes and inference configuration. Do not alter the separator.
2. Add bounded audio decoding and inference with overlap/context at beat chunk
   boundaries. Extract frozen MERT windows, time-local DSP energy/bass/onsets/
   chroma, beats/downbeats and conservative section-change evidence. Derive
   vocal activity from optional verified separated vocals; missing vocals remain
   unknown, never silent or non-vocal by default.
3. Persist immutable versioned timelines keyed by source/model/config hashes.
   Add append-only, revision-checked human corrections; preserve model estimates
   and prefer corrections in the effective timeline. Retain uncertainty and
   provenance; avoid unsupported semantic section labels.
4. Add CLI analysis and a loopback FastAPI editor with local audio playback,
   wave/energy/vocal/bar overlays, seeking and correction of beats/downbeats and
   candidate phrase boundaries. Browser requests use track IDs, not audio paths.
5. Test cache invalidation, bad timing/bounds, chunk seams, manual overrides,
   stale edits, migration and API behavior. Run actual CPU inference on an
   existing AfroHouse track, inspect the editor at desktop/tablet/phone widths,
   and distinguish inference success from musical annotation accuracy.

This slice adds timeline analysis/review; contextual candidate ranking, reference
mix annotations and the complete listening workflow follow separately.
