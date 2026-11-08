# Reference recording import

Import a local DJ recording (including the audio stream of an MP4) and its
original song files with an **ordered, untimestamped** manifest. This is the CLI
foundation for the reference collection. Per-transition [browser listening
review](reference-review.md) is available at `/references`; durable worker progress
remains unfinished. Existing `/mixes` continues to show generated mixes.

Create a UTF-8 JSON manifest. Relative paths resolve beside the manifest:

```json
{
  "title": "My reference set",
  "recording": "D:/Music/reference.mp4",
  "tracks": [
    {"title": "First song", "sources": ["D:/Music/first.mp3"]},
    {"title": "Second song", "sources": ["D:/Music/second.mp3", "D:/Music/second-remix.mp3"]},
    {"title": "Unknown version", "sources": [], "note": "Exact remix not found yet"}
  ]
}
```

Every list entry is a distinct occurrence, even when the source is repeated.
Up to five source alternatives may be compared. An explicitly empty source list
preserves an unresolved track; a path to a missing/broken file fails the import
before publishing anything. Imports snapshot source paths, hashes and durations;
changing source audio requires a new import. Original files are read in place.

From the repository:

```powershell
scripts/local.ps1 -m scripts.import_reference import D:/Music/manifest.json
scripts/local.ps1 -m scripts.import_reference align REFERENCE_ID --output D:/Music/alignment.json
scripts/local.ps1 -m scripts.import_reference refine REFERENCE_ID --output D:/Music/refined-alignment.json
scripts/local.ps1 -m scripts.import_reference report REFERENCE_ID --output D:/Music/report.md
scripts/local.ps1 -m scripts.import_reference template REFERENCE_ID --output D:/Music/review.json
scripts/local.ps1 -m scripts.import_reference show REFERENCE_ID --output D:/Music/snapshot.json
```

The import returns `id`, used as `REFERENCE_ID`. Audio extraction accepts up to
eight hours per input, decodes at most 41 seconds per chunk and keeps only compact
4 Hz spectral features. Extraction caches live under the configured D: data root.
One hour-long recording does not go through the twenty-minute song analyzer.

The matcher compares 16-second source windows over duration ratios 0.92–1.08.
Each hypothesis records `mix_time = offset_seconds + scale * source_time`.
The offset can be negative when a DJ begins partway through a song. Up to three
hypotheses per source per search pass retain their independent anchor windows and raw spectral
similarities. Similarities are **not confidence probabilities**. Ordered
suggestions retain increasing recording anchors with at least two supporting
windows; uncertain/unresolved entries remain null rather than forcing coverage.
Anchors do not establish audible track boundaries, overlap bars or exact EQ.
Pitch shifts, edits, very short excerpts and changing tempo may prevent matches.

`refine` appends a new snapshot using denser source windows in the gaps between
existing ordered proposals. It retains all earlier hypotheses and links to the
parent alignment. `refine --detailed` tries 8-second windows and duration ratios
0.8–1.2 for remaining gaps; these short-window proposals require four supporting
windows. Wider search is for locating reference audio, not permission to stretch
generated mixes beyond the renderer's limits. `report` exports a Markdown table
of the latest ordered proposals, explicitly distinguishing anchors from starts.

Review by listening, choose each `source_hash` from the import snapshot, and fill
the source/recording excerpt intervals in `review.json`. Intervals use seconds.
Set `reviewed` to true only after review. Unknown transition controls remain
null. Recipe categories are `groove_32`, `controlled_16`, `eq_8`, `cut`, `other`,
or null; these are observations, never automatic preference judgments.

```powershell
scripts/local.ps1 -m scripts.import_reference review REFERENCE_ID D:/Music/review.json
```

Saving requires every ordered source interval and the current `expected_revision`.
It validates source identities, positive bounded intervals, track order and
transition fields. Reviews append revisions without changing imports or
predictions. Stale revisions require reloading. The untouched template is not
a reviewed annotation. No training/promotion or negative alternatives are created.
