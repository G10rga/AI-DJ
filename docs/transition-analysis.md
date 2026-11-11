# Understand a reference transition

Open `/references`. Correct the recording entry/exit, check both original-song
cue intervals, and save. You can leave **Transition style** unknown.

- **Analyze transition** uses that transition's saved timing and selected originals.
  A saved timing draft with all six cues can be analyzed, but remains ineligible
  for training until you finish and include the listening review.
- **Analyze reviewed transitions** processes completed, included reviews together.
- The description explains measurable source behavior, evidence strength and
  whether a supported renderer style can be assigned. Expand **Analysis evidence
  and limits** to see fit error and provenance. Confidence is heuristic.
- Jobs show progress, Cancel and Retry. Closing the browser does not stop them.
  The Learning page also lists analysis jobs.

Analysis never changes your saved style, timing, include/exclude decision or
listening confirmation. Changing a saved review makes its estimate stale.
Unsaved edits disable analysis until saved or discarded. Human exports under
**Download reviewed examples** remain human-only.

## Training

Press **Train from included reviews** after analysis. Training uses current,
completed included reviews. A supported high-evidence automatic recipe fills an
unknown style in the training snapshot only, with weight **0.35** versus **1.0**
for human labels. Your known style always takes precedence, including Other.
Unsupported, uncertain, stale, pending and excluded estimates supply no style
target. Cue/overlap supervision continues to use your saved source timings.

The training/model pages count automatic labels separately. Model artifacts pin
the estimate's job, algorithm version, source/recording hashes and exact review
revision. Adding eligible estimates changes the training fingerprint; retrain
before generating a model test from that changed collection. Held-out human
style accuracy and agreement with automatic labels are separate report metrics.
No model is trained or promoted merely by pressing Analyze.

## Method and limits

The local analyzer reuses the reference matcher's 32 log-power frequency bands
at four frames per second (60–3600 Hz), converting them to linear magnitudes
before fitting. It maps source intervals to the marked recording interval,
observes up to two seconds before entry and after exit where the original audio
is available, pools neighboring frames, refines offsets within one second,
and solves nonnegative two-source magnitude attribution in three frequency groups.
Reconstruction residual, spectral separability and source support gate the result.
These are approximate gain measurements, not recovered fader/EQ knob positions.

Version `transition-magnitude-context-3` replaces the earlier power-additive
baseline. Power additivity is a poor approximation for phase-locked overlapping
bass. Boundary observations use a fixed short window, so a hard exit is not
hidden by averaging several seconds of the outgoing song. The description keeps
your actual marked overlap duration and never rewrites source cues.

The result separates measurable band changes, an estimated technique and a
training-eligible renderer recipe. Moderate evidence can support a written
technique estimate without being strong enough to label training. Completed jobs
show analyzed / described / training-label / uncertain counts. A completed job
with zero recognized techniques no longer looks like successful recognition.

Different handoff times across bands suggest an EQ handoff. Simultaneous fading
across bands suggests a gradual blend. A marked interval of at most half a second
is tested against 2.5 seconds of surrounding audio on each side; a cut requires
an observed abrupt switch, not just equal entry/exit fields.

Only high-evidence results map to renderer labels: EQ handoff near 8 bars,
gradual blend near 16 or 32 bars, or a verified cut. Bars come from your optional
observation or reliable original-song pulse evidence adjusted to the recording's
playback rate. No recipe is assigned from overlap seconds alone. Pulse-derived
bars assume four beats per bar and do not prove musical downbeats.

If the original-song cue intervals imply a speed change beyond 10%, check those
cues first. Otherwise a poor fit may mean inaccurate mapping, another song edit,
pitch changes, extra audible tracks, compression or effects this method does not
model. The analyzer explicitly leaves these unknown; it cannot identify vocals,
echoes or exact filters. There is no externally trained audio-language model.

The method is inspired by subband analysis of DJ mixes, but this implementation
is a simpler, uncalibrated baseline rather than a reproduction of the published
optimization model: [Kim, Yang and Nam, NIME 2021](https://nime.org/proc/nime2021_87/index.html).

SQLite schema 8 expands the existing job kinds while preserving jobs and models.
Completed job results hold immutable analysis records. Cancelled or failed work
does not publish labels. Existing worker leasing, recovery and retry apply.
