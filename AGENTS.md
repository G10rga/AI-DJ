# Agent instructions — ai-dj-set

## Read first

1. [HANDOFF.md](HANDOFF.md) — current state and open questions  
2. [docs/superpowers/specs/2026-10-30-ai-dj-set-design.md](docs/superpowers/specs/2026-10-30-ai-dj-set-design.md) — design  

## Rules

- Prefer chat over HTML mockup companions unless the owner asks for visuals.  
- **No product code** until design is approved and open questions in HANDOFF are answered and written into the design.  
- After approval: write an implementation plan before large builds.  
- Optimize for **transition quality** on house music; ML in v1 is order + transition style only.  
- Deeper “learned blend sound” ML is explicitly future — do not sneak it into v1.  
- Owner authorized an optional pretrained local vocal/instrumental separator on 2026-11-06 to mix mid-song with independent vocal fades. This is an explicit exception for source separation, not permission to train or generate learned blend curves. See `docs/superpowers/plans/2026-11-06-vocal-stem-transition.md`.
- Personal tool on owner’s Ubuntu + domain; skip multi-user/billing polish.  
- Owner authorized feedback-driven candidate preference learning on 2026-11-07. Learn settings rankings from explicit ratings/comparisons; no fabricated owner labels, generative blend audio or learned waveform curves. See `docs/superpowers/plans/2026-11-07-preference-learning.md`.

## Commits

Only commit when the owner asks. Do not commit secrets or large audio fixtures.
