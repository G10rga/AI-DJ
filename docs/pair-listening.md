# Compare transitions by listening

Open `/compare` or choose **Compare** in the navigation. The updated session is
running at **http://127.0.0.1:8005/compare**.

1. Choose outgoing and incoming songs from the existing library. Add songs through
   Learning if needed. After a reload the newest completed pair is preselected.
2. Press **Generate A/B previews**. The persistent background job uses musical
   timelines, proposes up to twelve cue/recipe candidates, validates their actual
   audio and renders two distinct alternatives. Missing timelines are analyzed
   locally; this can take several minutes. Cancel and Retry appear with the job.
3. Play A and B. Each has the same duration and handoff position, with matched
   loudness and true-peak checks. **Play from handoff** starts eight seconds before
   the central handoff. **Switch A/B at same position** carries the playhead to the
   other version. Playback is exclusive; polling preserves audio nodes.
4. Select **A is better**, **B is better**, **Tie** or **Neither works**. An optional
   reason can describe what you hear; DJ terminology is unnecessary. Choices save
   immediately, remain after reload and can be revised. A stale window receives a
   conflict; Refresh before saving again.

A/B preferences refit the experimental preference ranker from actual listening
choices. Tie and Neither retain explicit history and remove a prior winner for
that candidate pair; neither creates a fabricated ranking or star rating. Neither
also makes the next job for the same ordered songs skip those explicitly rejected
candidate IDs. Other unplayed alternatives are not treated as negatives.

The model now includes measured candidate context: energy change, harmonic and
embedding distance, vocal collision and outgoing energy trends. Unknown context
has separate missing-value masks. Legacy saved feature vectors remain supported.
It still reports leave-one-song-pair-out evaluation rather than training accuracy
as proof of generalization.

The first distinct preference can change experimental weights. **Use learned
ranking for this comparison** becomes available after at least six distinct
comparisons spanning three song pairs. This is a minimum-data guard, not musical
validation. Selection is explicit and pins the model snapshot in that job. The
existing deterministic contextual scorer remains available without the checkbox.
This preference model is separate from reference cue/style training; leaving
reference technique labels unknown does not prevent A/B preference learning.

Technical failures remain visible. A job publishes only when both matched
previews succeed. Cancelled work cannot publish a comparison. Feedback and media
requests require a successful registered comparison and unchanged audio bytes.
No generated preview is automatically marked musically accepted.

Schema 9 adds the `pair_audition` job kind while preserving existing jobs and
model references. Listening votes and per-comparison revisions live in the
existing `feedback/preferences.sqlite3`. Existing timelines are pinned when the
job is queued; newly required analyses record their resolved identities in the
result. Recipe descriptors used for candidate ranking share the renderer's
schedule code; real rendered feature vectors were verified to match exactly.
