# Experimental learning from HouseMixN3

Owner explicitly requested training on the imported recording on 2026-11-08.
There are 40 provisional source matches and no reviewed transition-style labels.
Proceed with positive-only weak supervision, preserving those facts.

1. Pin the immutable import and alignment. Validate all consumed source hashes.
   Build examples only for actual adjacent ordered entries with available
   multi-window matches. Do not bridge unresolved entries or create preference
   negatives. Preserve occurrence positions, hashes, windows and exclusions.
2. Summarize matched source and recording windows with fixed 32-band spectral
   mean/std descriptors. Train a small CPU PyTorch network to predict the next
   source's musical descriptor from the current source/recording context. This
   is an observed-successor context model, not a preference ranker, cue detector,
   transition-style classifier, generated audio or learned EQ/waveform curves.
3. Reserve a contiguous source-identity group before fitting any scaler. Exclude
   cross-group edges and repeated-source leakage. Split every augmented window
   of a pair together; reject overlapping train/evaluation recording windows.
   Document that one recording cannot supply an independent reference-set test
   and that automatic matches can contain errors or other audible sources.
4. Optimize regression on positive observations, evaluate against training-target
   mean and persistence baselines, and publish actual metrics even if worse.
   Freeze a deterministic epoch count; evaluation does not pick hyperparameters.
   Save dataset, exact config, checkpoint, dependency/source-code hashes and
   report atomically under D:/AI-DJ-data/models, with status experimental.
5. Supply explicit prediction/scoring commands, strictly load local tensor-only
   checkpoints and validate artifact hashes. Existing planning and active models
   remain as configured. No listening labels or promotions are implied.
6. Test source-group isolation, train-only scaling, missing/weak observations,
   artifact tampering, reproducibility, finite predictions and real training.

Reviewed style annotations and explicit A/B preference learning remain later
parts of the saved workflow. This run is a useful first trained context model,
not completion of that broader milestone.
