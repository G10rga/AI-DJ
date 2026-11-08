# Train and make test mixes in the browser

Open **http://127.0.0.1:8000/learning** or choose **Learning** in the navigation.
The reference review page also links to **Train and make test mixes**. Commands
and chat assistance are not needed for normal training, testing or retrying.

1. Save your reference reviews. Only completed reviews marked **Include for
   learning** are eligible. Excluded transitions and pending timing drafts stay
   out. You can begin an experimental run with two included transitions; you do
   not have to finish the whole reference recording first.
2. Press **Train from included reviews**. The job pins exactly the included
   review revisions and original file hashes available at that moment. Progress
   and its result appear below. Closing the browser does not stop the worker.
3. Select a **Model version**. The newly requested version becomes selected when
   training finishes. The page reports its example counts and available holdout
   results. Unknown style labels remain masked; cue/overlap learning still works.
4. Choose songs, add/remove them and arrange their order with **Up/Down**. The
   first two reference sources are preselected for a quick reproduction test.
   **Add songs from computer** imports original songs into the local D: library.
5. Press **Generate test mix** to use the selected model, or **Generate baseline**
   for the conservative comparison. Both are background jobs. Completed audio
   appears with native playback, **Download MP3** and **Open Mixes** links.

The local server runs one heavy job at a time. Other requests stay queued. Each
job has **Cancel** while queued/running, and **Retry** after failure, cancellation
or interruption. Its log is available for diagnosis. Jobs and results survive
page reloads. If the server stops during a job, recovery marks it interrupted
after its worker lease expires; retry uses the pinned inputs. Previous playable
mixes and completed models remain intact.

Changing included reviews makes prior models stale. Train a new version before
generating another model test from the changed collection. A running/queued job
retains its own immutable snapshot; later edits do not rewrite it. Repeated clicks
with the same active request reuse that job instead of starting duplicate work.

## What this model learns

This supervised model predicts the reviewed source cue positions and overlap
duration, with a separate style head for known recipe labels. It uses fixed
spectral source descriptors and a small CPU PyTorch network in the existing
isolated runtime. It is different from the earlier weak successor-context
experiment. It does not generate music, learn waveform/EQ curves or treat
excluded/unobserved choices as preference negatives.

Whole source identities are held out where enough disjoint examples exist. All
normalization fits training rows only. With too little disjoint data the report
explicitly has no evaluation. The report includes a training-mean baseline,
source cue error, overlap error, style-mask counts and exact source/review
provenance. A single recording still supplies no independent reference-set test.

Test planning treats predicted cues as preferences among nearby rhythm-supported
bar candidates, with a maximum 32-second search displacement. Requested and
applied cues are retained; movements appear in the result. Predicted overlap is
mapped to an eligible deterministic recipe. Cuts require phrase evidence; an
ineligible predicted cut is explicitly replaced by an eight-bar proposal before
the plan is frozen. Once selected, the model recipe cannot silently change after
waveform validation fails. Bounds, six-percent stretch limits, drift/phase,
separated-instrumental timing, finite stereo audio, peak/silence and publication
checks remain authoritative. A failure leaves a visible job error and retry.

Models remain **experimental** and are applied only to explicitly requested test
jobs. The default mixer/active-model configuration is not changed. Better mixing
quality requires listening and more representative reviewed examples; successful
training or rendering alone does not demonstrate improvement. Full test mixes
are not automatically synchronized or loudness-matched A/B preference trials.

## Saved data and operation

SQLite schema 7 adds `workflow_jobs`, a single-worker lease and `decision_models`.
Heavy jobs execute in subprocesses under one managed worker started with the
local app. Heartbeats, owner tokens and publication guards prevent cancelled or
stale jobs from publishing over a playable render. Test selection preserves the
ordered input entries, including repeats. No track is silently omitted.

Training stores `dataset.json`, `config.json`, `checkpoint.pt`, `report.json` and
`manifest.json` under `D:/AI-DJ-data/models/decision-model-JOB_ID`. Files are
hashed, checkpoints load tensor-only with strict state dictionaries, and complete
models become visible atomically through the job/model registry. Source files
are read in place and rechecked against pinned hashes. Job logs and intermediate
work stay in `D:/AI-DJ-data/tmp/workflow-JOB_ID`; rendered audio stays in `renders`.

Uploads accept supported original-song formats, validate size/audio/duration,
store opaque filenames under uploads, retain the original display name and
register only successful files. An invalid upload removes its partial file.
Browser requests select registered IDs and cannot choose arbitrary server paths.

The UI uses `/api/v1/learning/state`, `POST /train`, `POST /test-mixes`,
`POST /library`, and `POST /jobs/{id}/cancel|retry` under `/api/v1/learning`.
The app remains local and loopback-only. No additional packages, external
services, uploads outside the local app, deployment or billing were introduced.
