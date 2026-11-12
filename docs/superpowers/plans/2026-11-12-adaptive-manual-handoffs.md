# Make manual transition placement usable

Owner explicitly requests usable second-song entry / first-song ending controls.
Latest failure: Armand → Gaskin, requested entry 107.877s, incoming source 115.401s,
vocal completion 120.88s. Local 2/4-bar timing exists, but an entire rigid 8/16-bar
fit does not exist at both points. Moving to a theoretical limit still rejects.

## Behavior

- Add an optional real first-song finish marker (`outgoing_source_out`), distinct
  from vocal completion. Keep the incoming song's source point exactly as marked.
- Align its beat phase using observed local 2/4-bar anchors and a small visible
  adjustment to the outgoing entrance, rather than requiring marks on a fitted
  eight-bar span. Keep ordered, continuous source playback and requested/applied
  provenance. Never jump to a distant musical passage.
- Adapt the protected hold to the vocal completion plus the existing two-second
  guard, then use a gradual fade. Honor explicit first-song endings; if absent,
  calculate an ending after the protected vocal. Require a practical four-bar
  overlap and at least two seconds of outgoing fade. Contradictory physical
  bounds get immediate, specific feedback, not a template-matching rejection.
- Vocal completion can be omitted when estimated quieter evidence supports the
  fade. Otherwise ask for that one mark without discarding placement choices.
- Provide a read-only placement estimate for draft controls before queuing audio;
  estimates never fabricate listening confirmation or become renderable plans.
- Keep incoming gain low during the hold; offer two protected bed levels when
  both are valid. A plain crossfade is eligible only after vocal completion.

## Versioning and verification

1. Preserve version-1 planner eligibility/plan validation for existing artifacts.
   New confirmed manual plans use planner version 2 and manual-handoff-1 candidates.
2. Independently analyze actual original passages for manual plans; cached model
   grids are priors, not ground truth. Explicit human timing corrections still
   take precedence. Retain cached diagnostics and hash-pinned fresh originals.
3. For shorter manual overlaps, require whole-overlap bar phase, early/late beat
   alignment and nearby independently observed 4/4 support. A half-window with
   too few downbeats can use the verified whole-overlap phase; preserve that
   fact explicitly. Wrong phase, drift, missing evidence and encoded mismatch
   remain blocked. Legacy plans retain their original timing policy.
4. Test exact ends, preserved incoming source starts, long vocal holds, invalid
   bounds, short-overlap phase rejection, old plan validation and review/media
   fences. Replay real legacy plans, current owner placements, and deliberate
   timing faults. Inspect desktop/mobile controls and read-only estimates.
5. Render a new preview from the owner's unchanged latest marks and verify app
   playback. Do not save votes, train, promote defaults or claim M4 acceptance.

Implementation refinement: estimate manual tempos from the marked local observed
clock when every local beat (or downbeat) supports a regular fit; fall back to
supported source spans. Validate 20ms-quantized observed beat clocks with unchanged
25ms fitted phase at both window edges, retaining raw failures. Verify encoding
against hash-pinned pre-encode PCM in consecutive stereo windows, retaining all
encoded beat diagnostics. This separates actual timing drift from detection bias
in the changing mixture; genuine phase/bar faults and encoder shifts still fail.

Completed: 52 targeted tests, three real adaptive renders, five exact legacy
replays, four native timing-fault rejections, isolated desktop/mobile controls
and live owner preview/media verified. Evidence and IDs in HANDOFF.md.
