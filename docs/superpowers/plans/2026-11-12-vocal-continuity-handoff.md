# Preserve vocal continuity before adding effects

Owner approved replacing the rejected loop/hard-release approach with a
phrase-aware gradual handoff. Work on At Night / Stupidisco only.

1. Screen bounded original-song context with the existing MDX separator. Preserve
   original hashes and real source-time offsets; use vocal estimates as activity
   evidence, never semantic phrase truth. Analyze the outgoing ending and incoming
   intro, not just the chosen loop destination.
2. Find a continuous lower-vocal incoming intro and an outgoing vocal completion
   region. Preserve outgoing playback without jumps. Keep its audible vocal
   phrase at full source gain until it finishes; give a real tail/gap before
   fading. If no supported phrase plan exists, do not invent one.
3. Align supported complete bars at the common tempo and use a gradual incoming
   gain ramp lasting multiple bars. Check the whole outgoing fade for renewed
   vocal activity and avoid cutting another phrase. Use float stereo processing.
4. Verify exact prepared beat/bar alignment, gain continuity and source-time
   continuity, plus final decoding, duration, peaks and encoded timing. Publish
   one new preview on existing 8007 only if checks pass; no loop or echo.
5. Record exact planning evidence and uncertainty. Keep rejected audio/feedback
   immutable and leave app defaults and owner votes unchanged.
