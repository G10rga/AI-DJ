# Context-aware cues, recipes and auditions

This implements step 3 of the saved workflow. The planner uses effective musical
timelines, including corrections, to propose cue anchors and 32/16/8-bar blends
or a short phrase cut. It is a deterministic contextual baseline; no new owner
labels, contextual-network training or automatic model promotion are involved.

## Compare an ordered pair

The completed set and its recent matched previews are playable at
`http://127.0.0.1:8000/mixes` (also the app's home page). Select a mix, play or
download it, jump through the timestamped tracklist, or use **Play handoff** on a
preview. Only one player runs at a time. The source timeline editor is at
`http://127.0.0.1:8000/timelines`. Pair generation still uses the CLI below.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.suggest_transitions "D:\G1-Drive\Dj\AfroHouse\I Move (Lyrics).mp3" "D:\G1-Drive\Dj\AfroHouse\F Say What.mp3"
```

This generates up to twelve proposals, validates actual prepared audio, then
renders up to two distinct successful alternatives. `--render-count 0` performs
proposal generation and waveform validation without rendering auditions.
`--analyze-missing` explicitly runs the isolated timeline worker with vocals for
missing analyses; otherwise a missing timeline is reported as an error.

JSON and Markdown reports go to `D:\AI-DJ-data\plans\context-pair-*.{json,md}`.
Matched MP3s and their JSON reports go to `renders\matched-audition-*` on D:.
Previews have the same duration and handoff timestamp, even when their source
cues or recipes differ. For normal-length songs they are 128 seconds with the
handoff centered at 64 seconds. Short songs use less common context or reject
recipes that cannot fit. Compare around that timestamp, then listen through.

## Plan or render a set

```powershell
# Save an ordered plan with contextual adjustments and explicit fallback reasons.
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.plan_mix "D:\G1-Drive\Dj\AfroHouse" --contextual

# Render through the shared set service.
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.render_set "D:\G1-Drive\Dj\AfroHouse" --contextual
```

These paths preserve the existing ordering model and every input entry. Missing
timelines, incompatible tempo runs and candidates that fail waveform/set-geometry
checks retain the conservative join with a reported reason. Contextual choices
cannot consume a middle track's incoming/outgoing regions. A selected recipe that
fails final rendering is an error; it is not silently replaced by a different
recipe. The last playable render remains available. Without `--contextual`, the
existing conservative planner is retained.

## Decision evidence and guardrails

- Candidate anchors come from corrected/tentative phrase markers and nearby
  section-change evidence on the downbeat grid; lengths vary across recipes.
- Local energy/trend, bass, chroma, frozen MERT context, transient-density proxy,
  rhythmic stability and vocal activity contribute to screening or scoring.
  Missing embedding/vocal evidence remains unknown.
- Rising energy around the handoff, including the earlier midrange fade of a
  long blend, blocks proposals that would interrupt that rise. A major incoming
  energy collapse is rejected.
- Cuts require corrected phrase markers or phrase-plus-section evidence, regular
  local bars and known vocal gaps at both anchors. An energy spike alone is
  insufficient. They exchange the complete source in 40ms, centered at the seam.
- Blends schedule non-overlapping vocal gain windows independently from the
  instrumental bass/mid/percussion exchange. 16-bar blends have an explicit
  controlled recipe; they are not relabeled 8-bar renders.
- Source hashes, bounds, six-percent stretch limits and local bar stability are
  checked before proposing/using a plan. Independent waveform tests reject
  drift, unstable pulses and large phase corrections. Incoming phase corrections
  are capped at 80ms and one-fifth of a beat, and retained in validation records.
- Auditions recheck separated instrumental timing, decoded finite samples,
  duration, stereo, clipping and unexpected silence/tails. Full-set rendering now
  converts float separator stems into PCM16 for pulse measurements; the original
  float stems still feed the mixer.
- A/B files are matched by measured integrated LUFS using a shared target no
  louder than -20 LUFS, with true-peak headroom. Matched files are new artifacts;
  original renders and reports remain preserved.

SQLite schema 4 adds immutable candidate snapshots and append-only validation,
rejection and audition events. Snapshots include timeline/model identities,
correction revisions, source hashes, context vectors and requested settings.
Applied cue corrections and technical evidence are recorded separately. None of
these events are listening ratings. Existing preference feedback is unchanged.

## Real verification

Move → Say What generated twelve proposals from twenty screened choices; eleven
passed prepared-audio waveform validation. The selected alternatives were:

- Controlled 16-bar blend, source anchors 128.18s / 74.14s.
- Eight-bar EQ handoff, source anchors 144.18s / 74.14s.

Both auditions are 128s, centered at 64s, measured at approximately -20.00 LUFS.
The first verified matched pair had true peaks -4.10/-3.76 dBFS. No musical
acceptance or owner preference is inferred from those technical checks.

An actual contextual full-set plan was saved and rendered as
`D:\AI-DJ-data\renders\set-476f9c744fbc42c6aba1f716c1cffe81.mp3` (197.998s),
with both songs included and a controlled 16-bar join. Its report and timestamped
tracklist sit beside the audio. The original single owner comparison remains
the only recorded owner comparison.

All four recipes are exercised using generated stereo audio and an injected
separator in automated tests. Real pretrained separation was also run for the
two-song auditions and contextual full set. Listening acceptance, reference-mix
annotations, a trained contextual ranker, and browser A/B feedback remain later
work. This step does not make those components complete.
