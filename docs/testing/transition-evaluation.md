# Real-pair transition work

Owner feedback: beat timing is now acceptable, but the full-band crossfade does
not sound like a DJ transition. Keep the accepted timing as the comparison baseline.

Next implementation: an explicit `eq_swap` recipe, with separate bass, midrange,
and percussion bands. Keep outgoing bass until a beat-aligned handoff, introduce
incoming upper frequencies across the overlap, and exchange mids over a shorter
window to reduce competing musical material. Match overlap RMS conservatively,
reserve peak headroom, and validate the encoded output. Preserve `smooth` for A/B.

Use the same cues initially so the recipe can be judged separately. An 8-bar
duration and beat-aligned handoff do not prove musical phrase alignment. Automatic
downbeats, phrase selection, harmonic compatibility, and vocal conflict detection
remain unfinished; do not describe this recipe as a finished automatic DJ engine.

Validate with decoded spectral fixtures: the outgoing bass must dominate before
the handoff and incoming bass after it; mids must not overlap for the whole blend;
duration, stereo, headroom, and accepted pulse timing must remain intact. Owner
listening determines whether the musical result improves. No commits without request.

## Sauti → Famax feedback

The first EQ preview passed beat checks but interrupted an energy rise and had an
entirely silent tail after the outgoing excerpt ended. Duration and whole-file
peak checks did not detect that failure. Tail energy must be checked against the
incoming source, and source energy changes must inform cue selection.

Fixed mixer timeline reset before final fades, replaced the limiter with a
float-PCM peak scan and constant headroom gain, and added decoded incoming-tail
validation plus spectral tail assertions. All 13 tests pass. The revised 79-second
comparison uses later main-groove sections, plays Sauti alone for 16 bars before
the overlap, and keeps Famax audible afterward. Automatic structural planning
remains unfinished; these revised cues were selected from measured source profiles.

## Vocal overlap feedback and next change

Owner rejected the main-groove revision because one vocal interrupted the other.
Do not equate quiet mids with proven absence of singing. Keep source voices intact
by choosing a sparse outro/intro pair and adding an explicit `lead_handoff` recipe:
incoming bass/percussion can enter during the overlap, but its 180–4500 Hz lead
band stays muted until the outgoing source ends. The outgoing lead is retained
until its final beat, then the incoming lead fades in after it. This is band-based
scheduling, not stem separation or automatic vocal detection. Use sparse sections
because voices can extend beyond these bands. Keep `eq_swap` for comparison.

Validate decoded lead-frequency fixtures before, during, and after outgoing EOF;
both lead bands must not play together. Continue existing beat, tail, duration,
energy and peak checks. Musical phrase and vocal-end annotations remain unverified.

## Long groove transition request

Owner requested a long, smooth beat transition for Move → Say What. Use a 32-bar
overlap (64 seconds at 120 BPM), a 16-bar instrumental midrange trade, four-beat
bass exchange, and eight-bar vocal fades/EQ. Preserve percussion throughout.
Validate consecutive local beat windows rather than extrapolating solely from
the first 30 seconds. A synthetic late-phase-slip regression verifies that an
otherwise good opening cannot hide a later timing discontinuity.
