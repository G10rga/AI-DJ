# Shared transition audio and analysis foundation

Milestone 1 supplies reusable preparation and evidence for the experimental
planner. Generate/Compare activation is a later milestone. No default, model
promotion, listening vote or training label is changed by analysis.

## Application interfaces

`backend.app.timeline_analysis.analyze_registered_pair(workflow, track_ids)`
accepts any two catalog IDs in the supplied order. It checks original audio
hashes, uses the existing isolated Beat This/MERT timeline worker and MDX
separator worker, and returns pinned timelines plus distinct evidence layers.
There are no catalog filenames, fixed cues or research-script calls in this
service. The caller must run it inside its serialized heavy-job worker.

For individual files:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.analyze_timeline "path/to/song.mp3" --foundation --with-vocals
```

Omitting `--with-vocals` leaves vocal/quiet evidence unknown. Omitting
`--foundation` retains the old analysis configuration. Existing API callers
continue to use that configuration.

`backend.app.audio.float_prepare.prepare_float_excerpt` takes a source path,
fresh output path, source time at output zero, output duration and source/target
tempos. It decodes/stretches one continuous stereo float stream with up to eight
seconds of real context on each side, crops in output frames, and retains peaks
above full scale. Source bounds are checked; a short decode fails. Pre-file
silence requires an explicit `inaudible_before` interval and never repairs
missing audible audio. Processing streams blocks rather than holding full sets
in memory. `preparation_gain` chooses one gain from measured LUFS/true peak;
`apply_constant_gain` applies it in float before final encoding. Preparation
reports record source/result hashes, tempo mapping, context and padding frames.

## Evidence and uncertainty

The `transition-foundation-1` analysis profile stores `transition-evidence-1`
alongside the existing timeline format. Its cache identity includes original
audio SHA256, model metadata/files, runtime packages, adapter/evidence versions,
analysis implementation hashes, FFmpeg build and analysis configuration.

The worker retains raw chunk beat/downbeat observations with absolute source
offsets. It merges markers before deriving source-wide observed bar indices and
multi-beat local tempo fits. Missing beats, unsupported meter/tempo, excessive
drift and noncoincident downbeats cannot supply regular eight-bar spans. These
are local timing candidates, not proof of semantic phrases. Independent checks
on actual stretched/encoded sources remain required by the later planner.

Vocal screening uses stereo float context and verified float MDX stems. The
separate `verified-mdx-cache-1` namespace includes the complete model parameters,
adapter/cache versions and separator packages in its identity. It validates model
and stem hashes, format and source reconstruction. Corrupt cached stems fail
without rewriting the evidence. Historical separator caches remain untouched.

Half-second bins store actual start/end coverage, vocal RMS, master RMS, their
ratio, observed/unknown state, activity and chunk reference. A short final bin
retains its real duration. Near-zero master energy leaves the ratio unknown.
Every chunk records original/context/stem hashes, original offset, core/context
bounds, frame count, sample rate, model/runtime configuration and reconstruction
error. This provenance is validated before persisting new-profile timelines.

`interval_activity(rows, start, end)` requires coverage of the entire query:
missing/gapped/overlapping/invalid/unknown evidence returns `unknown`. Low
activity yields `quieter_candidate`; activity anywhere yields `active`.
`quieter_passages` merges only adjacent observed low-ratio bins. A future quiet
bar never establishes that an ongoing line has ended. MDX leakage remains a
limitation; none of these fields claims lyric/phrase recognition.

MERT novelty/energy structural changes and tentative phrase markers are separate
candidate layers, with null confidence. They are not promoted to human labels.

## History and corrections

New profiles create distinct immutable prediction IDs. Old predictions and
append-only human corrections stay attached to their exact IDs. Caching new
experimental analysis does not change the default timeline selected by the
existing editor/planner. Explicit profile selection is available through
`TimelineStore.tracks(profile=...)` and `for_content(..., profile=...)`.

`foundation_evidence(record)` derives bar/phrase views from the record's effective
markers, preserving the exact timeline ID, correction revision, effective hash
and model configuration. It does not copy corrections across model versions or
overwrite cached predictions. Legacy RMS-only activity cannot establish quiet
coverage in the new evidence adapter.

## Validation on 2026-11-12

Real registered-pair validation used **Edge of Desire** (134.91s) and **It's Not
Right But It's Okay** (152.32s), without research cue constants. Beat This/MERT/MDX
produced respectively 273/323 beats, 77/84 downbeats, 46/70 supported eight-bar
spans, 27/31 embeddings, 270/305 relative-vocal bins and 5/6 verified vocal chunks.
The 25/17 quieter passages and 4/7 structural changes are model candidates only.

Report:
`D:/AI-DJ-data/analysis/foundation-validation-b97494d6c37943128dfd291818287c60/report.json`.
Repeated calls returned identical pinned evidence. All three pre-existing
timeline predictions remained byte-for-byte unchanged. There were no saved
timeline corrections in that owner database; preservation and profile-selection
behavior with human revisions were separately tested in isolated fixtures.

The refactored At Night/Stupidisco regression runner produced a fresh isolated
revision at
`D:/AI-DJ-data/experiments/open-dj/auditions/vocal-handoff-84ddaf7fbc0c443897a6ec65b22b082e/`.
Independent prepared-source checks matched 27/27 beats, 7/7 downbeats and six
complete regular bars per source. Encoded timing/format/peak/dropout checks
passed. Reviewed reference artifacts and the rejected effects recipe remain
unchanged. This is technical regression evidence; listening acceptance is null.

Reproduce registered-pair validation with any two catalog IDs:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.validate_foundation OUTGOING_CATALOG_ID INCOMING_CATALOG_ID
```

This command creates fresh verification reports, checks cache reuse and checks
existing prediction/correction rows for mutation. It never saves test votes.

Final regression command: `powershell -ExecutionPolicy Bypass -File
scripts/local.ps1 -m unittest discover -v`. Result: 177 tests ran, 171 passed,
six skipped because they require the isolated PyTorch/Pedalboard test runtimes.
No training or native-effects implementation changed. The new foundation's nine
tests also passed after the final registered-source hash guard was added.
Changed Python modules compile; `git diff --check` passes. Real float preparation
retained native/stretched peaks 1.429/1.058 before fixed gain staging, and the
regression MP3 measured -20.00 LUFS / -4.46 dBTP. The reviewed audio and all four
saved screening-evidence hashes were rechecked against the old report; the
rejected effects marker remains present.
