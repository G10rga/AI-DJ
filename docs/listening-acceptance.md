# Milestone 4 listening acceptance

Execution started 2026-11-12. All six original jobs finished as Needs review.
The frozen definition and reports are under
`D:/AI-DJ-data/validation/listening-acceptance-3832c4ee1af243b595382cac21a7df19/`.
Milestone 4 is **in progress**. Listening acceptance and default approval are
pending; `legacy-v1` remains the persisted default.

## Frozen cases

These ten sources have not appeared in earlier improved-pipeline jobs. They are
source-disjoint within this five-pair batch, but are not claimed to be disjoint
from earlier reference imports/training or unfamiliar to the owner. Case labels
are hypotheses selected from the registered track versions; measured evidence
and actual listening must establish the situations covered.

| Case | Outgoing | Incoming |
|---|---|---|
| Dub rhythm | George Morel — Let's Groove | Nightcrawlers, MK — Push The Feeling On |
| Sung vocals | Gadjo, Alexandra Prince — So Many Times | Kiesza — Hideaway |
| Percussive vocals | Afro Medusa, Knee Deep — Pasilda | Jerry Ropero, Denis the Menace, Sabor — Coração |
| Hook to extended | Armand Van Helden — I Want Your Soul | Gaskin — A Fresh Energy |
| Short vocal edits | Herd & Fitz et al. — I Just Can't Get Enough 2024 | Hot 'N' Juicy, Mousse T. — Horny '98 Radio Edit |

Continuous-set integration order: Let's Groove → Push The Feeling On → Pasilda
→ So Many Times → A Fresh Energy. This reuses five batch sources and is a separate
continuity check, not five additional independent examples. The play-length
preference is 72 seconds per track; preserving vocal completion takes priority.

The owner-reviewed At Night → Stupidisco handoff is retained as a regression
reference, with source and retained audio/report hashes. The existing qualitative
verdict “its better” remains qualitative; full acceptance is unknown.

## First observed result

Let's Groove → Push The Feeling On completed model analysis and returned
`no_safe_candidate`; no comparison audio was published. The frozen source
timelines contain 209 and 60 supported eight-bar spans respectively. All 60
incoming spans pass the fixed-tempo filter, but none covers an entire estimated
quieter incoming overlap. This is a vocal-evidence abstention, not a failed beat
tracker or an owner listening verdict. The incoming vocal-active fraction is
approximately 0.686; the outgoing fraction is approximately 0.006. MDX activity
remains an estimate, not phrase transcription.

[Review this case](http://127.0.0.1:8005/transition-review/2cdf09ca47dd4724af91cf52f025e328)
to listen and supply actual source boundaries. The source-review page and API
return HTTP 200, the incoming original supports HTTP 206 range playback, and
unpublished result audio returns 404. No constraint was relaxed or source cue
invented to fill the comparison.

## Batch constraint diagnosis

The short-vocal-edit pair subsequently drove a timing-validator context recheck
fix. It is now a regression case for this change, not an independent quality
example. Fresh pairs are required for subsequent independent claims. Its exact-
cue corrected preview `94524e3c890f4afabef856d51f820e89` completed successfully;
owner listening feedback on this new audio is pending. See the same-context
timing report in `D:/AI-DJ-data/validation/timing-diagnosis-728ed7768f7f4915b0ea2855a1e7873f/`.

A later revision-9 attempt exposed the broader short-context detector problem.
Fixed 24-second context and consistent analysis levels now pass five real
regression attempts (three failures and two prior successes), with no timing
limit changes; deliberately corrupted timing remains rejected. These five
attempts are not the five independent M4 pairs. The latest short-edit preview
`531a62c658b5440e994b2e46a7a2ea25` is ready, with owner listening verdict pending.
The other frozen pairs and full five-song listening acceptance remain separate
unfinished work. See docs/transition-review.md for evidence and reproduction.

All five pairs were inspected against the frozen source records without changing
planner settings or manufacturing source corrections. Every case has supported
timing spans; every case loses all usable spans on at least one side to estimated
vocal activity. This is the current conservative rule, not proof that the songs
cannot be mixed. In particular, the incoming source must stay below the relative
vocal threshold for its entire 8/16-bar overlap; the outgoing source must stay
below it throughout its fade plus the two-second preceding guard.

| Case | Source vocal gate blocking all proposals |
|---|---|
| Dub rhythm | Incoming |
| Sung vocals | Both |
| Percussive vocals | Both |
| Hook to extended | Outgoing |
| Short vocal edits | Outgoing |

Exact counts and the read-only diagnosis script are retained as
`constraint-diagnosis.json` and `diagnose_batch.py` in the frozen session folder.
Counts include both recipes and both overlap lengths, so they are not unique bar
counts. Unknown evidence was not the blocker in these cases. Existing explicit
listening corrections can resolve vocal estimates, while beat/bar and encoded
audio checks remain mandatory. No gate or result was changed during diagnosis.

## Review in the main app

Owner feedback on corrected first-case preview `c0dd428a56464d9f8e6198253fbf65cc`:
“it sounds good”. The exact preview audio hash is
`ac1cabcfb5da5da781d7f1a0b4061ca489982713a6cb5f2fbd22271a21b13200`.
The statement is retained in the session's
`owner-feedback/0ffa31f081384769a13a41835e5641cf.json`, scoped to review revision 2
and this preview only. It is not an A/B choice or approval for all M4 cases.
The full comparison was resumed as `525e1ece692141c9a43a7acdaedd844a` with those
saved corrections. Original abstentions remain in the frozen job list; this
corrected comparison is linked in `corrected-comparison.json`.

That corrected comparison completed successfully: protected vocal and plain
crossfade alternatives both measured -20.0 LUFS. Pairwise listening feedback is
still pending. The first transition's existing confirmed source marks were
copied to five-song set review `6a1d5acfc50a4936aed356e012474ae5`, revision 1,
after verifying identical ordered source hashes, complete effective evidence,
timeline IDs and timing revisions. Provenance is retained in
`cue-transfer-ea736016b5224335939ed8bd524c9fa1.json`. This reuses an existing source
confirmation; it is not a new set-listening approval. Transitions 2, 3 and 4
still need source review, and no five-song audio has been published.

Open [Compare](http://127.0.0.1:8005/compare) for the five comparisons and
[Learning](http://127.0.0.1:8005/learning) for the continuous set. The ordinary
single heavy worker analyses new tracks, plans, renders and independently checks
timing. Queued work persists in the app database.

For each completed pair, listen to both versions around the handoff. Assess:

- Does the outgoing vocal line and its tail finish?
- Does the incoming song enter gradually without vocal collision?
- Do beats and bars stay aligned throughout the overlap?
- Is the energy consistent, without an abrupt hole or jump?

Use A/B/tie/neither with a specific defect note. These are actual owner verdicts
stored separately from legacy training. A preference vote alone is not approval
to change the application default. For the five-song set, also listen to every
middle track for uninterrupted source progression and all four transitions.

Needs review means the system withheld audio. Open **Review transitions**, listen
to the originals, mark outgoing vocal completion and incoming entry, explicitly
confirm, save, preview and resume. Human boundaries do not bypass timing checks.
Keep the initial abstention and the corrected revision as distinct results.

A valid baseline comparison contains a plain crossfade and a protected-vocal
version, both independently validated and within 0.3 LU. If two safe alternatives
cannot be produced, that case remains incomplete. Applied cues may differ; the
comparison evaluates complete proposals, not only one gain-envelope variable.

## Reproduce the report

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 -m scripts.listening_acceptance --session D:/AI-DJ-data/validation/listening-acceptance-3832c4ee1af243b595382cac21a7df19
```

Add `--watch` to refresh `status.json` and `README.md` every 30 seconds until the
six original jobs finish or request review. Reporting reads jobs and feedback;
it never saves votes, source corrections or default approval. `manifest.json`
stays immutable. `jobs.json` pins its hash and exact job IDs. `status.json` records
actual evidence, measured levels, recipes, applied cues, artifact integrity and
technical set checks as they become available.

Keep this session after a failure. If its examples lead to planner/renderer
tuning, they become regressions; select fresh pairs before claiming independent
quality. Promote only after actual listening acceptance and explicit owner
approval on a completed generation in the application.

Validation of the batch tooling: three isolated tests passed for immutable
definitions, retained-artifact integrity, both-recipe/level eligibility, changed
audio rejection, and absence of fabricated votes/default promotion. Python
compilation and `git diff --check` passed. These checks do not constitute musical
acceptance.
