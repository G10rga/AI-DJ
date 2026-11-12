# Recheck context-sensitive original beat detections

Job 3149351b716b4528a70aed8ba8a68a33 passes all actual prepared-pair and encoded
comparisons, but the late cached-original mapping covers 85.7% within 25ms:
two beats differ by 29.5/29.8ms. A fresh same-passage original detection maps to
the actual preparation within the existing limits; both raw and gain-matched
variants pass. All cached-to-local markers match within the original limits.
Evidence: D:/AI-DJ-data/validation/timing-diagnosis-728ed7768f7f4915b0ea2855a1e7873f.

1. Keep every initial check and all 25ms/70ms thresholds. Only mismatched cached
   original mappings are eligible for a same-context original recheck. Prepared,
   encoded, solo, bar-support, unknown/missing evidence failures remain blocked.
2. Decode the hash-verified original passage corresponding to the exact prepared
   detection window. Run the pinned tracker on raw and actual preparation-gain
   variants. Pin paths/hashes, windows, gain, model and worker in the report.
3. Require raw and gained local-original-to-prepared checks across whole/early/
   late windows, regular 4/4 bars, and 100% cached-to-local marker coverage at the
   existing tolerance. Retain original mismatches with explicit resolution links;
   never rewrite a failed measurement as aligned.
4. Test detector-context jitter resolution and rejection of real shifts, dropped
   markers, wrong phase, missing variants, non-original failures and bad solos.
5. Render the exact failed job's plan/corrections afresh. Verify artifacts and
   app playback, preserving all prior failures, source marks and owner feedback.
   New evidence driven by this case is a regression, not independent acceptance.
