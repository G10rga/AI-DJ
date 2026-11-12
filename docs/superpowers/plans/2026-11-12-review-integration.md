# Milestone 3 execution

Extend the existing low-light listening desk; preserve its type, surfaces and
timeline evidence colors. The review's question is where the outgoing line ends
and the incoming song can enter. Put both real source waveforms/playback next to
those controls, with explicit estimates, unsaved/saved revision and preview state.

1. Migrate workflow constraints to schema 10, preserving model foreign keys.
   Add immutable job evidence, review revisions, preview jobs, version-2 saved
   plans/artifacts, listening-only comparison feedback and explicit default choice.
2. Pin public pipeline requests; finish review jobs without occupying the heavy
   worker. Fence completion by lease, cancellation and parent review revision.
3. Apply saved human vocal corrections through the planner, preserving raw model
   evidence and requested/applied cues. Keep all independent timing gates.
4. Add review read/save/preview/resume/media APIs and existing-app playback.
5. Extend Learning and Compare controls and build the review route from existing
   typography/timeline conventions. Default promotion requires an explicit owner
   approval action and is not performed during implementation.
6. Test migrations/history, stale saves/previews, cancellation/restart, routes,
   source/media hashes, correction safety and browser flows with isolated fixtures.
   Verify real worker integration, then update plan.md and HANDOFF.md. No commits.
