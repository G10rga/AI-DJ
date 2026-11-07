# Shared rendering and persistence implementation

Resumed from `2026-11-07-context-aware-workflow.md` on 2026-11-07.

1. Extract library input collection and atomic plan registration from the CLI
   into application services. Retain duplicate uploads as separate entries and
   report invalid files without silently rendering a smaller playlist.
2. Extract the ten-track renderer into a callable service accepting entries,
   a validated plan, settings and separator configuration. Replace fixed catalog,
   track counts and D: paths with inputs and configured storage.
3. Persist append-only render attempts with immutable requested-plan snapshots,
   model provenance and final applied-cue/recipe reports. Publish a validated
   render transactionally; failures and stale completions keep the last playable
   revision. Preserve existing feedback and SQLite data.
4. Make plan/render CLIs wrap these services. Validate source hashes, honor
   boundary handoffs and check overlap geometry before mixing; record every cue
   shift, PCM delay and trim rather than misreporting the requested plan as the
   applied audio.
5. Add regression checks for atomic registration, retries/failures, stale render
   publication, duplicate inputs and variable track counts. Exercise the shared
   audio renderer with generated stereo audio and an injected separator (no model
   downloads); run the existing suite.

This milestone establishes the shared set pipeline. Pair-specific experimental
scripts and their existing feedback store remain compatible. Timeline inference,
the browser UI and contextual model training follow in later milestones.
