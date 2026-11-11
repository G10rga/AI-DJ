# Continuous vocal handoff

Owner approved protecting the outgoing vocal and gradually introducing the next
track after rejecting the loop/hard-entry experiment. One new At Night →
Stupidisco example is ready, with listening acceptance pending:

[Play the continuous handoff](http://127.0.0.1:8007/vocal-handoff-fdc44c762ab34ca8990521d1b53addc0/handoff.mp3).

- 60 seconds, stereo. Listen around 20–40 seconds.
- Incoming intro begins quietly near 22.38s and rises over eight bars (~15.24s).
- Outgoing stays at its full fixed preparation gain until 30s, allowing the
  preceding line and tail to pass. Incoming has reached only 25% gain then.
- Outgoing fades during the subsequent sustained quieter passage. Incoming
  rises from 25% to full gain, finishing the handoff near 37.62s.
- Both source streams play continuously; no loop, jump to a future bar, echo
  or millisecond release is applied.

The outgoing source window moved later, with its fade around 143.75–151.31s of
the original. The incoming source uses its opening around 3.92–19.28s during the
overlap, rather than entering in the vocal-heavy middle. The existing full-track
beat/downbeat predictions determine supported bar spans and tempo. Independent
analysis of the stretched preparations and encoded mix validates timing again.

The existing MDX model screened original context, covering outgoing 54s–end and
incoming 0–120s. It found a sustained lower-vocal region throughout the outgoing
fade and lower-vocal incoming intro throughout the overlap. Outgoing gain remains
unchanged until more than two seconds after the last strong estimated vocal
activity. Activity is derived from actual stem samples with source-time offsets,
not trusted from a manually edited cue or a quiet destination bar. It is **not
semantic phrase transcription** and does not guarantee musical quality.

All preparation remains float32 stereo with real stretching context. Incoming
audio before the original file begins is explicitly padded while its gain is
zero. Source audio after that point is continuous. Final audio passes loudness,
peak, finite, dropout, stereo/duration, HTTP hash, gain-continuity and independent
beat/bar checks. Rejected effects and earlier feedback are preserved. No app
defaults, models or owner votes changed.

Implementation: `backend/app/research/vocal_handoff.py` and
`scripts/render_vocal_handoff.py`. Early intro selection is explicitly allowed in
`stable_spans`; existing callers retain their previous context requirement.

Artifacts under `D:/AI-DJ-data/experiments/open-dj/alignment/phrase-handoff-1/`
retain screening contexts/manifests, source offsets, activity traces and each
preparation attempt. The audition's `report.json` records exact hashes, source
cue intervals, control timing, vocal evidence, uncertainty and technical results.
The effects recipe v1 remains disabled.

To render a fresh isolated revision using the saved screening evidence:

```powershell
cd C:\Users\user\Documents\GitHub\AI-DJ
& D:\AI-DJ-data\timeline\venv\Scripts\python.exe -m scripts.render_vocal_handoff
```

Screening is bounded to the separator's 180-second excerpt limit. Missing,
uncovered or conflicting activity evidence blocks rendering rather than being
treated as silence. A previous rejected vocal-cut interval also fails this gate.
