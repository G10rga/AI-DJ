# Broader transition listening test

Owner approved testing the plain crossfade on more song pairs, keeping
DJtransGAN and the existing renderer as comparators. No default promotion.

1. Reuse three already published two-song test mixes with six distinct songs,
   excluding I Move / F Say What. Freeze actual applied cues, tempo, overlap,
   track start positions and published audio; do not rerun cue prediction.
2. Extend the research-only runner to read successful test jobs without writing
   app data. Reject unsupported PCM delays or insufficient listening context.
3. Render the same 60-second mono window for all three versions. Use the same
   prepared source inputs for GAN and linear; crop the existing published mix.
   Match integrated loudness with constant gain and check finite decoding,
   duration, peaks and dropouts. Disclose separation/level-processing differences.
4. Publish an immutable session manifest and Markdown listening sheet through
   the existing audition file server. Keep version numbering consistent with
   the prior listening test: 1 existing, 2 pretrained AI, 3 linear crossfade.
5. Verify audio links/hashes and retain pending listening status. Do not invent
   feedback, force a GAN-vs-linear tie, or train on technical checks.

Development-server cleanup: retain app 8005 and audition files 8007. Verified and
stopped the four obsolete AI-DJ serve processes on 8000/8002/8003/8004. Do not
open another port for this listening batch.
