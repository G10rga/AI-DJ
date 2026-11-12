# Place the incoming song on the outgoing timeline

Add optional `incoming_at_outgoing`, expressed in the outgoing original's source
seconds. It is separate from outgoing vocal completion and the incoming song's
own source-start mark. Provide a playhead-mark button on the outgoing player,
a labelled dashed timeline marker, and an editable numeric field. Reuse the
current dark surfaces, controls, focus states and responsive form layout.

Persist and validate the optional value against the outgoing source. Constrain
the planned overlap start to the nearest outgoing downbeat (within half a bar),
then require a supported fitted span within the existing 250ms cue tolerance.
Never change the vocal end, incoming source point, tail guard or timing gates to
make a requested placement fit. Retain requested and applied cue provenance.

Keep existing reviews/plans compatible when this optional field is absent.
Invalidate listening confirmation when a source marker changes. Test save/resume
pinning, marker placement, conflicting tail protection and older review behavior;
verify the UI at desktop and phone widths using isolated browser interactions.
