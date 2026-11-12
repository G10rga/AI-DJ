# Stabilize timing validation across passages

The owner reports repeated independent timing failures after changing cues. Job
7e1179e9bbfe437ba4fb5c49c03ebc1b exposes the broader cause: an 8-second context
produces unstable extra/offbeat detections even when comparing an unchanged solo
source with its encoded output. Fixed 24-second context and deterministic input
level normalization make all 30 comparisons and both solo checks pass on the
same audio. Normalizing the short window alone still fails: adequate musical
context is required. Diagnostic policy was frozen before running these variants.

Evidence: D:/AI-DJ-data/validation/systemic-timing-02033e355fb947898206a041ae2b78ab.

1. Use a fixed 24-second context for independent source, encoded and local-
   original detections. Normalize detector input to mono RMS 0.1 with mono peak
   cap 0.98; never amplify silence or nonfinite data. This affects analysis only.
2. Record policy, input-window levels/gains and implementation hash. Retain all
   25ms/70ms, coverage, 4/4, solo, publication and context-recheck requirements.
   Do not search many windows and choose a passing outcome.
3. Return specific rhythm-evidence failures identifying the source/stage and
   recovery rather than treating every failure as a vocal-mark problem.
4. Freeze replay cases before the production edit: newest half-beat false
   detection, prior short-window/solo failure, cached-context failure, successful
   Let's Groove/Push The Feeling On preview, and successful At Night/Stupidisco.
   Re-render their exact immutable plans into isolated storage, preserving owner
   cues/results. All are regressions, not independent quality claims.
5. Test gain invariance, peak limiting, silence, invalid audio, policy hash
   binding and existing wrong-beat/bar/missing-marker rejection. Run workflow
   publication/review tests and real replay validation before deployment claims.
6. Reproduce the current saved review in the normal app and verify media/hash
   integrity, latest review reasons and unchanged source marks. Preserve genuine
   uncertainty as Needs review and leave listening/default approval to the owner.
