# Explain conflicting entry markers and snap incoming source starts

The owner's requested outgoing placement is 111.165s and vocal completion is
140.813s. Even the 16-bar protected blend would fade too early for the two-second
guard. Its incoming source-start mark, 20.289s, is also 0.549s from a downbeat.
The UI promises supported-bar snapping but the old incoming rule only accepted
marks already within 250ms of a fitted cue.

Snap incoming source marks to the nearest actual downbeat within half a source
bar, then keep the existing 250ms fitted-span and all independent timing gates.
Preserve the requested value in correction provenance and applied value in cues.
Explain an impossible outgoing placement with exact vocal/entry times and the
earliest possible entry for the allowed 8/16-bar recipes. Never change the saved
marks, extend the blend silently or fabricate listening confirmation. Reproduce
the same preview request after testing so its current review shows the specific
reason rather than the old generic result.
