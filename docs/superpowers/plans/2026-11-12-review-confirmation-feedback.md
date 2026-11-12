# Explain unconfirmed source marks

The owner saved outgoing/incoming times but previewed with listening confirmation
false. The planner correctly retained automatic vocal constraints, but the UI
repeated the original generic failure and accepted an unhelpful preview request.

1. Derive an explicit unconfirmed-marks review item from the saved snapshot.
   Preserve the original job failure separately; never change confirmation.
2. Reject preview/resume with marked but unconfirmed selected joins immediately,
   before writing a job. Permit the existing fully automatic path without marks.
3. Display the latest matching-revision child failure when available, while
   retaining original failure provenance and earlier child history.
4. Test saved values, no extra queued job, confirmation resolution and unchanged
   empty/automatic reviews. Verify the real review API after a safe app restart.
