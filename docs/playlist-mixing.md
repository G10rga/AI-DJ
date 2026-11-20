# Automatic playlist mixing — implementation contract

Approved by the implementation request on 2026-11-20. This supersedes excerpt
defaults for new `playlist-1` projects only. Existing pipelines and owner reviews
remain unchanged. No owner listening judgments may be inferred from tests.

Implementation order: versioned evidence and monotonic tempo maps; joint candidate
search; revision-pinned persistence and leased jobs; Rubber Band offline rendering
and independent timing gates; playlist and transition editor; integration checks.

Full songs are the default. Search final 25% / first 20%, then 40% / 40%, using
2/4/8/16/32 bars and blend, bass-swap, filter recipes. Vocal prominence is a cost,
not an eligibility gate. Explicit vocal endings are constraints. Each middle song
has one continuous source interval and one continuous warp with native timing
between joins. Export requires resolved rhythm evidence. Keep up to three ranked
attempts per join with the actual failure reasons.

Projects use optimistic revisions; plans and artifacts are immutable and pinned.
Only the current revision can publish. Previous prepared audio remains playable.
Analysis, time warps, and automation rendering use separate cache identities.

UI: established black/Inter/lime AI DJ language, playlist in the main workspace,
library alongside it, transition waveforms and curves below. The primary action
is Mix. Reordering is explicit and preserves the first entry. Keyboard alternatives
accompany drag controls. Unknown evidence is visibly unknown.

Acceptance: freeze development/evaluation source hashes before scoring calibration;
technical tests are not musical acceptance. Target 16/20 fresh house pairs, all
four joins in a five-song set, and a 30-song export. Scores remain development
heuristics until the freeze and actual listening records exist.

## Use the playlist studio

Run `python run.py` on the local Windows checkout, or open
`http://127.0.0.1:8005/` if the app is already running. Use
`scripts/setup-playlist.ps1` to install the pinned Rubber Band utility and
rebuild the shared DSP. Timeline and MDX setup still use the existing model
installers. Set `AI_DJ_RUBBERBAND` to use a separately installed executable.

Add songs from the library, drag them into order, then press Mix. Smart Reorder
proposes a new order for you to apply and keeps the first song. Each transition
opens its source cuemarks, presets, timed automation and audition controls.
Curve changes affect the prepared preview immediately. Save and prepare queues
the revision for validation. The previous audition and export remain available
while work is pending. A current revision with unresolved timing cannot be
exported. Saved mixes and Compare remain available from the navigation.

## Verification records

The [benchmark split](playlist-benchmark.json) pins source hashes for two
development pairs, the five-song integration set, and 20 held-out pairs. The
scoring weights are development heuristics. Held-out usability and the
five-song listening verdict require actual owner listening.

- The 5-song and 30-song synthetic sets produced stereo WAV and MP3 at about
  -14 LUFS. The 30-song set ran 545 seconds and passed encoding timing across
  29 joins. Synthetic pulse attacks landed within 3 ms of the planned ramp.
- At Night / Stupidisco passed independent original and prepared rhythm checks
  and produced a 414-second set. Browser verification covered prepared playback,
  live curve editing, seeking, 206 range playback, and layouts at 1440, 768,
  and 390 pixels. A cached gain change reached the output analyser in 11.2ms
  in one local Chromium run. The MP3 measured -14.00 LUFS and -3.62 dBTP.
- Let's Groove / Push The Feeling On produced three distinct cue attempts.
  Independent bar evidence remained unresolved and blocked export. The old
  engine stopped earlier on its quiet-vocal requirement. Both are technical
  results for this pair. The editable audition and the three timing reports
  are retained in the development project.
- The real five-song development run prepared all five tracks and tested three
  candidates on each of its four joins. Independent bar evidence remained
  uncertain on all four final placements. The four contextual previews are
  available for correction, and the worker withheld the set export.
- Reproduce the matched simple crossfade with
  `python -m scripts.playlist_benchmark PROJECT_ID JOB_ID OUTPUT_DIRECTORY`
  against a validated two-song job. It uses the exact same cues, warp, and
  listening window. The development pair differed by 0.01 LU. The generated
  files and report are under
  `D:/AI-DJ-data/validation/playlist-development/at-night-ab`.
