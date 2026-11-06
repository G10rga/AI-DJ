# Unsupervised library planning implementation

Owner approved the long Move → Say What transition and requested ML on 2026-11-06.
Implement milestone 3: learned track similarity/order and transition-style
suggestions, with deterministic DSP feasibility checks. No learned blend curves,
supervised quality claims, full-set rendering or UI in this change.

1. Extend cached DSP analysis with MFCC/timbre statistics. Independently scan local
   kick regions to obtain usable tempo/cue support; retain ambiguity and missing
   estimates rather than trust the existing whole-track confidence score.
2. Fit robust feature scaling, PCA and KMeans on distinct local audio content.
   Use the learned distance plus explicit tempo/energy constraints to order every
   supplied upload exactly once. Keep a deterministic DSP-only baseline.
3. Fit a small unsupervised Gaussian mixture to pair descriptors and map pair
   groups to long/short recipe suggestions. Document that these groups do not
   represent learned human quality scores. Missing/insufficient data uses an
   explicit baseline, not invented ML confidence.
4. Build source-bounded excerpts and feasible common-tempo runs. Prefer the
   approved 32-bar groove where compatible, with eight-bar or warned boundary
   handoffs when confidence, source bounds or overlap geometry require them.
   Preserve every valid entry, including duplicates and musical outliers. Reject
   invalid input batches without silently creating a reduced mix.
5. Save readable model metadata and plan artifacts on D:, and round-trip the core
   MixPlan through SQLite. Explain learned similarities, pair groups, cue support
   and every downgrade. Include optional deterministic baseline comparison.
6. Provide a CLI for the folder, run it on the user's local library, and connect a
   planned pair to the existing validated stem renderer for an audition. Actual
   waveforms must still pass tempo/phase/headroom/tail checks before audio is
   published. Do not describe approximate cue support as verified phrase/vocal
   boundaries, or a preview as a rendered full set.

Tests: deterministic ordering and model state, duplicate preservation, one track,
missing BPM/key/timbre, outliers, degenerate collections, finite features, source
bounds, non-consuming overlaps, no forced stretching, persistence and failed
input handling. Run the current audio regressions and an actual local plan/preview.
No commits or pushes without request.
