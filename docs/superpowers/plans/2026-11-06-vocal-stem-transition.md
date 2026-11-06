# Mid-song vocal stem transition experiment

Owner explicitly requested on 2026-11-06: mix mid-song, suppress the incoming
song's vocals at first, fade the outgoing vocal, and introduce the incoming vocal
afterward. This authorizes an internal vocal/instrumental separation experiment
beyond the earlier EQ-only prototype. No public stem export, new track-ordering
ML, training, or generative blend model is included.

1. Keep the existing renderer and source files intact. Put optional separation
   runtime, downloaded pretrained model, cache and stems under `D:\AI-DJ-data`.
2. Use an established pretrained UVR MDX ONNX model locally. Record model identity,
   hash and transform settings; do not upload user audio. Bound inference to one
   stereo chunk at a time and use cached local results.
3. Reuse accepted mid-song cues/tempo alignment. Separate the prepared stereo
   excerpts so vocal and instrumental stems share the exact same timing. Derive
   the complementary stem by subtraction, ensuring stems reconstruct the mix.
4. Blend instrumentals with the existing bass handoff. Keep the outgoing vocal
   initially, fade it over a musical interval, then fade the incoming vocal in
   with a short gap rather than overlapping two full vocals. Maintain a steady
   instrumental bed throughout. Detect strong vocal gaps near intended changes
   if the separated signal supports them; do not assert semantic lyric boundaries.
5. Validate STFT round-trip, exact stem reconstruction, explicit vocal gain
   schedules, pulse alignment, stereo, clipping, duration and sustained tail.
   Render an MP3 plus reproducible JSON report. Owner listening is the musical
   acceptance criterion; separation leakage/artifacts remain possible.

No commits unless requested. This experiment does not establish automatic
downbeat, harmonic compatibility or vocal-phrase planning.
