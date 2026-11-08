# Review the actual transitions in a reference mix

Open **http://127.0.0.1:8000/references**. HouseMixN3 has 40 adjacent handoffs.
Its 38 prepared search ranges and source cue estimates are starting points;
the two handoffs around Can't Get Enough need manual timing. Nothing has been
marked as listened to or approved automatically.

1. Choose a transition and press **Listen to handoff**. The recording starts
   eight seconds before the suggested range and stops eight seconds after it.
   For an unresolved transition it opens a wider listening window. The native
   player can seek anywhere in the recording.
2. At the incoming song's first audible entry, use **Set entry here**. At the
   outgoing song's final exit, use **Set exit here**. You can also type `m:ss`,
   `m:ss.sss`, seconds or `h:mm:ss`. A cut can have equal entry/exit times.
3. Press **Update source estimates** after changing the recording interval.
   Check both original song players and their source-at-entry/source-at-exit
   positions. Their cursors open at the draft source entry; their marking
   buttons copy the current original-song playback time. Select the correct
   original if alternatives exist. Unknown mappings require manual cues.
4. Choose **Include for learning** for a transition worth imitating, or
   **Exclude from learning**. Style, overlap bars, vocal behavior and energy
   behavior are optional; leave them unknown when you cannot establish them.
5. To keep timing edits immediately, press **Save timing**. You can save just
   entry, just exit, or both, even with source cues and learning choice unfinished.
   These saved drafts stay pending and are excluded from training. To finish,
   check **I reviewed this handoff by listening**, then **Save review**.
   Each handoff saves independently. Completed included examples require both registered
   originals and all six valid timing values. Exclusions can retain unknowns.

The first few reviewed examples are useful; all 40 are not a prerequisite to
starting supervised experimentation. Saving collects actual decisions; it does
not immediately train or activate a new model. Open **Learning** and press
**Train from included reviews**, then **Generate test mix**. See
[UI learning and testing](ui-learning.md). Unknown style labels are masked.
The previous successor-context experiment remains inactive.

**Download reviewed examples** appears after an included review is saved. It
exports only the latest explicitly included reviews, their revisions, original
hashes, cue intervals and optional observations. Excluding a previously included
transition removes it from the current export while preserving review history.
These observations are not automatic A/B preference negatives.

Editing an approved review clears the listening confirmation. Saving that edit
as timing-only returns the latest version to pending and removes it from the
current training export until you confirm it again; history remains intact.
The queue distinguishes saved timing drafts from completed reviews. Controls
lock while saved reviews are loading, preventing a late reload from overwriting
new edits or a save response.

Unsaved edits prompt before switching transitions or reloading. A failed save
keeps the form. When another window has saved the same transition, use **Reload
saved reviews** to load that revision before saving again. Playback is exclusive:
starting an original pauses the recording and the other original. No autoplay.
The phone folds the queue under **Choose transition**.

## Preparing another recording

After importing/alignment through `scripts.import_reference`:

```powershell
scripts/local.ps1 -m scripts.extract_reference_transitions REFERENCE_ID --output D:/AI-DJ-data/references/transition-drafts.json
scripts/local.ps1 -m scripts.serve
```

Extraction runs through shared services outside web requests. Four-second
source agreement windows suggest support bounds; adjacent support brackets and
registered source boundaries constrain the initial listening range. When only
coarse anchor windows are usable, the draft says so. These bounds cannot prove
the exact start of a faint fade or identify mixer controls. Raw similarity is
uncalibrated and remains separately visible under **Source match evidence**.

SQLite schema 6 stores immutable draft batches pinned to imports/alignments and
append-only per-join review revisions. New extraction never rewrites a saved
batch. The browser opens the newest batch; older batches/reviews remain available
by their saved draft IDs. Human exports always identify that precise batch.
Media requests use registered IDs/hashes and reject changed source bytes.

The local API exposes `/api/v1/references`,
`/api/v1/reference-drafts/{draft_id}`,
`POST /api/v1/reference-drafts/{draft_id}/transitions/{position}/reviews`, and
`/api/v1/reference-drafts/{draft_id}/training-examples`. Saves require
`expected_revision` and an explicitly `reviewed` include/exclude decision.
