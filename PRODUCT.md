# AI-DJ

## Platform
Local browser application on Windows, bound to loopback. Ubuntu deployment is
deferred. Audio, model environments and caches stay below `D:\AI-DJ-data`.

## User and job
One owner making AfroHouse mixes from their own local tracks. They select tracks,
generate a continuous set and listen to alternatives for weak transitions.
Transition quality matters most; every valid selected entry must remain included.

## Mechanism
Analyze musical context, generate and validate transition candidates, render
audio, and learn settings rankings from explicit listening feedback. The saved
plan names frozen MERT embeddings and Beat This beat/downbeat inference. Estimates
need provenance and human correction. Never invent feedback or musical approval.

## Stack
Python application, FastAPI, SQLite, one heavy worker, server-rendered UI and
lightweight JavaScript, as specified in the approved workflow plan.

## Current surface
Mix listening is the home page: choose a completed playable set, play/download
it, seek from its tracklist and compare recent matched previews for its song
pairs. Streams stay pinned to the saved playable revision while newer renders
finish. The Mixes and Timelines tabs separate listening from source correction.

Timeline review: select an analyzed song, listen/seek, inspect musical evidence,
correct beat/downbeat and phrase markers, and save a revision without destroying
the original prediction. The full mix/review application is still under development.

## Constraints
Personal tool, no billing/public deployment polish, no generated waveform or
learned EQ curves. Keyboard access and clear unavailable/error states are needed.
No established visual identity exists. Owner explicitly asks for autonomous work
without routine approval questions; existing plan settles task and stack.
