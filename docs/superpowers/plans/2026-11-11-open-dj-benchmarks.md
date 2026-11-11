# External recognition and generation benchmarks

Owner approved UnmixDB recognition evaluation and an isolated DJtransGAN generator
comparison on 2026-11-11. This permits pretrained learned-fader/EQ inference in an
experimental benchmark, not automatic promotion or training a new waveform model.

1. Pin upstream source revisions and downloaded artifact hashes. Store data,
   source archives and optional runtimes under D:/AI-DJ-data/experiments. Preserve
   the working app, owner feedback, saved reviews and existing runtime packages.
2. Download one bounded UnmixDB archive (start with the smallest official set),
   verify the published checksum, extract safely and parse original labels/cues.
   Use its documented good-mix subset when available. Distinguish benchmark-only
   source identities and synthetic truth from owner annotations. Evaluate current
   recognition/coverage without tuning on the evaluation examples or inventing
   technique categories the dataset does not label.
3. Inspect pinned DJtransGAN inference/model/checkpoint code; use a compatible
   isolated CPU runtime. Require a real pretrained checkpoint, tensor-only loading
   and strict architecture compatibility. A missing checkpoint must fail, never
   produce random-network audio as a trained result. Record any compatibility
   adapter changes and implementation hashes.
4. Run the published example first, then a bounded local song pair. Compare with
   a deterministic baseline using explicit source/cue/tempo provenance, matched
   loudness and common listening windows where feasible. Check decoding, finite
   audio, silence and peaks. The published checkpoint is mono: keep all benchmark
   comparators mono and disclose this limitation; do not invent a stereo extension.
   Keep mismatched cue semantics explicit.
5. Save machine-readable reports and playable artifacts plus usage documentation.
   Report technical success separately from listening acceptance. Do not mark an
   external generator better or activate it without actual comparison evidence.
