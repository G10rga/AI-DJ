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
## Saved marks and listening confirmation

### Stable detector inputs and current preview status

Version `improved-audio-timing-3` uses a fixed 24-second context around each
handoff, clamped to real available audio. The detector receives a consistently
normalized input: mono RMS target 0.1 with mono peak cap 0.98. Silence or channel
cancellation stays unknown rather than being amplified into invented beat
evidence. This changes analysis inputs only; rendered audio is unchanged.
Policy implementation hashes, exact frame windows and measured normalization
gains are retained in every timing report. The original 25ms beat / 70ms
downbeat tolerances, coverage, 4/4, solo and publication guards remain intact.

This fixes a broader issue than the earlier cached-grid recheck: short excerpts
could make the model predict extra or half-beat events depending on level and
musical context, even in matching source/encoded solo passages. On identical
captured audio, normalized 8-second context still fails while the fixed longer
context passes all 30 comparisons and both solos. New failures identify the
source/rhythm-validation stage instead of repeating the old catch-all message.

The page's revision line follows the newest attempt for the selected transition,
showing Transition preview ready after success. It no longer presents the
original parent job's durable Needs review state as the current preview result.
Old history/results remain available and are explicitly labelled Earlier attempt.
Reasons are scoped to the transition selected in the dropdown.

Validation: 40 targeted tests passed. Five real frozen-plan replays passed,
including three prior failed attempts and two successful examples. The successful
examples retain bit-identical audio. Deliberately shifting a preparation by half
a beat, shifting bar phase by one beat, introducing 2% tempo drift, and shifting
encoded PCM were all rejected by the real pinned worker. These are regression
checks, not independent listening acceptance. Read-only desktop/390px browser
checks passed for ready status, history labels, media availability and overflow.

The latest revision-9 preview `531a62c658b5440e994b2e46a7a2ea25` succeeded with
unchanged cues/plan, all 30 initial checks aligned, both solo checks aligned,
and verified HTTP 206 playback. Evidence:
`D:/AI-DJ-data/validation/systemic-timing-02033e355fb947898206a041ae2b78ab/`
and `D:/AI-DJ-data/validation/timing-regressions-35c29f9b20254308b8fb93426a79e0d5/`.

Reproduce isolated real replays with
`powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.replay_timing_validation`.
Resume their exact implementation with
`--session <directory>`; changed implementations require a fresh replay session.
`scripts.check_timing_faults <captured-directory>` tests real deliberate faults
without publishing audio or writing owner votes.

### Context-sensitive cached beat grids

The independent worker can resolve a cached-original mapping mismatch through
an explicit same-passage original recheck. Eligibility requires that every
prepared-pair, encoded, solo and bar-support check already passes; missing or
unknown evidence cannot use this path. It decodes the hash-verified original
window corresponding exactly to the actual preparation and detects both raw
and preparation-gain variants with the pinned model.

Every whole/early/late beat and downbeat comparison must pass at the existing
25ms/70ms limits. Both variants must account for 100% of cached markers within
those limits and independently match the prepared audio with regular 4/4 bars.
The original failed measurements stay marked mismatch, with `resolved_by` links
to `original_context_recheck`. Reports use `improved-audio-timing-2`; hashes,
source windows, gain, detections and resolution checks remain available. No
original reviews or source timelines are rewritten.

Real validation: original job `3149351b716b4528a70aed8ba8a68a33` had 29/30 initial
checks passing. Two cached outgoing beat positions differed by ~30ms, while
same-context original reanalysis matched the preparation within the existing
limits. Rerender `94524e3c890f4afabef856d51f820e89` retained the exact plan ID and
corrections and completed with validated audio. Cached-to-local coverage was
100%; minimum local-to-prepared coverage was 92.86%, above the unchanged 90%
requirement. HTTP 206 playback and artifact hashes passed. 35 targeted tests
passed, including rejection of actual shifts, wrong phase, missing variants,
unaccounted cached markers, unknown checks and bad solos. Listening is pending.
Evidence: `D:/AI-DJ-data/validation/timing-diagnosis-728ed7768f7f4915b0ea2855a1e7873f/`.

### Placement conflict follow-up

For the short-vocal-edit pair, the owner marked second-song entrance 111.165s,
outgoing vocal completion 140.813s, and incoming source start 20.289s. The current
8/16-bar protected envelopes cannot hold the outgoing vocal that long from the
requested entrance. The planner now returns `entry_before_vocal_tail` with exact
times and a lower bound (128.046s) instead of the generic placement error.

Incoming source starts now snap to the nearest detected downbeat within half a
source bar, then still require a fitted span within 250ms. The requested mark is
preserved. This fixes the prior mismatch between promised snapping and rejecting
the owner's 20.289s source point, 0.549s from a downbeat. A read-only proposal
check without the fixed outgoing entrance finds an 8-bar protected candidate at
137.097s outgoing / 19.740s incoming. This is planner feasibility, not a rendered
audio or listening pass. No owner corrections were changed.

The existing 23-test review/planner suite and two targeted snapping/conflict tests
passed. The app was restarted successfully after the owner's explicit restart
request, resolving the earlier automatic-review block. New previews use this
fix; stored historical failures keep their original messages. Saved marks and
the legacy default remain unchanged.

### Place the second song on the first song

On the outgoing (first) player, seek to the desired entrance and click **Bring
next song in here**. A dashed amber **Next song enters** marker appears there.
The optional **Second song enters first at** field edits the same source-time
position. **Start within second song** separately chooses the second track's own
starting passage. The outgoing vocal-end mark retains its separate purpose.

This optional value is stored as `incoming_at_outgoing` on the join correction.
The planner snaps it to the closest outgoing downbeat within half a bar and
requires a supported fitted span within 250ms of that downbeat. Requested and
applied source cues remain visible. A conflicting vocal-end/placement returns
review; no tail guard or independent timing check is bypassed. Editing any
source mark clears listening confirmation, so listen and confirm before preview.
Existing reviews without this optional field keep their previous behavior.

Validation: 23 review/planner tests passed. An isolated real-browser/native-worker
test saved/reloaded the playhead marker, checked confirmation reset and desktop/
390px layouts, rendered a checked preview at 68.149s for a 68.249s request, and
verified HTTP 206 media playback. No console errors or horizontal overflow.
Evidence: `D:/AI-DJ-data/validation/review-browser-931bdd4e184a44c5ba068436d6b43592/entry-marker-check/`.

Saving source times does not confirm listening. A marked transition with its
confirmation unchecked now shows `listening_confirmation_required` and rejects
preview/resume immediately without adding a job. Empty corrections still allow
automatic planning. The original failure remains in `original_review_items`;
displayed reasons follow completed previews/resumes for the current saved
revision, scoped to their transition. Earlier failures stay in history.

Verified against the owner's saved 184.218s outgoing / 101.821s incoming marks:
values and unchecked confirmation were preserved, the live API displays the
specific explanation, and preview returns 422 without creating a job. An
in-memory planning check with confirmation enabled found two candidates, not an
audio-validation or listening pass. Eleven transition-review tests passed.


### Adaptive manual handoffs (2026-11-12)

Use **Bring next song in here** and **Finish first song here** on the first
original. Use the second original to choose the exact passage to start from.
The finish is optional; clearing it lets the planner calculate an ending after
the protected vocal. A vocal-end mark is needed only when the estimated quieter
passage cannot establish a safe fade. Editing marks clears listening confirmation.

The live placement estimate is read-only (`POST .../transition-review/placement`,
with expected_revision, corrections and join_index). It shows the applied entry,
small beat/bar phase adjustment, full-level hold and exact finish before rendering.
It never saves a revision, queues audio or confirms listening. Conflicting bounds
appear immediately and block preview; the draft can still be saved.

Confirmed manual placements use vocal-preserving-planner-2 / manual-handoff-1.
They preserve the incoming source point and explicit outgoing finish, allow long
vocal holds, and fit fades around the available overlap instead of requiring a
fixed 8/16-bar template. Four bars of overlap and a two-second fade are still
required. The first song stays at full relative level through its vocal tail guard.
Automatic planning and existing version-1 plans retain their original policy.

Timing version 4 independently analyzes both original passages and prepared
sources. Human-corrected timing retains priority. Short overlaps use nearby
observed 4/4 context and whole-overlap bar phase, with early/late beat checks.
The 20ms detector resolution may be resolved by complete regular observed-clock
fits whose phase remains within 25ms at both window edges; raw checks remain
in the report. Encoded audio is additionally checked against the actual hashed
pre-encode waveform in consecutive windows (lag <=1ms, similarity >=.98).
This can resolve beat-detector disagreement caused by changing mix levels;
prepared-source beat/bar errors still prevent publication. No listening votes or
default approvals are inferred from these checks.
