# One Pedalboard loop/filter/delay preview

Owner explicitly approved the proposed loop → filter → beat-synced delay →
bar-boundary incoming release. Build one isolated At Night / Stupidisco example,
keeping the corrected crossfade as the comparison. No default activation.

1. Pin Pedalboard 0.9.26 and its Python 3.12 Windows wheel SHA256 in a new venv;
   reuse existing CPU packages read-only. Preserve all other runtimes and votes.
2. Verify and reuse the exact corrected float32 stereo sources and timing.
   Keep the 60s listening window, tempo and bar grid. Select a supported one-bar
   outgoing segment, with instrumental screening if the available separator can
   provide evidence. Never claim a model establishes absence of vocals.
3. Start looping at the existing overlap entry (~22.38s), repeat for four bars,
   sweep the loop's filter and introduce quarter-note delay. Release incoming
   playback at the 30s bar boundary, with a short click-safe gain ramp and an
   explicitly bounded outgoing echo tail. Preserve plugin state across blocks.
4. Verify sample-exact repeat placement, click-safe seams, flushed effect tail,
   float headroom, loop and incoming beat/bar correspondence, and final encoded
   beat continuity. Block publication on mismatched or uncertain evidence.
5. Match loudness with a new copy of the corrected baseline. Publish only after
   audio checks, with hashes, plugin settings, control timeline and pending owner
   acceptance. Serve through existing 8007; do not open another server or UI.
