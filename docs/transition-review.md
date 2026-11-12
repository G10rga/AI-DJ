# Improved transitions in the application

Milestone 3 is implemented. Use the existing application at
`http://127.0.0.1:8005`; the review workflow does not require another server.

## Generate, correct and listen

1. Open **Learning**, select songs in the desired order and choose
   **Improved transitions — experimental** under Mixing pipeline. Choose
   **Generate improved mix**. No cue model or reference training is required.
   **Generate current baseline** explicitly retains the old pipeline.
2. A completed safe set has Play/Download actions and appears in **Mixes**.
   An uncertain join becomes **Needs review**, releases the heavy job and
   exposes **Review transition**. A questionable set is not published.
3. The review shows both originals, coarse real peak/energy waveforms, estimated
   vocal activity, downbeats, source playback and seeking. Mark **Outgoing line
   finishes here** and **Start the next song here** from their players or type
   source seconds. Optional whole-song/60-second views help inspect the passage.
4. Confirm that you listened to the outgoing completion/tail and the complete
   incoming overlap. This explicit human correction can resolve uncertain or
   conflicting model vocal estimates; it does not change those original estimates.
   The planner still keeps the two-second outgoing tail guard and supported bars.
   An optional final-song ending can resolve an unsuitable automatic closing cue.
5. **Save and preview transition** saves a revision and queues a durable preview
   job. Playback/download become available only after audio and independent
   timing checks pass. **Play from handoff** seeks into the transition context.
6. **Save and resume generation** creates a linked job using the saved correction
   revision and ordered sources. Earlier jobs, previews and playable audio remain
   in history. Reloading the browser restores them without chat or CLI commands.

If timing still fails, use **Correct timing in timeline editor**. This opens the
exact pinned source analysis. Save beat/downbeat corrections there, then preview
or resume from the original review. The new job pins the latest saved timing
revision of that same analysis ID and independently checks actual audio again.
The original review keeps its original evidence/history. Human vocal confirmation
cannot make missing or inconsistent beat/bar evidence pass.

**Compare** has the same pipeline selector. Improved alternatives use the shared
planner/renderer and are served through the app. A/B switching aligns their
nominal handoff positions. A/B/tie/neither are saved as listening-only revisions;
they do not train the old preference model. Neither excludes only the exact
rejected candidate IDs for that ordered pair. Legacy comparisons and preference
data remain unchanged.

## Default selection

The default remains `legacy-v1`. A completed improved generation's review exposes
**Make default**, disabled until the owner explicitly checks the listening and
approval statement. The server also requires `approved: true`, a completed
improved generation and an intact validated artifact. Earlier jobs always keep
their saved pipeline. No default approval was given or inferred during this work;
milestone 4 listening acceptance remains outstanding.

## Persistence and compatibility

SQLite schema 10 adds `needs_review` and `join_preview` to workflow constraints
without dropping referenced jobs/models. New tables retain immutable job evidence,
append-only correction revisions, version-2 plan/artifact snapshots, listening-only
comparison reviews and the explicit default choice. Version-2 plans include exact
relative gain automation, preparation gains, protected intervals, source evidence
references and the underlying recipe plan. `read_plan` reads either the new
`ImprovedPlan` or unchanged schema-1 `MixPlan` format.

New generation/comparison requests accept `pipeline: legacy-v1` or
`improved-transitions-1`; an omitted value resolves the persisted default once at
enqueueing. Existing jobs with no pipeline remain legacy and are never
reinterpreted. The review APIs are below
`/api/v1/learning/jobs/{id}/transition-review`: GET state; POST `save`, `preview`,
`resume`, or `make-default`. Original and validated output media routes support
byte ranges, inline playback and downloads, checking stored source/artifact hashes.

Preview/resume enqueueing checks the review revision in the same transaction as
job insertion. Completion checks the worker lease, cancellation, parent review
revision and pinned timing revisions before registering any media. Stale previews
are interrupted and cannot publish. Retry of an obsolete review revision is
rejected with a reload action. Saved earlier playable previews remain accessible
as their own explicit historical revisions. Waiting reviews survive restart and
do not hold the heavy worker; queued/running recovery retains existing behavior.

## Verification

- Full regression run: **201 tests, 195 passed, six isolated-runtime skips**.
  The final nine-test review suite also passed with the additional comparison
  feedback and timing-revision cases. Five final stale-preview/playback checks
  passed after the last retry guard. Python and JavaScript syntax/diff checks pass.
- Migration tests retain old plan/render rows and model foreign keys. Review
  tests cover stale saves, immutable source predictions, latest timing pinning,
  edits during processing, cancellation, media hashes/ranges, explicit default
  approval, listening-only feedback and ordered-pair rejection semantics.
- Real browser/worker checks ran against an isolated database and cached real
  source evidence, with the existing pinned audio/model runtimes. Source marking,
  saving, checked preview, playback, stale-save rejection, reload, linked resume,
  download/ranges, Mixes listing, tablet/phone layouts, preview cancellation,
  retained earlier audio, pipeline options and listening-only comparison feedback
  all passed. No browser console errors were recorded. Test corrections and
  votes were written only to the isolated database, not owner reviews/preferences.
- Evidence:
  `D:/AI-DJ-data/validation/review-browser-de271cdb90854d4eafe6f3ef4ff938d3/browser-check/report.json`.
  Preview `d5546a200a004b2c9466e9cacece3b6b` and linked generation
  `a59e3132a50146ceafe9f2c2b5a29fa1` completed through the actual leased worker.
- The existing True-black flat direction (saved seed 1382705394) was retained,
  including Inter, flat surfaces, lime energy/focus and amber correction marks.
  Rendered inspection at 1440/768/390px reported zero failures. One spacing warning
  was retained: the source panels reserve space for the native transport, waveform
  and seeking controls rather than placeholder content. Screenshots were reviewed
  and a real mobile selector overflow was fixed. Source lint has zero findings.
- The isolated server was stopped. The updated main app runs on port 8005;
  its state endpoint confirms `legacy-v1` remains the default. No new listening
  acceptance, owner training labels, effects, commits or external publishing.

Reproduction helpers: `scripts/review_browser_fixture.py` prepares isolated QA
state using the saved milestone-2 artifacts; `scripts/check_review_ui.mjs` runs
the real-browser flow using the local design skill's zero-dependency CDP client.
These are verification tools, not dependencies of the normal app workflow.
