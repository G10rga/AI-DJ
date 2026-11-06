# AI DJ Set Maker — Design

**Date:** 2026-10-30  
**Updated:** 2026-11-06 (owner decisions recorded; local development first)  
**Status:** Approved by owner on 2026-11-06  
**Working name:** ai-dj-set (personal tool)  
**Handoff:** See repo root `HANDOFF.md` / `AGENTS.md`

## Intent

Build a personal web app that turns a user-uploaded house playlist into one continuous, DJ-like set with usable transitions. Develop and run locally on the owner’s PC first. Ubuntu hosting is a later deployment target. First user is the owner; polish for a public audience is out of scope for v1.

## Why

House sets live or die on transitions. Existing “mashup” toys often produce weak joins. The owner wants to dump ~30+ of their own tracks and get a set they’d actually play, with a quick way to fix the few bad handoffs.

## Goals

- Upload at least ~30 house tracks (user-provided files).
- Produce one playable audio file (e.g. MP3/WAV) of a continuous set.
- Beatmatched, phrase-aware transitions that don’t feel amateur.
- Adaptive transition length/style per pair: short (~8-bar EQ in / cut) when grooves lock; longer (~32-bar smooth) when the handoff needs room.
- Unsupervised ML chooses **track order** and **which transition style** to use between pairs.
- After first render: swap a weak transition style and re-render; play or download the result.
- Run locally on the owner’s PC; retain a path to later Ubuntu deployment.
- Use DJ-style excerpts with selected mix-in/out points and include every valid uploaded track.

## Non-goals (v1)

- Public stem export, cue markers, or export for Serato/Rekordbox/etc. Owner authorized internal pretrained vocal/instrumental separation on 2026-11-06 for independent vocal handoffs.
- Streaming catalogs, YouTube ingest, or commercial licensing of music.
- Multi-user accounts, billing, or public product polish.
- Generative / learned “how the blend sounds” (EQ curves, mash overlays, AI audio). Explicit **future** feature.
- Multi-genre party mixes; v1 is house-focused.
- Live DJ performance UI (decks, jog wheels).

## Anti-goals

- A set that is technically continuous but fails because transitions are weak, clashy, or off-phrase.
- Forcing one transition style for every pair.
- Blocking on labeled “good mix” training data for v1.

## Constraints

- **Stack (defaults):** Python backend (FastAPI), background workers for long jobs, files on disk, simple web UI. Frontend framework left to builder unless owner prefers otherwise.
- **Hosting/access:** Local PC only for now; bind to loopback and defer login, public access, domain configuration, and remote deployment.
- **Later server target:** 4 GB RAM, third-generation Intel Core i3, and 200+ GB storage. Develop on the PC first; its CPU/RAM are not yet specified. Keep memory bounded, cache analysis, and default to one heavy processing job at a time for the later server target.
- **Input:** User uploads their own audio files.
- **Output:** Single playable file + in-app playback; no DJ-software package.
- **Compute:** Analysis + stretch/mix of 30+ tracks is CPU-heavy; design for async jobs and progress, not a single request/response.

## User flow

1. Upload 30+ house tracks.
2. Local backend analyzes tracks and builds a mix plan (order + excerpt mix-in/out points + transition styles), including all valid uploads. Invalid or undecodable inputs must be reported rather than silently omitted.
3. Server renders one continuous set.
4. User plays the set; inspects tracklist with per-join transition labels.
5. User swaps a weak transition style (and may nudge order if cheap to support); requests re-render.
6. Download or keep playing the updated file.

## System shape

```
Upload → Analyze (DSP) → Order + style (unsupervised ML)
      → Transition plan (rules + pair scores) → Render (DSP)
      → Editor (swap style) → Re-render → Play / download
```

### Analyze (DSP)

Per track: BPM, beat grid, key (or camelot-style), energy over time, coarse structure/phrase hints (intro / body / outro where reliable). Prefer established libraries over custom ML for this layer in v1.

### Unsupervised ML (v1 scope)

- Build track embeddings / features from analysis (and optionally short audio embeddings).
- Cluster or nearest-neighbor similarity to propose a listening order suited to house (tempo continuity, key compatibility, energy arc — exact objective left to builder within “sounds like a set, not a shuffle”).
- Score each adjacent pair for blend difficulty; map score → transition style (e.g. 8-bar EQ/cut vs 32-bar smooth; builder may add a small discrete set like 16-bar filter if useful).
- No labeled mix dataset required.

### Transition plan + render (DSP)

**Owner extension (2026-11-06):** Support an optional mid-song experiment using
pretrained local vocal/instrumental separation. Keep the instrumental groove
running, fade the outgoing vocal separately, then introduce the incoming vocal.
Audio stays local. This is source separation plus deterministic mixing, not
training/generating a blend model or providing a public stem-export feature.
Separation leakage/artifacts and heuristic vocal-gap timing require listening.

- Align in/out to bars/phrases from the beat grid.
- Choose DJ-style excerpts rather than playing full tracks. Exact excerpt duration is a builder tuning decision; no fixed duration has been approved.
- Include every valid uploaded track; do not drop tracks merely because they are poor musical fits.
- Time-stretch for tempo match without destroying groove when possible.
- Apply the chosen recipe (EQ swap / cut / longer crossfade).
- Write one continuous audio file.
- Re-render after a swap should prefer regenerating affected regions when practical; full re-render is acceptable for v1 if region-patching is costly.

### Editor

- Show ordered tracklist with the transition style between each pair.
- Allow swapping style for a join; trigger re-render.
- Play and download the current set file.
- Drag-reorder and per-blend preview are nice-to-haves, not required for v1 if they inflate scope; swap + re-render is required.

## Future (explicitly not v1)

- Learned blend curves / deeper ML on how transitions sound.
- Richer editor (drag-reorder mandatory, solo-preview each transition).
- Multi-user or public deployment hardening.

## Success criteria

- Owner can upload ~30 house tracks and get a set they will listen through without flinching at most joins.
- Weak joins are fixable by swapping transition style and re-rendering without starting over.
- End-to-end path works locally on the owner’s PC using loopback access.
- Every valid uploaded track appears as a DJ-style excerpt in the rendered set.

## Owner decisions resolved (2026-11-06)

1. **Track length in set:** DJ-style excerpts with mix-in/out selection.
2. **Coverage:** Include all uploaded tracks; poor musical fit is not grounds for omission. Invalid inputs must be surfaced for correction.
3. **Resources/development:** Develop locally on the owner’s PC first. Later server has 4 GB RAM, a third-generation Intel Core i3, and 200+ GB storage.
4. **Access:** Local PC only for now. Remote access and authentication requirements are deferred until hosting is in scope.

All four owner questions are answered. Owner explicitly approved the revised design on 2026-11-06. Implementation planning and application code are authorized within this scope.

## Left to the builder

- Concrete libraries (analysis, stretch, ML embedding/clustering).
- Frontend choice and minimal UI aesthetics.
- Job queue / process model on Ubuntu.
- Exact discrete set of transition styles and scoring thresholds.
- Audio formats supported and output codec/bitrate defaults.
- Storage layout and cleanup policy for uploads and renders.
- Whether first-version reorder is included or deferred behind swap-only.

## Out of scope decisions (owner already made)

| Topic | Decision |
|-------|----------|
| Audience | Personal tool first |
| Genre focus | House |
| Min scale | ~30 tracks → one set |
| Failure that matters most | Weak transitions |
| Transition policy | Adaptive 8-bar vs ~32-bar (and similar) by pair |
| ML in v1 | Order + transition style only |
| Deeper blend ML | Future |
| Input | User-provided files |
| Output | Playable file only |
| Post-mix | Swap transition + re-render |
| Hosting | Local PC first; owner Ubuntu server later |
| Track length | DJ-style excerpts with selected mix points |
| Coverage | Include all valid uploaded tracks |
| Access | Local PC only for now |
| Backend language | Python |
