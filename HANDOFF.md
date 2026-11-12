# Handoff — AI DJ Set Maker

## Main-app improvement milestone 3 completed — 2026-11-12

See [plan.md](plan.md) and [docs/transition-review.md](docs/transition-review.md).
The main app at **http://127.0.0.1:8005** now exposes **Improved transitions —
experimental** in Learning and Compare. Uncertain jobs enter durable Needs review
without publishing audio. The review page has both original players/waveforms,
line-end/incoming-entry marks, explicit listening confirmation, saved revisions,
checked preview, linked resume, playback/download and history. Human vocal edits
do not bypass independent timing gates. The exact timeline editor is linked;
new previews/resumes pin the latest saved timing revision of that analysis ID.

SQLite schema 10 preserves old jobs/models/reviews while adding immutable review
context, correction revisions, join-preview jobs, version-2 plan/media snapshots,
listening-only comparison feedback and explicit default choice. Stale review or
timing revisions, lost leases and cancellation fence media publication. Old
playable previews stay pinned and readable. New comparison votes do not train
legacy preference features. Make default requires explicit owner approval on a
completed generation; the actual owner default remains **legacy-v1**.

Full regression: 201 tests (195 passed, six isolated-runtime skips). Final nine
review tests and five stale-preview/playback checks passed. The isolated real
browser/native-worker flow passed marking/save/preview/play/conflict/reload/
resume/download/Mixes/cancel/history plus comparison feedback; no owner test
labels/votes were saved. Rendered desktop/tablet/mobile checks passed with zero
failures. QA server stopped; only the normal app is needed. No commits, effects
or listening acceptance/default promotion. Resume at milestone 4.

## Main-app improvement milestone 2 completed — 2026-11-12

Read [plan.md](plan.md) and [docs/vocal-planner.md](docs/vocal-planner.md).
The shared experimental backend now implements plain/protected vocal recipes,
at most twelve evidence-constrained candidates, continuous ordered set geometry,
sample-based master envelopes, stereo float rendering and independent original/
prepared/encoded whole/local timing gates. Both Generate/Compare job entry points
dispatch explicitly pinned `improved-transitions-1` payloads to that service.
Legacy/default jobs remain unchanged. Unsafe/missing evidence returns structured
review items without audio; selected failures never change cues or recipe.

Real At Night/Stupidisco Generate and same-cue plain/protected Compare artifacts
passed all 30 timing checks each, at -20.00/-19.99 LUFS. These use independently
selected later source regions, not the earlier owner-reviewed experiment cues;
new listening acceptance remains null. Edge of Desire / It's Not Right But It's
Okay correctly requested review with no safe candidate and no audio. Reviewed
artifacts, old evidence/defaults/models and rejected effects remain preserved.
Full suite: 193 tests (187 passed, six isolated-runtime skips), plus final 15
planner/timing checks after the local-window edge fix. No votes or commits.

Resume at milestone 3: visible experimental option, durable review state,
correction/preview/resume/media integration, pinned plan persistence and job
publication guards. Backend `needs_review` results are not yet durable workflow
review states. Preference feature extensions and effects remain milestone 5.

## Main-app improvement milestone 1 completed — 2026-11-12

Read [plan.md](plan.md) for the current cross-session implementation checklist.
Owner chose main-app quality first, correction by listening for uncertain joins,
staged effects and default promotion only after listening validation/approval.
Milestone 1 is implemented: shared float preparation/fixed gain staging,
source-wide multi-beat bar fits, application-owned registered-pair analysis,
versioned isolated Beat This/MERT/MDX workers, verified MDX caches, relative vocal
levels with actual coverage and separate quieter/structure/phrase candidates.
Existing timelines/corrections remain immutable; experimental analysis requires
explicit profile selection and does not replace the default editor/planner view.
Real full-song analysis on Edge of Desire / It's Not Right But It's Okay passed,
including identical cache reuse and preservation of 3 earlier predictions.
The refactored handoff runner passed fresh model-backed timing and encoded-audio
checks (-20 LUFS, -4.46 dBTP); reviewed reference/rejected artifacts remain intact.
See [docs/transition-foundation.md](docs/transition-foundation.md) for interfaces,
verification reports and limits. Resume at milestone 2 in plan.md. Main-app
Generate/Compare integration, listening acceptance and default promotion remain
later work. No new owner votes, effects, training labels or commits.

## Owner reports continuous handoff is better — 2026-11-12

Owner listened to vocal-handoff-fdc44c762ab34ca8990521d1b53addc0 and said
"its better". An immutable research listening review pins the exact audio/report
hashes and records qualitative improvement. No score, explicit pairwise vote or
full acceptance inferred; no app activation/training changes. Use this
continuous vocal-protecting, gradual-intro version as the research reference for
further work. Keep the rejected loop/filter/delay recipe disabled.

## Continuous vocal handoff preview ready — 2026-11-12

Owner approved letting the outgoing vocal finish and gradually introducing the
incoming song before adding effects. Plan:
`docs/superpowers/plans/2026-11-12-vocal-continuity-handoff.md`; usage:
`docs/vocal-handoff.md`. Still At Night → Stupidisco, one isolated example.

**http://127.0.0.1:8007/vocal-handoff-fdc44c762ab34ca8990521d1b53addc0/handoff.mp3**
is the final 60s stereo preview, pending listening. Incoming starts quietly near
22.38s and reaches only 25% gain at 30s. Outgoing stays at full fixed preparation
gain until 30s; its last strong estimated vocal activity ends near 26.73s, giving
a 3.25s source-time tail guard. Outgoing fades 30–37.62s while incoming rises
25%→100%. Both sources remain continuous, with no loops, source jumps or effects.

Moved outgoing fade to original 143.74788–151.30927s, a sustained quieter gap
before the next vocal activity. Incoming overlap uses its opening 3.92–19.28s,
instead of its vocal-heavy middle. MDX screen outgoing original 54s–end and
incoming 0–120s, each within the separator's 180s bound. Vocal traces are derived
from actual stems with checked source/model/context hashes and explicit offsets.
No semantic phrase recognition or human cue labels claimed. Max predicted vocal
ratios: .05562 throughout outgoing fade + guard, .09698 throughout incoming
overlap (p95 .03577). Earlier rejected cut region 112.09–119.7s fails this gate.

New research helper vocal_handoff.py validates continuous coverage and quiet
intervals, and generates protected-outgoing/gradual-incoming envelopes. Renderer
render_vocal_handoff.py checks the exact stretched sources and encoded mix.
Early intro fitting is an explicit stable_spans option; existing callers retain
35s leading-context behavior. Incoming's pre-file silence is padded explicitly
while inaudible; all actual source samples thereafter play continuously. Float
stereo preparation preserves peaks until gain staging.

Verification: preparation 27/27 beats and 7/7 downbeats matched, six complete
regular bars each; final outgoing/transition/incoming beat match fractions 1.0
and final downbeat fraction 1.0. Protected line gain=1, smooth multi-bar incoming
ramp, -20 LUFS, -4.46 dBTP, finite/format/dropout and HTTP SHA256 checks passed.
45 focused tests OK, two native effects skips; native DSP tests were previously
passed in their own unchanged runtime. Old reviewed/rejected files intact.
No votes, app defaults or models changed. Earlier unshared f50e1f... pilot marked
superseded. The rejected loop/filter/delay v1 remains disabled.

## Loop effects rejected and v1 disabled — 2026-11-12

Owner rejected loop-filter-delay-cdac3973477e4616b7866412cfc5cb6a: outgoing
song cut during vocals, fade/loop ending bad, incoming cut abruptly. Immutable
review `32e408fac724494bb7c7cc9f40f954b0` pins exact effect audio/report hashes
under that folder's listening-reviews/. This does not reject the baseline or
invent a pairwise vote. REJECTED.json and README show the effects verdict.

Audit: at 22.3811s the effect replaces outgoing playback with a bar from 30.0s,
skipping 7.6189s while vocals are active. MDX predicted vocal RMS is .0278–.0396
in the surrounding half-second windows. Picking a quieter destination bar did
not establish that the current vocal phrase had ended. Incoming ramp .005s is
a click-prevention ramp, not a gradual musical entrance. Beat/bar agreement did
not validate either of these musical decisions. These are recipe/planning errors.

`alignment/loop-filter-delay-1/rejection-audit.json` records evidence. Local
recipe-status.json marks v1 owner_rejected; scripts.render_loop_transition now
fails before preparing or publishing anything if that recipe is unavailable.
Keep original rejected media/reviews intact; no corrected effects audio exists.
No new song pairs or further previews were generated, no votes/defaults changed.

Before designing another version, establish actual outgoing phrase completion
or a sufficiently continuous instrumental passage including the playback point,
and a suitable incoming phrase/intro with a gradual overlap. RMS dips and bar
boundaries alone are not semantic phrase evidence. Prefer preserving the current
vocal line and source continuity over jumping to a lower-vocal future bar. The
preceding corrected crossfade retains the owner's "its better" assessment.

## Pedalboard loop/filter/delay preview ready — 2026-11-12

Owner explicitly approved the loop → filter → beat-synced delay → bar-boundary
release example. Plan `docs/superpowers/plans/2026-11-12-loop-filter-delay.md`;
usage and reproduction `docs/loop-effects.md`. Owner described the preceding
corrected crossfade as "its better"; no numeric rating or broad approval inferred.

New preview: **http://127.0.0.1:8007/loop-filter-delay-cdac3973477e4616b7866412cfc5cb6a/loop-filter-delay.mp3**.
Matched baseline in that folder: `crossfade.mp3`. Both 60s stereo, -19.99 LUFS,
true peaks -7.70/-7.44 dBFS. Same source preparations and tempo as corrected pair.
Loop starts 22.3811s, repeats one bar four times, filter sweeps 18k→600Hz,
quarter-note delay 0.476181s with feedback .30 / send max .22 and 250Hz return
highpass. Incoming releases at 30s, echo decays by 33.8095s. Float32 processing.

New `pedalboard-runtime` under experiments/open-dj reads existing CPU packages
without modifying them; pins Pedalboard 0.9.26 Windows cp312 wheel SHA256
`816b7063d3befb00263bfee7656932ee5f51788c586d5184d4d61f7a85f61aea`.
`scripts/setup_pedalboard.py` creates it. `scripts/render_loop_transition.py`
verifies original/prepared/baseline hashes and creates fresh work/published dirs.
`backend/app/research/loop_effects.py` owns deterministic DSP/control timeline.

MDX vocal screening only selected the master-audio template; no separated stem
is audible. Selected outgoing prepared bar 4 (30.0–31.9047s), predicted vocal
RMS ratio .08461 versus .32–.44 in several nearby bars. Model leakage possible.
Screen manifest is alignment/loop-filter-delay-1/vocal-screening.json.

Sample-position loop repeats use 4ms seam crossfades without shortening periods.
Filter state retained across 128-frame automation blocks. Native delay warmup and
fixed 512-frame processing size preserve its state when caller chunk sizes vary;
changing maximum native block size had lost an impulse in a regression test.
Echo tail is explicitly flushed/decayed, RMS .002629 after release.

Verification: independent beat/bar gate and actual loop-body checks passed;
encoded outgoing/loop-release/incoming beat match fractions 1.0, transition
downbeat match 1.0. Five real splice boundaries passed local discontinuity checks.
All output finite/duration/stereo/peak/dropout and HTTP hash checks passed.
40 focused app tests OK with two native-DSP skips; all five DSP tests pass in
the isolated effects runtime. Syntax and diff checks passed. No votes/defaults/
model promotion or commits. Existing ports 8005/8007 only. Listening pending.
Earlier unshared loop pilot b07f4af442164e72be9915530240236a is marked superseded.

## One corrected stereo crossfade ready — 2026-11-12

Owner approved fixing At Night → Stupidisco only. Plan:
`docs/superpowers/plans/2026-11-12-one-aligned-crossfade.md`. Full-original
Beat This analysis saved in `experiments/open-dj/alignment/at-night-stupidisco-1/`
under D:/AI-DJ-data. Full-track markers support nearby regular eight-bar spans.
Fitted tempos 127.01288 / 125 BPM, target 126.00242. Corrected overlap source cues
111.62050 / 121.04000 seconds, replacing 112.09295 / 120.10337. The old cues were
roughly one and two beats after their corresponding predicted bar starts.

New preview: **http://127.0.0.1:8007/corrected-at-night-stupidisco-f0096cf999294ce7b45e2b70dfba792b/corrected.mp3**.
60s stereo; handoff 30s, linear overlap 22.3811–37.6189s. No separation/EQ/GAN.
Prepare each source with 8s real context on both sides before cropping. Native
float32 throughout preparation, constant gain staging, final MP3. Avoid PCM16
clipping before normalization: initial pilot showed ~0.16–0.19% saturated samples
and was superseded, marked with SUPERSEDED.json. Production prepare_excerpt is
unchanged and its PCM16 preparation still merits a separate clipping fix.

Independent analysis of the exact stretched sources: 27/27 beats and 7/7 downbeats
match within declared tolerances, median offsets zero, beat p90 20ms. Six complete
4/4 bars supported on each source; both local overlap halves pass. Encoded solo
sections also retain their source beat timing. Encoding/finite/peak/dropout,
stereo/duration and HTTP content hashes passed. 35 focused tests pass, including
new marker-quantization tempo-fit and invalid/irregular evidence regressions.
Reports include sources, applied settings, full marker predictions, provenance,
technical checks and pending listening status. Old rejected audio/reviews intact.
No defaults, training or owner votes changed. Await listening on this one preview;
model timing checks do not prove phrase/vocal compatibility or musical quality.

## Owner rejected follow-up; beat/bar audit blocks all three — 2026-11-12

Owner: "what is this? none of them are good plus many of them dont even have
matched beat and are off beat". All nine follow-up previews rejected, no named
per-file timing failures invented. Immutable review ID
`4bb313c1ab1840d4aec2ccc652364bb5` is saved in the batch and all pair folders'
`listening-reviews/`, pinned to exact hashes. Prior Move/Say What acceptance stays.

The earlier ready-for-listening/technical checks did not verify actual musical
beat/bar alignment. No timelines existed for the six new tracks. Legacy bass
pulse checks still pass every rejected pair, demonstrating that they are an
insufficient gate. `scripts/audit_listening_timing.py` records this in timing-audit.
Pinned independent Beat This audit (`scripts/audit_listening_beats.py`) detects
~40ms median beat offset in A, and flags predicted bar mismatch in A/B/C; B/C
beats themselves match within 25ms. Bar predictions are irregular on at least one
source of each pair, so these are model flags, not verified bar truth. Do not
blindly move cues by a beat or claim the actual mixes have been fixed.

`backend/app/research/beat_alignment.py` compares markers symmetrically (missing
beats cannot hide), validates regular 4/4 bar support, and fails closed. All three
real rejected pairs are blocked by this independent gate. The research runner
checks owner/test input beats+bars before rendering, records timing-check.json,
and refuses to overwrite any reviewed folder. Example remains smoke-test-only.
Existing app renderer is unchanged and still needs a dedicated alignment fix.
32 focused tests pass, including half-beat, half-tempo, bar-phase, absent markers
and irregular-bar failures. Research audit only; no new previews or promotion.

Next work: establish reliable beat/downbeat/phrase evidence on actual originals
with enough context (or explicit owner correction when uncertain), fix one join,
then listen before another batch. Never equate a successful decode or a periodic
bass-pulse fit with acceptable musical alignment.

## Three additional listening comparisons ready — 2026-11-11

Owner approved testing the simple crossfade on more pairs with GAN and the app
as comparators. Plan: `docs/superpowers/plans/2026-11-11-multi-pair-listening.md`.
Research-only helpers read successful published test jobs in SQLite read-only
mode; pin applied cues, tempo, positions, overlap and originals; reject unsupported
PCM delays and insufficient context. No app votes, models or rendering defaults
were changed. Existing app comparator also differs in separation/gain processing.

Session `D:/AI-DJ-data/experiments/open-dj/auditions/listening-batch-ae9f08aa6f4e4755995d33abc82fcfc8`
is ready_for_listening, with session.json and README.md. Three pairs/six distinct
source songs, excluding the earlier Move/Say What pair:

- A: At Night → Stupidisco; folder `test-pair-6fe842b8e47940d3a67914b7740a46d6`.
- B: Too Much For Me → Dreamer; folder `test-pair-340b3ca2f93b4bee8f38c6405fcbe1ea`.
- C: Sauti → Fire Fire; folder `test-pair-c89d1ffe53ca4586b878432ca9a89b8b`.

Each folder is served on existing 8007. Numbering: 1 existing-app.mp3,
2 djtransgan.mp3, 3 linear.mp3. All 60s mono; handoff 30s; overlap near 22–38s.
Within-pair LUFS: A -20.00, B -20.58/-20.59, C -21.36. All nine passed finite,
duration, true/sample-peak and dropout checks; HTTP downloads match saved SHA256.
No new listening choices yet: await owner feedback separately for A/B/C.
28 focused research/interpreter/comparison tests passed, plus syntax/diff checks.
The batch refuses to regenerate folders with saved listening reviews.

## Development ports consolidated — 2026-11-11

Owner asked why so many ports were running. Verified loopback listeners and exact
AI-DJ serve command lines; no workflow jobs were running. Stopped only obsolete
serve PIDs 9452/19476/352/11484 on 8000/8002/8003/8004. Rechecked: only app 8005
(PID 8720) and benchmark file server 8007 (PID 21752) remain in 8000–8008; both
respond 200. Earlier notes about keeping older servers are superseded. Use these
existing services for further tests instead of opening more development ports.

## Owner accepted both research alternatives on one pair — 2026-11-11

Owner listened to the numbered links (1 existing-app, 2 DJtransGAN, 3 linear)
and said: "2 and 3 are good and both are better then ones we have".
Record only DJtransGAN > existing-app and linear > existing-app for these exact
files; no preference or explicit tie between the two winners was supplied.
An immutable JSON review in the benchmark audition folder's `listening-reviews/`
pins the statement, two comparisons, audio hashes and benchmark report hash.
This is research feedback, not fabricated ranker features or broad promotion.
Existing app feedback remains separate. Earlier "listening pending" below is
superseded for this one pair. No new product rendering mode was activated.

Next technical direction: test a plain crossfade without source separation on
additional distinct pairs before adding complexity. The existing-vs-linear
comparison changes separation, EQ and fade handling together, so it cannot yet
identify which individual component causes the worse sound. Keep DJtransGAN as
the pretrained comparator; the owner has not chosen it over the simple baseline.

## Open-source benchmark evidence — 2026-11-11

Owner approved UnmixDB evaluation and isolated pretrained DJtransGAN inference.
Usage/results: `docs/open-dj-benchmarks.md`; plan:
`docs/superpowers/plans/2026-11-11-open-dj-benchmarks.md`.

- Data/sources/runtime/reports: `D:/AI-DJ-data/experiments/open-dj`. Setup scripts
  pin two upstream commits, verify official dataset checksum, reject unsafe ZIP
  paths and repair interrupted extractions. Additional research dependencies are
  installed only in a separate Python 3.12 venv; existing CPU packages read-only.
- Frozen interpreter UnmixDB baseline: 11 good mixes, 22 oracle-timed fades from
  only two distinct adjacent source pairs. Predictions: 20 unknown, one correct
  gradual_blend, one incorrect eq_handoff. Accuracy 1/22; coverage 2/22. No tuning,
  no owner labels or training writes; does not evaluate transition discovery.
- DJtransGAN author checkpoint: SHA256
  `495987d70bd873fb94838b3af705be85d368a6639659f2ffcc2b05a9740e8fd2`;
  tensor-only load, 122 keys strictly matched, all tensors finite. Adapter copies
  pinned source and removes only eager unused frontend/preprocessing imports;
  executable originals checked against source archive. No random-weight fallback.
- Published-example preflight and real I Move → F Say What pair rendered. Each
  benchmark folder includes source/control/output hashes and runtime provenance.
  Owner pair uses existing job `9f3958001f11492f8df9200868c44877` alternative A's
  cues/tempo/overlap. Three 60-second mono previews: pretrained, exact-input linear
  crossfade, existing app controlled/stem render. Handoff 30s, overlap 14–46s,
  matched ~-21.33 LUFS, no clipping or 100ms near-silent blocks. Mono is explicit;
  preprocessing is our adapter, not exact author madmom replication.
- Listen at **http://127.0.0.1:8007/owner-pair-9f3958001f11492f8df9200868c44877/**.
  Isolated standard-library file server exec session 64720 serves only audition
  artifacts, no votes; existing app remains on 8005. Listening acceptance pending,
  no default promotion. Existing app comparator also differs in source separation.
- Validation: 27 focused research, interpreter and pair-comparison tests passed;
  both real inference runs passed audio checks; repeated inference reproduced
  identical output hashes. Five new tests cover truth/speed mapping, missing or
  corrupted weights, unsafe archives and partial extraction. HTTP audio/index and
  existing Compare responded 200. Tempo preparation at 0.96/1.04 also preserved
  one-second duration and a 1kHz test tone. No commits or benchmark feedback writes.
- Latest read-only owner-feedback audit: five feedback events and two audition
  reviews, both currently B (including the earlier real comparison). Preserve
  these choices. Earlier pair-section counts/unvoted status describe its original
  completion, not the current state. The research baseline explicitly uses that
  job's first/A alternative; it does not represent an owner-selected winner.

## Pair listening shipped locally — 2026-11-11

Owner approved the one-pair matched-comparison milestone after reporting poor
generated transitions. Implementation plan:
`docs/superpowers/plans/2026-11-11-pair-listening.md`; usage:
`docs/pair-listening.md`. Current final app: **http://127.0.0.1:8005/compare**.
Managed server exec session 80553, Python PID 8720 at completion. Older ports
retain earlier code; use 8005 for Compare. Restarted only the managed test server
through its own exec session; no existing older server was killed.

- `/compare` selects two registered sources and runs durable `pair_audition` jobs.
  Existing timeline revisions and optional preference model are pinned. Missing
  timelines are analyzed in the heavy worker. Up to twelve contextual candidates
  receive waveform checks; two distinct recipes/cues render via existing stem
  handling and common loudness matching. Both previews must succeed to publish.
- A/B players support same-position switching, handoff seek and exclusive playback.
  Polling retains audio nodes. A/B/tie/neither and optional reasons persist with
  revision conflicts. Compare navigation and phone header wrapping are shared.
- Preference ranker v2 adds candidate energy/harmonic/embedding/vocal/trend features
  with unknown masks; legacy vectors pad to the new dimensions without rewriting
  reports. Descriptor/render features matched exactly on both real previews.
  Explicit learned ranking pins its snapshot and requires the existing six
  distinct comparisons / three song pairs minimum. No automatic promotion.
- Tie/neither preserve history and revoke any previous pairwise winner; ratings
  cannot manufacture a replacement after a neutral choice. Neither makes the next
  job for those ordered source hashes skip the two explicitly rejected candidate
  IDs. No unplayed alternatives are labeled bad. Old feedback is preserved.
- Schema 9 allows pair_audition jobs, preserving prior jobs/model foreign keys.
  Feedback stays in the existing separate preferences SQLite database; per-job
  review revisions are transactional with feedback events. Media and feedback
  verify successful publication and immutable audio hashes. Cancelled jobs cannot
  expose previews. Comparison history is independent of other job kinds.
- Real job `9f3958001f11492f8df9200868c44877`: I Move (Lyrics) -> F Say What;
  alternative A controlled_16, B eq_8; both 128 seconds, handoff at 64 seconds,
  matched -20.00/-20.01 LUFS. Available and **unvoted** for owner listening.
  Rendering does not establish that either version sounds good.
- Validation: full suite 134 tests OK, four isolated-runtime skips. After adding
  the explicit-neither candidate exclusion, all eight comparison tests passed.
  Browser: 19 checks passed, including real playback/switching, all four feedback
  choices, reload, conflicts, node preservation and 390/1440 widths/navigation.
  Browser votes were written ONLY to a copied database under
  `D:/AI-DJ-data/tmp/comparison-browser-fixture`, served temporarily on 8006.
  Owner feedback still has exactly one original event and zero fixture labels.
  Evidence: `.impeccable/review/compare`; suite log:
  `D:/AI-DJ-data/tmp/pair-listening-suite.log`. App DB backup before migration:
  `D:/AI-DJ-data/tmp/before-pair-comparison.sqlite3`.
- No commits, pushes, public hosting, new dependencies or owner listening labels.

## Owner's three-stage architecture — 2026-11-11

Owner specified separate transition parsing, behavior interpretation and learning
for new sets. Target architecture and implementation/acceptance sequence:
`docs/superpowers/plans/2026-11-11-three-stage-learning.md`.
The existing matcher/interpreter/cue model are baselines, not three finished ML
models. Preserve the distinction. Stage 2 needs per-observation structured
outputs rather than forcing everything into the renderer's four preset names;
stage 3 learns from those supported fields, not generated prose. Human correction
and inference provenance remain separate. This turn records architecture only;
no new trained models, parser replacement or product-code implementation claimed.

## Recognition correction — 2026-11-11

Owner correctly reported that completed analysis jobs were not useful recognition.
The original baseline produced zero types. Replaced power-additive fitting with
linear magnitudes and added bounded before-entry/after-exit context. Boundary gain
summaries now use a fixed short window rather than 20% of the entire overlap,
which could hide a hard exit. No confidence thresholds were loosened.

- Current analyzer: `transition-magnitude-context-3`. Exact source/review identity,
  stale handling, immutable human fields and high-evidence training gate persist.
- Live final app: **http://127.0.0.1:8004/references**. Earlier servers on 8000,
  8002 and 8003 retain old Python modules; use 8004 for current results. Previous
  environment rejection prevented stopping those servers. New worker rejects old
  algorithm requests explicitly instead of silently applying a different version.
- Real batch `696a50a0a52b4fbabf6358e177fe2165`: 26 processed, 6 written technique
  estimates (EQ handoff / gradual blend), 20 uncertain, **0 training labels**.
  Estimates are moderate, not human-confirmed or proven accurate. Do not claim
  style learning is solved. No owner model was trained during this correction.
- UI shows three measured band observations when supported and explicit result
  counts on References and Learning; prior analyzer jobs are identified as older
  results. Backend analyses never populate the human style selector.
- Verification: final 31 related tests passed, including all 14 analyzer tests
  covering hard-exit context, wrong/missing sources, actual decoding and
  version-request guards. Eight browser checks passed against saved
  real results, with 390/1440 screenshots under
  `.impeccable/review/transition-analysis/recognition-v3-*`.
- Read-only diagnostic CLI: `scripts/local.ps1 -m scripts.diagnose_transition_analysis`.
  It compares saved versus alternative mappings without changing reviews.
- An earlier development batch was cancelled before publication after the
  boundary-window test exposed a remaining defect. Its cancellation is truthful
  history. Final batch above succeeded. No commits or pushes.

## Automatic transition descriptions — 2026-11-11

Owner approved a local analyzer so they can correct timing without knowing the
transition technique. Usage: `docs/transition-analysis.md`; plan:
`docs/superpowers/plans/2026-11-11-transition-analysis.md`.

- References now has Analyze transition / Analyze reviewed transitions, written
  descriptions, heuristic evidence, provenance, background progress/cancel/retry.
  Saved complete timing drafts can be inspected individually; only completed,
  included reviews can enter training. Saved human fields are never overwritten.
- Algorithm `transition-subband-2`: nonnegative per-band spectral attribution,
  bounded offset refinement, fit/conditioning/support gates; gradual and EQ
  handoffs, plus surrounding-audio verification for cuts. Renderer recipe mapping
  requires supported technique and bar duration; short marked timing alone cannot
  prove a cut. This is an uncalibrated spectral baseline, not a general audio AI.
- Schema 8 preserves old jobs/models while allowing transition_analysis jobs.
  Immutable successful results pin review revision, decision/source/recording
  hashes and implementation provenance. Cancellation fences publication; stale
  estimates cannot supply current labels. Human exports remain human-only.
- Training separately enriches unknown styles from supported high-evidence
  estimates at weight 0.35. Human styles win. Reports separate human accuracy from
  automatic-label agreement. No actual owner model was trained or promoted.
- Real included-review batches and a single-transition UI job completed. The
  current recordings/cues did not yield any supported automatic recipe labels;
  retain unknown rather than claiming technique recognition worked. In particular
  the first reviewed outgoing interval implies about 18% slowdown versus its
  marked recording interval and is explicitly flagged. Other poor fits can mean
  cue/version mismatches or effects outside the baseline. Do not loosen confidence
  gates just to fill labels. Further accuracy needs validated alignments/evaluation.
- Verification: full suite 124 tests OK, 4 runtime-specific skips; isolated CPU
  style-supervision test passed separately. Five workflow/provenance tests passed
  after final guards. Browser: 16 checks passed including actual single/batch jobs,
  unknown-label preservation, dirty protection and 390/768/1440 widths. Evidence:
  `.impeccable/review/transition-analysis`. DB backed up before live migration to
  `D:/AI-DJ-data/tmp/before-transition-analysis-20261111-203750.sqlite3`.
- Root `python run.py` starts the app with the existing venv and local D: settings;
  earlier long-form PowerShell startup still works. No commits or pushes made.
- Updated live app for this session: **http://127.0.0.1:8003/references**. The
  environment blocked stopping the existing 8000 server, so it was left alone;
  8002 is the earlier verification instance. New 8003 serves final code, sharing
  the same saved reviews. Its logs are `D:/AI-DJ-data/tmp/analysis-updated-server.*.log`.
  Save edits in any older tab before switching. The ordinary launcher still
  defaults to 8000 for future starts when that port is free.

## Training and test mixes from the UI — 2026-11-08

Owner requested completing review → training → test mixes with buttons, without
chat commands. Implemented **http://127.0.0.1:8000/learning**, shared navigation
and reference-page link. Usage: `docs/ui-learning.md`; implementation plan:
`docs/superpowers/plans/2026-11-08-ui-learning-workflow.md`.

- Train from included reviews, choose model version, select/upload/reorder songs,
  generate model test or baseline, monitor progress, cancel/retry, play/download.
  Polling preserves active audio nodes and exclusive playback; no autoplay.
- Schema 7 persists jobs, a single heavy-worker lease and model registry. Training
  pins review revisions and source hashes. Pending/excluded reviews never train;
  unknown styles are masked. CPU supervised source-cue/overlap prediction uses
  frozen spectral features, with source-disjoint holdout where possible. This is
  separate from the earlier weak successor-context model. No default promotion.
- Models/artifacts/checkpoints are hashed and loaded strictly. Changed reviews
  require retraining before another model test. Jobs retain immutable snapshots,
  cancellation kills owned subprocesses, and publication guards preserve prior
  playable results. Retry/recovery and duplicate active-request handling persist.
- Test cues use nearest rhythm-supported bar candidates within 32 seconds of
  predictions; movements are visible. Model recipes cannot silently change after
  technical validation fails. Ordered songs, including repeats, remain intact.
- Actual owner data remains **3 included completed reviews**, positions 0,1,3,
  and zero style labels. No owner decisions or synthetic labels were added.
  Real UI training job/model `f5dc59e4371e466aaaa572f6767e92d0` succeeded.
  Train 2 / held-out 1; normalized held-out MSE 0.05131 vs mean baseline 0.03789.
  The UI honestly reports this worse result and keeps the model experimental.
- Real model test `ed0b9fcfcca54c09807f450169c9bdc7` rendered 87.24 seconds,
  mix `41b932c495b448eda595996f3f32fc8d`. Another user-visible model test also
  succeeded. UI baseline → Cancel → Retry produced successful baseline job
  `3c4e00dbe4cf4269ae1617863f2a3e07`, 125.72 seconds. Earlier failed/cancelled
  jobs remain truthful history. Technical success is not musical acceptance.
- Full suite: **110 tests OK, 3 isolated-runtime skips**. Then **10 targeted
  tests passed**, including two additions after that run. Isolated CPU PyTorch
  run: **4 passed**. Browser: **18 checks passed**, plus actual training/render/
  cancel/retry actions. Evidence/screenshots: `.impeccable/review/learning`.
- Healthy existing local server remains running; logs
  `D:\AI-DJ-data\tmp\workflow-server.{out,err}.log`. Live upload response may
  omit an ID until the next normal restart; the client supports both response
  versions by resolving newly registered catalog IDs. No restart is needed.
- Inherited true-black-flat/Inter design preserved. Inspector: 0 FAIL; native
  audio accounts for the panel-void warning. Independent finish reviewer found
  one material issue, now resolved: historical model jobs display their pinned
  version/identity even if the current selector changes or the model is missing.
  Reviewer verdict pass: **ship for that sole scored fix**. Four additional
  browser provenance checks passed across all three historical model jobs.
  Documenter comparison confirms incumbent-system fidelity; DESIGN.md and its
  sidecar remain unchanged. Pre-existing PRODUCT.md drift was recorded without
  repair. Review and documentation reports are in the learning evidence folder.

Reference review is still the human step. After more saved included reviews,
press Train, then choose songs and Generate test mix. Learning quality beyond
this small experiment needs more representative reviewed transitions/listening.
No commits, pushes, external services or learned waveform/EQ curves were added.

## Entry/exit-only save fix — 2026-11-08

Owner reported being unable to save corrected recording entry/exit. The previous
form required a completed listening decision and all six included-example times;
editing also cleared listening confirmation. Added a separate pending timing save.

- Any corrected endpoint can now save via **Save timing**, with undecided learning
  choice, missing source cues and no listening confirmation. Pending revisions
  preserve partial progress; they are never exported as reviewed examples.
- Explicit completed include/exclude reviews remain strict. Saving a changed
  approved review without re-confirming makes the new revision pending and removes
  it from current training export. Old revisions stay intact. Counts/queue/form
  distinguish saved timing drafts from actual completed listening reviews.
- Fixed reload race: lock controls until the reference response has populated
  the form so refresh cannot overwrite a concurrent edit/save result.
- Validation still rejects nonfinite/out-of-range/reversed times with field
  names in the error. No schema migration required; new reviewed=false payloads
  use the existing append-only reference_transition_reviews table.
- **21 reference/review tests pass** and **13 browser regression checks pass**
  against isolated copied data, including two-field/one-field saves, reload
  survival, missing source cues, pending inclusion exclusion from training,
  explicit approval, correction after approval, reload locking and 1440/390 fit.
- Existing user reviews are preserved: production had actual saved reviews at
  positions 0, 1 and 3 while debugging; do not confuse them with synthetic tests
  or overwrite/reset them. Browser regression rows live only in
  `D:\AI-DJ-data\tmp\reference-review-browser-9be7d7ae4ea34009aa2cae04b99f9349`.
  Production server restarted with updated backend, hidden/detached; logs now
  `D:\AI-DJ-data\tmp\save-timing-server.{out,err}.log`.
  Screenshots/checks: `.impeccable/review/references/save-timing-*`.

Owner should note any times still unsaved in the old open page before refreshing
to load the new client; future edits can then save as pending timing immediately.
No human review decisions or new training labels were created by the agent.

## Actual transition drafts and browser listening review — 2026-11-08

Owner accepted extracting/reviewing actual reference transition decisions before
training on them. Implemented preparation and the human collection surface;
the owner must now listen and save actual decisions. Usage:
`docs/reference-review.md`; plan:
`docs/superpowers/plans/2026-11-08-transition-review.md`.

- `reference_review.py` fits source-to-recording mappings and measures aligned
  four-second spectral agreement. It proposes source-bounded overlap/search
  brackets and labels coarse anchor fallback. These are listening search ranges,
  not proof of exact audible fades. Styles/bars/vocal/energy labels stay unknown.
- Real 40-join batch:
  `87855a29974246056e45efdde3eb964afe6482566cb55c22f46884e7b6c4b986`.
  Artifact: `D:\AI-DJ-data\references\housemix-n3\transition-drafts.json`.
  There are 38 bounded draft/search ranges and two unresolved handoffs around
  Can't Get Enough. All 41 occurrences/40 joins remain. Earlier extraction
  iterations stay immutable; the newest batch is shown in the UI.
- SQLite schema 6 adds immutable transition drafts and append-only per-join
  listening reviews with optimistic revisions. Reviews choose registered sources,
  edit six times, optionally label style/bars/vocals/energy, explicitly include/
  exclude and confirm listening. Included examples need valid complete timing;
  exclusions may keep unknowns. Millisecond display rounding respects bounds.
  Exports contain only latest explicitly reviewed/included observations, never
  drafts or fabricated preference negatives.
- **http://127.0.0.1:8000/references**, linked from Mixes/Timelines: native MP4
  recording/source players, exclusive playback, scoped handoff listening, cue
  marking, queue/filter, independent save/export, dirty/saving/failure/conflict
  recovery. Phone queue folds; tablet source players stack. Unknown styles stay
  unlabeled. Audio resolves registered IDs and rejects changed source bytes.
  Heavy extraction is CLI-only, never triggered by page GET requests.
- Production server restarted detached/hidden with current code via local.ps1.
  Logs: `D:\AI-DJ-data\tmp\reference-review-server.{out,err}.log`.
  Isolated browser server on 8001 was stopped. Its copied database remains at
  `D:\AI-DJ-data\tmp\reference-review-browser-9c626f902dd24bf3bcc92b03aaf779f3`.
  Synthetic browser reviews exist there only. Production confirmed 0/40 reviewed,
  zero included/excluded and an empty training export after browser testing.
- Verification: full suite **94 tests, OK, one PyTorch-only skip**. Added a final
  millisecond-boundary regression afterward; all **seven reference-review tests
  pass**. Synthetic extraction locates an 80–100s overlap; persistence/API tests
  cover immutable drafts, revisions, exclusions/cuts, unknowns, ranges, hashes and
  cross-origin restrictions. **31 real browser checks pass**, including actual
  MP4 playback/seeking, source exclusivity, marking, saves/exports, stale writes,
  failed/delayed saves, dirty work, empty/error recovery and 1440/768/390 fit.
  None of these checks implies musical acceptance.
- Design-taste-frontend and Impeccable skills inherited the existing true-black
  direction/Inter/tokens with no redraw. Inspector zero FAIL, one native-audio
  panel-void false positive. Fresh finish-review disposition **ship**, no material
  fixes. Documenter comparison also ship; DESIGN.md/design.json preserved.
  Evidence under `.impeccable/review/references`. Pre-existing PRODUCT.md identity
  wording drift was recorded without repair. No commits or pushes.

Next: owner opens References, listens to a few handoffs, corrects recording/source
times, includes useful examples and saves. Supervised cue/style learning should
consume those decisions once they exist. Saving does not automatically train;
no listening labels or subsequent training were fabricated in this turn.

## Experimental ML trained on HouseMixN3 — 2026-11-08

Owner explicitly said "train ML on that mix". Completed an actual CPU PyTorch
training run on the matched source/recording passages and supplied order.
Plan: `docs/superpowers/plans/2026-11-08-reference-training.md`.
Usage/limits: `docs/reference-learning.md`.

- New `planning/reference_learning.py` builds positive-only observed-successor
  context examples, splits source identities with a recording-window embargo,
  fits train-only scalers, trains and strictly loads the small residual network.
  CLI: `scripts.train_reference`; isolated runtime worker:
  `scripts.reference_training_worker`. No new packages or downloads.
- Model predicts next-source spectral musical descriptors from outgoing source
  and actual recording context. It does not claim cue/style/preference learning,
  exact mixer controls or learned audio/EQ curves. Automatic anchors remain
  unreviewed; human style/preference counts stay zero. Missing entry 6 is excluded
  without bridging its neighbors. No feedback database or active model changed.
- Real dataset: 40 located occurrences, 133 augmented windows from 38 observed
  joins. Training: 86 windows/26 joins. Evaluation: 36 windows/nine joins.
  Cross-group edges: eleven windows/three joins excluded. Repeated source hash
  occurrences stay in one group; all windows of each pair stay together.
- PyTorch 2.6.0+cpu, NumPy 1.26.4 in existing timeline runtime. Seed 11, 300 fixed
  epochs, 128→24→64 residual network; no held-out hyperparameter selection.
  Pair-weighted evaluation MSE: **2.5470 model, 1.6950 mean baseline, 3.0990
  persistence**. Training MSE 0.3575. It beats persistence but fails the mean
  baseline. No mixing-quality improvement or independent-set generalization is
  established. Status experimental, inactive, no listening approval.
- Model artifacts at
  `D:\AI-DJ-data\models\reference-context-87e4edc6e599d44f1939087175a1d0d27cc47fed365690687dac47166f47f2c2`:
  checkpoint.pt, config.json, dataset.json, split.json, report.json. Dataset,
  config, split and checkpoint have recorded hashes, runtime/implementation
  provenance and immutable publication. Existing identical runs are preserved.
- Human-readable result:
  `D:\AI-DJ-data\references\housemix-n3\training-report.md`.
  `training-result.json` links the model; `prediction-smoke.json` contains a real
  strict-load prediction from a held-out example (64 finite dimensions).
- Verification: six learning tests all pass in isolated PyTorch runtime,
  including reproducible fitting, tensor-only strict loading and tamper rejection.
  Main-runtime learning/reference tests: 16 passed, one PyTorch-only check skipped
  there (passed in isolation). Tests cover unresolved gaps, source-group leakage,
  repeated sources, recording embargo, train-only scaling and finite descriptors.
  No commits or pushes.

Reference-style supervision and contextual preference ranking still require
their actual labels. This experiment is a trained precursor, not completion of
the entire saved learning milestone. Do not tune to the reported held-out split.

## Reference recording import and first real collection — 2026-11-08

Owner requested reference import and supplied an untimestamped 41-song ordered
list plus `D:\G1-Drive\Dj\Mixes\HouseMixN3. Good 1 hour mix.mp4` and sources in
`D:\G1-Drive\Dj\House Bangers`. Recording duration: 3657.119637 seconds (60:57).
Owner clarified that House Music Anthem is a remix of Move Your Body and that
Strings of Life uses the vocal version. Owner subsequently confirmed the proposed
Herd & Fitz and Marshall Jefferson/Solardo source versions are correct. Preserve
this as identity confirmation, not listening approval of inferred alignments.

- Added `references.py`, bounded spectral matching, SQLite schema 5 and
  `scripts.import_reference` commands: import/show/align/refine/report/template/
  review. Usage: `docs/reference-import.md`; implementation scope:
  `docs/superpowers/plans/2026-11-08-reference-import.md`.
- Inputs are read in place. Immutable import snapshots retain file hashes,
  explicit alternative sources, repeated occurrences and missing-source slots.
  Invalid explicit files fail before publication. Audio extraction uses 40s
  chunks plus FFT context; 4 Hz log spectral features are cached on D:.
- Global matching searches 16s windows and duration ratios 0.92–1.08. Ordered
  proposals require multiple supporting windows and increasing recording anchors.
  Refinement searches unresolved slots between neighboring anchors, preserves
  the parent alignment and stores another immutable snapshot. Similarities are
  uncalibrated; anchors do not establish track boundaries or exact mixer controls.
- Human JSON review requires every ordered source/excerpt, explicit reviewed
  status and optimistic revision. Bounds, identity, order and transition fields
  are validated; observations append revisions. Unknown controls remain null.
  Reference observations never become preference negatives automatically.
- Actual reference ID:
  `2ef77cd59eb76b6d2ca0fa2059624f780bb399f5d4043a78a408f16ff762576b`.
  Import, manifest, initial/refined alignments, report and untouched review
  template live at `D:\AI-DJ-data\references\housemix-n3`.
  `owner-confirmations.json` preserves the later explicit source-identity replies;
  import-time notes remain immutable. `unresolved-06-cant-get-enough.mp3` is a
  review excerpt of recording seconds 366–531.75, not a proposed exact interval.
  Latest detailed alignment ID:
  `91a13ff56f1d1d0f93b201c77c8af167d9044b90b1189a32e7de0553cd332d4f`.
  **40/41 ordered proposals; one unresolved**: entry 6 Can't Get Enough (the
  source is Herd & Fitz — I Just Can't Get Enough 2024). Detailed gap search
  added a weak unreviewed proposal for entry 9 Move Your Body. The same
  Marshall Jefferson/Solardo file also matches entry 38 House Music Anthem.
  Both Stupidisco alternatives were compared; the original Junior Jack file
  has the ordered proposal. Vocal Strings of Life also has a proposal.
- No real alignment/listening approval or training labels were entered.
- Verification: full **81-test suite passed** after updating the old migration
  assertion to schema 5. An additional refinement/persistence test was then added;
  all **11 reference tests pass**. Synthetic decoded audio checks chunk continuity
  and source localization; tempo-changed feature tests and human-review tests
  cover ambiguity, unknowns, repeated tracks, bad bounds and stale revisions.

This milestone supplies CLI import/alignment/JSON review. Browser reference
annotation, durable progress and contextual training remain unfinished. Existing
generated mixes stay available through the browser. No commits or pushes.

## Mixes now visible and playable in browser — 2026-11-07

Owner asked why the mix was absent from the web interface. Added the missing
listening surface; `http://127.0.0.1:8000/` and `/mixes` now open completed mixes.
Source correction remains at `/timelines`, linked in the shared navigation.

- `playback.py` lists published/playable SQLite renders, timestamped tracklists,
  actual transition windows and recent matched audition events. It serves only
  registered audio inside render storage. Full-mix audio URLs are pinned to
  their playable revision so a new render cannot splice into an existing stream.
  Failed rerenders preserve the previous playable version; missing audio has an
  explicit unavailable state. HTTP ranges and downloads are supported.
- `mixes.html/css/js` inherits the existing design. Full mix player/download is
  first, followed by seekable tracks/transitions and two recent previews filtered
  to adjacent source pairs in the selected set. Play handoff starts four seconds
  before the shown seam. Starting a player pauses all others. No autoplay.
- Actual Move/Say What set and matched previews are visible and stream from the
  browser. The local server was restarted on port 8000 (process 10452 in this
  session). Root now means listening, not source timeline review.
- **71 automated tests pass**, including four new playback API regressions for
  ranges, downloads, tracklist, revision pinning, failed rerenders, absent files
  and registered audition path restrictions. Thirteen real browser checks passed
  for muted playback/seeking/download, player exclusivity, responsive fit at
  1440/768/390, preserved timeline navigation and failed-refresh recovery.
- Visual review disposition ship for this inherited extension; no material
  findings. The static hierarchy false positive on mixes.html is narrowly waived
  with browser-size evidence. Native media control whitespace and no-data-hue
  inspector warnings are intentional: this page contains players, not a chart.
  Surface contract: `docs/mixes-surface.md`. No owner feedback or audio changed.

Mix generation/import/background progress and explicit browser preference voting
remain later work. This extension supplies playback for existing completed
renders and previews; it does not claim the whole planned application is done.
No commits or pushes.

## Contextual candidates, auditions and set integration — 2026-11-07

Implemented step 3's conservative baseline. See `docs/contextual-transitions.md`
and `docs/superpowers/plans/2026-11-07-contextual-candidates.md`.

- `planning/contextual.py` proposes up to twelve cue/recipe alternatives from
  effective timeline snapshots. It uses local energy/trend, bass, chroma, frozen
  embeddings, vocal activity, downbeat/bar and section evidence. The method is
  explicitly a deterministic context baseline, not trained personal taste.
- Recipes: 32-bar groove, controlled 16-bar blend, 8-bar EQ exchange, 40ms
  phrase-aligned cut. Cuts need corrected phrase or phrase-plus-section evidence
  plus known vocal gaps; an energy spike alone cannot trigger one. Rising
  sections, including the earlier mids fade of a long blend, are protected.
- `auditions.py` independently validates prepared waveform phase/drift, bounds,
  stretch and levels. Small cue corrections are recorded and capped. Rendering
  checks the separated instrumentals and encoded audio. Fixed non-overlapping
  vocal windows leave the groove running. No recipe fallback during auditions.
- A/B files have a shared duration and centered handoff, measured integrated-LUFS
  matching and true-peak headroom. Matched files are new artifacts; original
  previews remain stored. Legacy preference feature/report fields are retained
  in newly generated reports; no new listening labels were entered.
- SQLite version 4 adds immutable transition candidate snapshots and append-only
  validation/rejection/audition events. Timeline IDs, correction revisions,
  model/config identities and context vectors remain attributable.
- `scripts.suggest_transitions` handles ordered-pair comparisons. `scripts.plan_mix`
  and `scripts.render_set` accept `--contextual`: keep existing ML ordering, choose
  validated contextual joins, check neighboring excerpt geometry and retain every
  input. Missing/invalid context retains an explicitly reported conservative
  join. Selected contextual joins fail clearly if final validation fails.
- Real Move → Say What: twelve proposals from twenty screened choices, eleven
  prepared-audio validations. Two 128s matched auditions with handoff at 64s:
  controlled 16 bars at source anchors 128.18/74.14s, and 8-bar EQ at
  144.18/74.14s. Verified pair report:
  `D:\AI-DJ-data\plans\context-pair-47cda1b563fc442da4429aff3902d1f9.json`.
  Its matched outputs measured -20.00/-20.01 LUFS and -4.10/-3.76 dBFS true peak.
  Final repeat with legacy feedback report compatibility:
  `D:\AI-DJ-data\plans\context-pair-6a3f8909c04548bc8fb886b5e7b28046.json`.
  A (16 bars): `D:\AI-DJ-data\renders\matched-audition-1f099e4c0bc64056b783cfcd23a8ed11.mp3`.
  B (8 bars): `D:\AI-DJ-data\renders\matched-audition-3db89f39ccd6413d86d74cd89f9bda67.mp3`.
- Real contextual full-set plan `mix-d6a68a4fd24a4d008aa214372862a06f` rendered
  successfully with BOTH inputs, controlled 16-bar join, duration 197.998s and
  encoded peak 0.8012. Playable output:
  `D:\AI-DJ-data\renders\set-476f9c744fbc42c6aba1f716c1cffe81.mp3`.
  Adjacent JSON/TXT contain applied cues and tracklist. Float separator stems
  are now converted to PCM16 only for pulse checking, fixing a real full-set
  integration gap; float stems continue into the mixer.
- Final verification: **67 tests pass**, including eleven new contextual tests,
  actual generated-audio renders for every recipe, LUFS matching, adjacent-join
  geometry, float-stem full-set integration, immutable identities and rejected
  waveform failures. Actual model separation/instrument timing also passed for
  the real auditions and full set. Production correction revisions remain zero
  for both real tracks. Original explicit owner comparison count remains ONE.

Listening approval remains pending. Next saved-plan milestone is reference mix
import/alignment/annotation, followed by contextual ranking/style learning and
the complete browser listening workflow. Durable worker integration remains
unfinished. The timeline review UI remains available; pair audition generation
is currently exposed through CLI/shared services. No commits or pushes.

## Musical timelines and local correction editor — 2026-11-07

Continued step 2 of the recovered Plan mode workflow. New implementation plan:
`docs/superpowers/plans/2026-11-07-musical-timelines.md`. Usage and limits:
`docs/timeline-usage.md`. New local UI: `http://127.0.0.1:8000`, launched with
`scripts/local.ps1 -m scripts.serve` (server started in this session).

- Isolated Python 3.12 CPU inference environment: `D:\AI-DJ-data\timeline\venv`.
  Beat This 1.1.0/final0, frozen MERT-v1-95M, torch/torchaudio 2.6 CPU,
  Transformers 4.38.2. Core requirements and exact runtime lock are checked in;
  setup downloads artifacts to D:. MERT revision is pinned and all model files
  have recorded hashes. Beat This's official host had an expired certificate;
  setup falls back to a pinned reupload with a fixed verified SHA-256.
- Worker uses 30s cores with 4s beat context and 5s frozen MERT windows. DSP
  bins retain RMS/peak, bass, transient-density proxy and chroma. Optional vocals
  reuse the existing DirectML separator on bounded source chunks; absent vocals
  stay unknown. Candidate phrases/sections are explicitly tentative, confidence
  uncalibrated. No named verse/chorus/drop claims.
- Important loader fix: default MERT loading silently skipped positional
  weight-norm tensors under modern PyTorch. That run was stopped before storage.
  The worker now maps old g/v names to parametrization names and loads ALL tensors
  strictly. Two full strict-loader runs on I Move succeeded. HF module/model
  caches are directed onto D: before Transformers imports.
- SQLite schema 3 adds immutable predictions, track associations and append-only
  optimistic-lock correction revisions. Human overrides preserve original
  estimates; correction history belongs to the particular analysis ID. Cache
  identity includes source, models, dependencies, adapter and configuration.
  The library shows the newest analysis per track; older versions remain stored.
- Real track: `D:\G1-Drive\Dj\AfroHouse\I Move (Lyrics).mp3`, 177.70s. Output:
  354 beats, 89 downbeats, 88 candidate four-beat bars, 36 embeddings, 178 DSP
  bins, 356 vocal bins, three section-change candidates. Latest timeline ID:
  `6d10ed7707adc9a697aa7e1f875d1806bd0ffa072df9e8e92f54742aa1aaf44f`.
  Track ID: `timeline-e352917db2528148e6539c0b`. Production corrections remain
  revision 0. These are inference outputs, not human-approved annotations.
- Loopback FastAPI editor supports source playback/range requests, seeking,
  whole-song/30s/60s zoom, coarse waveform/energy/vocal/downbeat/phrase overlays,
  add/remove marker, revision save, restore estimates and discard edits.
  Save locks conflicting controls; stale saves require reload. Browser requests
  use IDs and cannot choose arbitrary source paths.
- Validation: **56 tests pass**, including 11 new timeline/API/feature tests.
  Browser checks passed for muted playback, seek/zoom, marker saves and delayed
  save locking, error/filter/restore/discard states, loaded font and no horizontal
  overflow at 1440/768/390. Browser mutations used the isolated database in
  `D:\AI-DJ-data\tmp\test-timeline-browser`, not production. Its temporary server
  on 8001 was stopped. Screenshots/check artifacts are gitignored under
  `.impeccable/review`. Fresh design review scored the identified fixes resolved;
  design tokens documented in DESIGN.md and `.impeccable/design.json`.

Next saved-plan work: contextual candidate generation consuming effective
timelines; all four recipes and comparable auditions. Manual annotation/listening
evaluation of the new estimates is pending. Timelines do not yet change existing
mix choices. Durable worker/import progress, reference annotation, contextual
ranking and the complete listening workflow remain future work. No commits or
pushes, no owner feedback fabricated. Earlier sections below are history.

## Resumed Plan mode workflow — 2026-11-07

Canonical repository: `C:\Users\user\Documents\GitHub\AI-DJ`. The Desktop path
in older sessions is absent; `Projects\ai-dj-set` is an older design-only copy.
Recovered the exact previous Plan mode proposal into
`docs/superpowers/plans/2026-11-07-context-aware-workflow.md` and wrote the first
implementation slice in `2026-11-07-rendering-foundation.md` alongside it.

Implemented the shared rendering/persistence foundation:

- `backend/app/library.py` owns discovery, analysis and atomic initial-plan
  registration. `scripts.plan_mix` and `scripts.render_set` call these services.
- `backend/app/rendering.py` extracts the disk-backed stem renderer from the
  fixed ten-track experiment. It accepts arbitrary input entries and a saved
  plan; separator paths resolve below the configured data root. The set CLI now
  requires explicit files or a directory (`--excerpt-seconds` defaults to 144).
- SQLite version 2 adds append-only render-attempt history. Requested plans and
  planning-model provenance are snapshotted. Reports retain applied cues, PCM
  delays, trims and actual joins; saved requested plans stay immutable.
- Planned boundary joins remain boundary joins. Beatmatched joins are checked
  across overlap windows before and after separation. Geometry, source hashes,
  decoded duration/stereo/finite samples/peak/silence are validated. Failed or
  stale completions never replace the last playable revision.
- Final verification: **45 tests pass**, including ten new persistence/rendering
  regressions and real FFmpeg synthetic stereo renders for 1/2/3 entries. Model
  inference is substituted in these new tests; no new real-music listening
  approval or real separator integration run is claimed. No commits or pushes.

Next: continue the saved plan. Durable worker/restart integration, musical
timelines and correction UI, contextual candidates, reference annotation and
contextual ranking/listening UI remain unfinished. Existing pair experiments
and the original feedback store remain compatible; they have not yet all been
converted into this shared set pipeline. No owner feedback was fabricated.
The owner requests no routine approval questions; the app may still enforce
command permissions. The sandbox process launcher failed during this session.

Older history follows; where it conflicts, the dated update above is current.

**Project path:** `C:\Users\user\Documents\GitHub\AI-DJ`
**Date of handoff:** 2026-11-06  
**Prior context:** Design approved. Foundation, validated two-track/stem renderers, and milestone 3 unsupervised library planning are implemented. Owner approved the long Move → Say What reference blend. Twenty-nine tests pass. Actual ML-selected pair preview validated; musical listening is pending. Full-set audio rendering and the web app remain unfinished.

## What this is

A personal house-music DJ set builder (rave.dj-like): user uploads their own tracks; the system produces one playable mixed set with DJ-like transitions. Develop and run locally on the owner’s PC first; Ubuntu hosting is deferred.

## Done so far

- [x] Product brainstorm with owner
- [x] Written design: `docs/superpowers/specs/2026-10-30-ai-dj-set-design.md`
- [x] Builder review of design → 4 open questions (below)
- [x] Owner answers open questions; decisions written into design
- [x] Design approved by owner on 2026-11-06
- [x] Implementation plan: `docs/superpowers/plans/2026-11-06-ai-dj-set-implementation.md`
- [x] Milestone 1 foundation and five automated tests
- [x] Local launcher verified: FFmpeg/ffprobe 9.0.2 and Rubber Band filter available; data initialized on D: with about 299 GiB free
- [x] Audio analysis and two-track prototype (synthetic checks complete)
- [x] Owner accepted the long Move → Say What reference blend
- [x] Milestone 3 ML ordering/style planner, library run, persisted plan and automatic audition
- [ ] Owner listening evaluation of the ML-selected audition and complete playlist

## Hard gate

**Do not scaffold, install deps, or write product code until the owner approves the design** (after open questions are resolved and folded into the design doc). Exploring and updating docs is fine.

## Owner decisions (locked)

| Topic | Decision |
|-------|----------|
| Audience | Personal tool first |
| Genre | House |
| Scale | ~30+ tracks → one set |
| Worst failure | Weak transitions |
| Transitions | Adaptive: ~8-bar EQ/cut when beats lock; ~32-bar smooth when needed |
| ML v1 | Unsupervised: **order + transition style only** |
| Deeper “how blend sounds” ML | Future feature |
| Input | User uploads files |
| Output | Single playable file (+ in-app play); no stems/markers/Serato export |
| Post-mix | Swap transition style + re-render |
| Hosting | Local PC first; Ubuntu hosting later |
| Track length | DJ-style excerpts with selected mix-in/out points |
| Coverage | Include all valid uploads; never drop poor musical fits |
| Later server | 4 GB RAM, third-generation Intel Core i3, 200+ GB storage |
| Access | Local PC only for now; loopback access |
| Backend | Python |
| UI flow | Upload → auto mix → swap weak transitions → play/download (confirmed) |

## Pipeline (agreed mental model)

1. **Analyze (DSP)** — BPM, beat grid, key, energy, phrase/structure hints  
2. **Unsupervised ML** — embeddings/clustering → order; pair difficulty → style (8-bar vs 32-bar, etc.)  
3. **Transition plan (rules + scores)** — bar-aligned recipes  
4. **Render (DSP)** — stretch, EQ/crossfade, one file  
5. **Editor** — swap style → re-render  

## Owner answers (2026-11-06)

1. DJ-style excerpts; exact duration remains a builder tuning decision.
2. Include all tracks. Report invalid inputs rather than silently omitting them.
3. Later server: 4 GB RAM, third-generation Intel Core i3, 200+ GB storage. Develop on the local PC first; PC resources are not specified.
4. Local PC only for now. Public hosting and authentication decisions are deferred.

No original owner questions remain open. The revised design is approved as of 2026-11-06.

## Suggested next steps for the taking-over agent

1. Read `docs/superpowers/specs/2026-10-30-ai-dj-set-design.md` and this file.  
2. Read `docs/superpowers/plans/2026-11-06-ai-dj-set-implementation.md`.
3. Run `powershell -ExecutionPolicy Bypass -File scripts/local.ps1` to check installed audio tools. Owner installed FFmpeg at `D:\Tools\ffmpeg-9.0.2-essentials_build`; the launcher keeps all application data in `D:\AI-DJ-data` because C: has limited free space.
4. Review the newest ML plan/audition below; distinguish unsupervised similarity from human-rated transition quality.
5. Implement bounded-memory full-set rendering/worker integration next, then the minimal local interface. Preserve waveform validation and every uploaded member.

## Current prototype (2026-11-06)

- **First owner preference recorded:** Owner explicitly said “in this case B” for the first Move → Say What A/B audition. Recorded winner `1ce8b05dba5ae6aa` (8s vocal fades) over `e80d704469d06426` (16s), preserving the song-pair-specific qualification. Retrained ranker and verified B ranks above A. Production dataset now has **1 comparison / 1 song pair**, so experimental weights exist but learned automatic selection remains disabled; no held-out accuracy is available yet. Do not generalize this into a universal preference for shorter fades. `feedback/first-audition.json` marked rated.

- **Preference-learning extension:** Owner explicitly requested learning/improvement from listening feedback. Added `planning/preferences.py`, `scripts/feedback.py`, and plan `2026-11-07-preference-learning.md`. Local SQLite stores immutable hashed render candidates plus append-only explicit ratings/preferences. Pairwise logistic ranking learns feature differences within the same ordered song pair; repeated votes are deduplicated and reversals update training direction. Ratings induce only within-pair comparisons; explicit comparisons take precedence. No prior chat remarks or synthetic labels have been entered as owner feedback.
- The first comparison fits experimental weights/rankings. Learned render selection is opt-in (`render_stem_pair --learned-settings`) and requires at least six usable comparisons across three source song pairs. JSON model state includes leave-one-song-pair-out validation, not randomly split mirrored examples. Readiness is a cold-start guard, not proven quality. Supported candidate knobs are vocal fade bars and instrumental profile; it does not synthesize audio or learn waveform curves. Existing full-set/library defaults are unchanged.
- **First real A/B session ready, unrated:** Move → Say What, same source cues/120 BPM/32-bar instrumental bed. A = 16-second vocal fades: `D:\AI-DJ-data\renders\stem-pair-a390cc7ba4b54ac6b1b4541de8ac6113.mp3`, candidate `e80d704469d06426`. B = 8-second vocal fades: `D:\AI-DJ-data\renders\stem-pair-32748fe18b064829ac30f33400cd27dd.mp3`, candidate `1ce8b05dba5ae6aa`. Both 128s, vocal treatment best heard 0:40–1:40. Registered in `D:\AI-DJ-data\feedback`, but production feedback count is ZERO; never claim the personal model has already learned from the owner. Next explicit A/B answer should be recorded with `scripts.feedback prefer WINNER LOSER`, which retrains immediately. Six new preference tests cover actual ranking changes, cold start, persistence, grouped validation and contradictory/duplicate votes; all 35 total tests pass. No commits/pushes.

- **Ten-track set completed (2026-11-07):** Owner requested a mix of ten AfroHouse songs. Added the local ten-track experiment `scripts/render_set.py` (fixed selected catalog, not yet a general queue/UI renderer). Uses ML order, prepares/corrects excerpts, separates locally, schedules independent incoming/outgoing vocal envelopes, shapes EQ, and adds blockwise into a disk-backed float master before static-headroom MP3 encoding.
- **Full mix:** `D:\AI-DJ-data\renders\set-10-130e567fbe894b4291982b457e8c0f4f.mp3`, **18:46.01**, with adjacent `.txt` timestamped tracklist and `.json` report. All 10 selected tracks included. Nine joins validated on original prepared audio and again on separated instrumentals: 3 long 32-bar joins and 6 eight-bar joins; no unbeatmatched fallback remains. One edge-of-file cue needed a small positive PCM delay (modulo a beat), masked by the outgoing track. Full decode peak 0.799, no invalid samples/clipping/unexpected silent windows. All 29 existing tests pass. Listening acceptance pending.
- Local GPU acceleration was validated against CPU on real model inputs (relative RMS difference 7.8e-7). Optional DirectML runtime `onnxruntime-directml==1.24.4` installed in `D:\AI-DJ-data\separation\gpu-venv`, sharing CPU dependency packages through a `.pth` file. `mdx.py` uses DirectML only when available, with sequential execution/memory patterns disabled; standard CPU environment stays unchanged. The ten-track script prefers the optional GPU worker and otherwise uses CPU. Work/checkpoints are under `D:\AI-DJ-data\tmp\set-10-130e567fbe894b4291982b457e8c0f4f`; cached model/stems remain on D:. No commits or pushes.

- **ML implementation (completed 2026-11-07):** Owner accepted the long reference and requested ML. Implemented `backend/app/planning/{learning,order,rhythm,excerpts,planner}.py` and `scripts/plan_mix.py`. Version 3 DSP analysis includes MFCC and spectral statistics. Local kick scans produce regional tempo/cue evidence (e.g. Yamore corrected from the old ~162 BPM tracker estimate to measured 120 BPM); this is not semantic phrase/downbeat detection.
- Learned model fits 45 features with RobustScaler/PCA/KMeans on distinct content hashes, then orders every entry with learned distance and tempo/energy constraints. Gaussian mixture pair groups suggest long/short recipes; declared physical-difficulty mapping and DSP guards determine feasible blends. It does not learn human listening quality or generate blend curves. Duplicates remain separate entries without reweighting model training. Single/degenerate/missing-feature cases are explicit; invalid input batches do not produce reduced playlists.
- Ran on all 16 audio files in `D:\G1-Drive\Dj\AfroHouse` (non-audio PDF excluded). Four track clusters; pair mixture converged. ML order differs from the deterministic baseline. Plan has 3 long, 11 short, and 1 flagged boundary handoff (BODY → set me free; insufficient regional pulse support). All 16 entries retained, source/overlap bounds valid, stretch limited to 6%, SQLite round-trip verified.
- **Plan and readable summary:** `D:\AI-DJ-data\plans\mix-f465a206f55445d1b62997a9159edb47.json` and adjacent `.md`. **Model:** `D:\AI-DJ-data\models\library-8ad2dd20eb6a878dee1436e898981cc1e3d7d563f67e542994137402ba475dd4.json`. Models are readable JSON state, not pickles. Full-set audio has not been rendered.
- **Automatic audition:** ML-selected join 7, Ma Tnsani → Si Ai. Output `D:\AI-DJ-data\renders\stem-pair-f7696b1faa7d44d1ac51e1b51f749ec2.mp3`, 76.60 seconds; instrumental overlap starts at 7.66s and lasts 61.28s. Planned common run tempo is preserved by the new optional `target_bpm` argument to pair rendering. Four separated-instrument timing windows passed; encoded peak 0.815 and no silent windows. Original sources/cues come from the plan. Vocal/lyric placement remains heuristic; owner listening pending.
- CLI: `powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.plan_mix "D:\G1-Drive\Dj\AfroHouse" --compare --preview-best`. `--preview-join N` selects a one-based join. Plans/models/summaries are on D: and core plans persist to SQLite. Style edits preserve order/revision, reject invalid geometry and require refreshed validation before converting flagged boundary joins to beatmatching. All 29 tests pass, including learned model state, deterministic ordering, duplicate/missing/outlier handling, bounds, persistence, bad inputs and audio regressions. No new commits or pushes.

- **Latest request/result:** Owner requested a long, patient beat transition for Move → Say What. Added `--blend-profile long_groove`: upper percussion layers throughout the overlap, instrumental mids trade over up to 16 bars, and bass trades over four beats. Original profile remains the default. Long overlaps now check pulse phase/drift in consecutive 16-second windows, including the separated instrumentals, so early alignment cannot hide a late beat slip. Eighteen tests checked successfully, including a new synthetic late-slip regression and a spectral check of the extended midrange blend.
- **Newest long preview:** `D:\AI-DJ-data\renders\stem-pair-a390cc7ba4b54ac6b1b4541de8ac6113.mp3`, 128 seconds, 120 BPM. Move source 32.2–128.2s into Say What 0.16–96.16s. Overlap 32–96s: 32 bars/64 seconds. Instrumental midrange handoff lasts 32 seconds; bass swap near 64s over two seconds. Vocal fades/EQ use eight bars/16 seconds: outgoing 41.38–57.38s, incoming 80.65–96.65s. The full overlap passed four local timing windows before/after separation; encoded preview has no clipping or silent windows. Source reconstruction within 3e-8. Owner listening pending; no new commits or pushes.

- **Newest two-song listening preview:** owner requested another pair from the same AfroHouse folder. Selected `I Move (Lyrics).mp3` → `F Say What.mp3`, both stable near 120 BPM. Output `D:\AI-DJ-data\renders\stem-pair-d035fc1d5c2341adaaa55b31ef371474.mp3`, 80 seconds. Source cues Move 48.20–96.20s and Say What 16.16–64.16s; instrumental overlap 32–48s. Long vocal fade-out 33.38–41.38s, incoming vocal fade/EQ opening 44–52s. Outgoing fade ends in a detected low-energy gap; incoming has no suitable detected entry gap, so uses an explicitly reported gradual fallback. Actual local ML separation, reconstructed stems and full encoded output validated; owner listening pending. No product code changed for this pair.

- **Newest feedback/revision:** Owner found the stem vocal fade-out much too fast and requested vocal fade-in/EQ-in. Replaced the 4-beat (~2s) outgoing fade and sub-second incoming restoration with configurable 2/4/8-bar fades (default 4 bars, ~7.9s). Outgoing vocal uses a gradual quarter-sine gain curve and closing high band; incoming vocal builds from its detected entry with a half-sine gain curve and opening high band above 1800 Hz. The instrumental bed, source cues and beat alignment are unchanged. `--vocal-fade-bars` controls this in `scripts/render_stem_pair.py`.
- **Latest preview:** `D:\AI-DJ-data\renders\stem-pair-8c407a83f6704c9eb87617121d2b65fd.mp3`, duration 79.01s. Sauti vocal fades 29.63–37.53s; Famax vocal builds/brightens 38.96–46.86s. Fully decoded peak 0.820, no silent windows, separated-instrumental beat offset under 1 ms and measured drift under 2 ms. All 17 tests pass, including added assertions for gradual gain ramps, incoming high/low vocal spectral change, and sustained instrumental bass during the fade. Owner listening pending; no new commits.

- **Latest owner extension:** Rejected the outro/intro lead handoff for killing energy; explicitly requested mid-song mixing with the second vocal removed initially, fading the first vocal and then introducing the second. Internal pretrained local stem separation is now authorized (AGENTS/design updated); no learned blend curves, training, or public stem export.
- Optional separation environment is `D:\AI-DJ-data\separation\venv` (Python 3.12); main Python 3.14 application environment is unchanged. `requirements-separation.txt` pins the small CPU ONNX runtime dependencies. `scripts/setup-separation.ps1` reproduces setup and downloads the public `UVR-MDX-NET-Inst_HQ_3.onnx` model plus UVR metadata onto D:. User audio stays local.
- `backend/app/audio/mdx.py` runs the pretrained instrumental model on one centered-STFT stereo chunk at a time, with 50% overlap. The complementary vocal is source minus instrumental, preserving reconstruction and timing. Float stems are cached under `D:\AI-DJ-data\separation\stems` by source/model/version hash. Model artifacts and audio are outside the repository.
- `scripts/render_stem_pair.py` takes a validated pair JSON report, preserves its source cues and tempo, checks separated-instrumental beats, and blends instrumentals independently from vocals. Vocal gap timing uses energy in the separated vocal; no semantic lyric/phrase detection. Fallback outgoing vocal fade is explicit when there is no suitable gap. Voices receive the same crossover phase response as the instrumental bed to preserve consistent reconstruction outside the handoff.
- **Newest preview:** `D:\AI-DJ-data\renders\stem-pair-818b4c5e26364ee187d1e02d55393135.mp3` (79.01s), using the earlier main-song Sauti/Famax cues from `pair-a21d69bda3d547c8a5dbfc353cda47e2.json`. Instrumental overlap 31.61–47.41s; Sauti vocal fades 35.56–37.53s; Famax vocal gain restores 38.63–38.93s before a detected entry. Bass swap near 39.51s. The groove stays underneath; separation bleed/artifacts remain possible. Owner listening pending.
- All 17 tests pass, including model STFT packing/round-trip, gap scheduling, separate vocal gain timing, instrumental continuity during the vocal gap, and post-EOF tail. Actual separated stems reconstruct their inputs within 3e-8. No new commits or pushes.

- Real-pair listening: owner rejected the short fallback and then reported doubled beats in the initial BPM-matched smooth preview. BPM matching alone did not align pulse phase.
- Owner also rejected the circular-mean pulse alignment preview: its small reported error was misleading because nearby syncopations suppressed kick events and biased phase. That metric did not establish audible beatmatching.
- Smooth renders now retain attacks 80 ms apart, fit a narrow recurring attack train in 70–130 Hz after stretching, and require at least 70% beat coverage and attack error p90 below 15 ms. Reports include matched event timestamps. Cue correction still rejects drift over 25 ms or residual phase offset over 12 ms. This remains a heuristic, not a downbeat/phrase detector. Twelve tests pass, including louder syncopations near kicks, deliberate phase offset, and drift detection.
- Latest local listening preview: `D:\AI-DJ-data\renders\pair-b01cece390a8426f98894a71882fe882.mp3`. Transition at 14.95–29.89 seconds. The incoming cue moved about 163 ms earlier in output time relative to the rejected preview, delaying its attacks to the outgoing kick train. First measured corresponding attacks are 0.6625/0.6645 seconds into overlap. Owner acceptance pending. Local source cue/tempo settings are in the adjacent JSON report. Changes are not committed.
- Owner accepted beat matching in that preview but said the musical result was far from a true DJ transition. Implemented `eq_swap` for matched `auto` renders (explicit `smooth` retains the comparison): 180/1800 Hz crossover, upper-band overlap, eight-beat midrange trade, and half-beat bass swap anchored to the outgoing pulse grid. Overlap RMS is conservatively matched; a latency-compensated safety limiter reserves headroom. This is still a pair prototype; automatic downbeats/phrases and vocal conflict handling are unfinished.
- New EQ comparison: `D:\AI-DJ-data\renders\pair-879f4ee96b3241569eebdbb581615b8c.mp3`, transition 14.95–29.89 seconds, bass swap 22.62 seconds. Incoming source starts near 0.054 seconds to retain its first kick rather than starting one beat into the intro. Phrase alignment is explicitly unverified. Thirteen tests pass, including decoded spectral checks for bass ownership, shorter midrange overlap, percussion coexistence, duration, and headroom; owner listening is pending. See `docs/testing/transition-evaluation.md`.
- Owner found that preview much cleaner. Subsequent Sauti → Famax preview was beatmatched but musically rejected: it interrupted Sauti's rise and became entirely silent after roughly 32 seconds despite a 47-second file duration. Decode and duration checks had missed this bug.
- The mixer now resets timestamps before its final fade. Removed the dynamic limiter in favor of an unclipped float-PCM intermediate, blockwise peak scan, and fixed headroom gain. A decoded incoming-tail check compares against the prepared source and rejects unexpected disappearance after outgoing EOF. Regression checks now measure actual bass/mid energy after outgoing EOF; all 13 tests pass. The original attribution to the limiter alone was incomplete: tail regression also required the timeline reset.
- Latest Sauti → Famax revision: `D:\AI-DJ-data\renders\pair-a21d69bda3d547c8a5dbfc353cda47e2.mp3`, duration 79.01 seconds, blend 31.61–47.41 seconds, bass swap 40.00 seconds. Manually selected established grooves using energy profiles: Sauti source 94.52–141.73 seconds, Famax source about 111.52–159.12 seconds. Sauti's main groove plays for 16 bars before the blend, avoiding the previously interrupted rise. Fully decoded output has peak 0.787 and remains audible through its incoming tail. Cue selection is still manual; this does not establish automatic phrase planning. Owner listening pending. No new commits.
- Owner then rejected the main-groove revision because vocal lines overlapped and were interrupted. Added explicit `lead_handoff` (default `auto` still uses `eq_swap`): incoming 180–4500 Hz lead stays muted until outgoing EOF, outgoing lead fades only over its final beat, and incoming lead fades in afterward. Incoming bass changes near the end; upper percussion may enter earlier. This is band scheduling, not vocal recognition or stem isolation. Outgoing solo/body RMS is used to avoid matching incoming level to an already quiet outro. Nearest-beat rounding also fixes the prior one-beat bias when measured phase wraps close to one full period.
- Latest vocal-overlap comparison: `D:\AI-DJ-data\renders\pair-722ae79ceca8444fbb43d1787c733e90.mp3`, 79.01 seconds. Sauti source 299.11–346.32 (outro) into Famax source 16.31–63.91 (intro). Overlap 31.61–47.41 seconds; bass swap 46.91; incoming lead starts 47.41 after outgoing ends. These sections have much lower centered lead-band activity than the rejected main grooves, but absence of singing and phrase ends are not automatically verified. All 13 tests pass, now including decoded lead-band non-overlap before/after EOF. Full decode peak 0.788; incoming tail stays audible. Owner listening pending. No new commits.

- `scripts/render_pair.py`: analyze two paths, choose/override source cue points and BPM, render stereo MP3 plus a JSON report. Use via `scripts/local.ps1 -m scripts.render_pair ...`.
- `scripts/demo_pair.py`: reproducible synthetic 120/124 BPM stereo demo. Last verified output: `D:\AI-DJ-data\renders\pair-725f05f6d16548afbab7eb7750b167ab.mp3`, duration 28.260s, overlap 15.740s.
- Audio dependencies installed in the project virtual environment; `requirements-audio.txt` snapshots the tested versions. Downloads/temp/cache use D: through the launcher/install command; the virtual environment itself remains on C:.
- Tempo is refined from fitted beat times to avoid frame-lag quantization. Confidence is a heuristic, not calibrated probability. Half/double-time alternatives remain explicit.
- Analysis caches content/version/config on disk, currently independent of the SQLite analysis table; worker integration remains future work.
- Phrase starts are tentative; named key detection is deferred in favor of chroma features. Pair EQ/bass-swap is now implemented; no full-set ordering, queue execution, or UI yet.
- A 6% maximum change per track and low-confidence fallback preserve all inputs rather than forcing unsuitable beatmatching. `--style smooth` fails clearly when infeasible.
- Follow README for real-track commands. Next: listen to owner-selected house pairs, then implement milestone 3 planning and milestone 4 recipes. Do not infer musical quality from synthetic test success.

## Stack defaults (builder may refine)

- FastAPI backend, Redis/RQ or Celery (or similar) for jobs  
- Simple web UI (React or server-rendered — builder choice)  
- Analysis: Essentia / librosa / similar  
- Time-stretch: Rubber Band / similar  
- Files on disk; async jobs with progress  

## Notes / landmines

- Initialized a repository in this project folder on 2026-11-06 at the owner's request to push to a new GitHub repository. Use the project repository; do not modify any parent repository. Owner explicitly requires no AI commit attribution or co-author trailers.
- `.superpowers/` holds local brainstorm HTML; keep gitignored.  
- Transition quality is the product; order/energy matter less than joins that don’t flinch.
