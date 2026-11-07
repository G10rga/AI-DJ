---
name: AI-DJ
description: A flat, low-light workspace for listening and correcting musical timing.
colors:
  ground: "#000"
  surface: "#111"
  raised: "#242424"
  control: "#444"
  text: "#fff"
  muted: "#b4b4b4"
  accent: "#c6f24e"
  warning: "#e5a93b"
  error: "#ff8a91"
  pressed: "#333"
  primary-hover: "#ddd"
  placeholder: "#a2a2a2"
  divider: "#252525"
  waveform: "#343434"
  vocal: "#909090"
  beat: "#555"
typography:
  mobile-title:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.3
  mobile-section:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 600
  mobile-legend:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 400
  brand:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 600
  title:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "22px"
    fontWeight: 600
    lineHeight: 1.3
  headline:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 600
  body:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.6
  section-label:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 500
  label:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
  caption:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 400
rounded:
  control: "6px"
  panel: "12px"
spacing:
  compact: "8px"
  field-gap: "10px"
  inset-small: "12px"
  inset-mobile: "16px"
  panel: "20px"
  section: "24px"
  workspace-gap: "28px"
  page: "32px"
components:
  button-primary:
    backgroundColor: "{colors.text}"
    textColor: "{colors.ground}"
    rounded: "{rounded.control}"
    padding: "8px 11px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "8px 11px"
  button-secondary-hover:
    backgroundColor: "{colors.raised}"
  input:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "8px 11px"
  track-current:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
  timeline-panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
    padding: "20px"
---

# Design System: AI-DJ

## Overview

**Creative North Star: "The Low-Light Listening Desk"**

AI-DJ is a compact working instrument: true black, flat neutral surfaces, precise timing columns and familiar controls. Its visual language supports sustained listening and direct correction. Musical evidence supplies the visual interest; decoration does not compete with it.

Inter carries the entire interface, with tabular numerals keeping times steady. The selected surface direction is Operate: restrained controls and explicit states, with no glow or decorative motion. Mix listening and the timeline editor share this established visual vocabulary; these rules describe the implemented surfaces rather than a complete future mix application.

**Key Characteristics:**
- True-black ground with flat tonal grouping.
- Compact Inter typography and tabular times.
- Lime energy, pale vocal activity and amber phrase markers.
- Familiar controls with visible keyboard focus.
- Explicit uncertainty, provenance and correction state.

## Colors

The palette is predominantly neutral, with a small functional signal vocabulary. The frontmatter contains the normative values, extracted from the stylesheet and SVG renderer.

### Primary
- **Energy Lime** (`accent`): measured RMS energy, the seek control, text selection and keyboard focus. The primary save button uses white rather than lime.

### Secondary
- **Timing Amber** (`warning`): phrase-candidate lines and ordinary status messages. Amber identifies phrase candidates, including original estimates; it does not uniquely mean a manual edit.
- **Error Rose** (`error`): request, validation and audio errors in the live status region.

### Neutral
- **True Black** (`ground`): page ground and sticky table headings.
- **Listening Surface** (`surface`): timeline, selected track, selects and empty state.
- **Hover Charcoal** (`raised`) and **Pressed Charcoal** (`pressed`): button interaction states.
- **Control Gray** (`control`): field and button outlines.
- **White** (`text`): primary text and playhead; also the save-button fill.
- **Supporting Gray** (`muted`) and **Placeholder Gray** (`placeholder`): supporting copy and input hints.
- **Pale Gray** (`primary-hover`): primary-button hover and actual downbeat strokes.
- **Divider Gray** (`divider`): table row separators.
- **Waveform Gray** (`waveform`), **Vocal Gray** (`vocal`) and **Beat Gray** (`beat`): peak envelopes, vocal regions and fine beat lines. Legend swatches approximate vocal/downbeat strokes rather than forming additional semantic roles.

**The Evidence Color Rule.** Preserve each musical signal's meaning across the chart and legend; color is an aid to the accompanying text, geometry and position.

## Typography

**Display and Body Font:** Inter, self-hosted as a variable TrueType font with system-ui and sans-serif fallbacks. There is no separate display or monospace family. The shipped font license remains with the font asset.

**Character:** Compact, neutral and readable. Tabular numerals apply globally, so playback times, marker times and evidence values align without a monospace costume.

### Hierarchy
- **Title:** track or mix name, reducing to (20px) on mobile; balances and wraps long filenames.
- **Headline:** primary section headings.
- **Section label:** smaller evidence/history headings, with (24px) above and (12px) below.
- **Body:** base interface type; explanatory paragraphs use generous line spacing. Correction guidance uses the label size and a maximum (75ch) measure.
- **Label:** table, evidence and correction labels. These finish at (13px), including overrides at the end of the stylesheet.
- **Caption:** library subtitles, legend, transport, revision status and compact action metadata. The mobile legend reduces to (11px).

## Layout

The desktop workspace is a two-column grid: a (224px) track library, a (28px) gap and the remaining width for the editor. Main content has (32px) horizontal padding and a maximum width of (1800px). The header is (64px) tall. The timeline occupies the editor width above the corrections and evidence; the lower grid reserves (280px) for evidence with a (32px) gap.

At widths up to (1100px), the library becomes (190px), page padding becomes (24px), and the main gap becomes (22px). Corrections and evidence stack; evidence retains a two-column internal grid. The revision stacks under the track title, and the secondary seeking instruction is hidden.

At widths up to (650px), the header becomes (56px), page padding becomes (16px), and the library stacks above the editor. Track navigation scrolls within (150px). The library hint and local-library header label disappear. The workspace starts (26px) below the library. Evidence returns to block flow; grouped toolbar fields wrap while keeping each label beside its control.

The chart remains (230px) high at every breakpoint. Its SVG viewBox follows the rendered width, with a minimum drawing width of (280px), so chart labels retain their size. Six time labels use inward anchoring at the edges. The legend wraps; controls and action rows wrap rather than forcing a horizontal page scroll. Marker rows scroll within (245px) with a sticky heading.

Mix listening reuses the library/workspace grid. The full-width player leads the workspace; tracklist and transitions occupy one lower column, with previews in an equal second column separated by (36px). The lower columns stack at the tablet breakpoint with a (28px) gap. On mobile, the mix library scrolls within (190px), the workspace starts (24px) below it, and listening details start (26px) below the player. Long names and preview action rows wrap.

## Elevation & Depth

There are no shadows, gradients, glows or decorative animation. Depth comes from the black ground, slightly lighter timeline and selected-track surfaces, and thin control/table boundaries. Playback updates communicate actual progress. Browser-native audio and select rendering can vary by platform.

**The Flat Surface Rule.** Use tonal grouping and spacing to establish hierarchy; preserve the shadow-free working surface.

## Shapes

Controls and selected tracks use the control radius; the timeline and empty state use the larger panel radius. Buttons and fields have a thin (1px) outline. Table rows remain square and separated by rules. The brand mark is a simple inline geometric SVG. Chart geometry is generated from actual musical analysis, not illustrative waveform artwork.

## Components

### Buttons

Conventional, compact and explicit. Standard controls have a minimum height of (38px). Secondary buttons have transparent fills and control-gray outlines; hover uses the raised surface and press uses the pressed tone. Save is white with black text and a pale hover fill. The primary button inherits the generic pressed rule, but its later primary rule keeps the white fill; no separate primary pressed treatment is established.

Disabled buttons have half opacity and the default cursor. Save is disabled when unchanged or saving. During a save, buttons, inputs and selects are disabled together; success updates the visible revision and failure uses the error status. Compact footer controls are (32px) minimum height; table and evidence actions are (30px).

All buttons, inputs, selects and links have a lime (2px) focus-visible outline with (3px) offset. Do not hide this state.

### Inputs / Fields

Transparent fields sit directly on the page ground with control-gray borders and muted placeholders; selects use the listening surface. Inputs use a lime caret. The search field and correction-note field fill their available width. The time field is (86px), reducing to (80px) on mobile. Validation and server errors appear in the shared live status region; there is no established per-field error border treatment.

### Navigation

The library is a vertical set of left-aligned track or mix buttons with wrapping names and a supporting subtitle. Current selection uses the listening surface and white text; other entries use supporting gray. Track entries are at least (62px) high and mix entries (72px), with (5px) between entries. Mix subtitles show duration, track count and unavailability when applicable.

The brand is a plain home link with an inline SVG. Beside it, Mixes and Timelines are text links: the current page is white, the other supporting gray, and hover underlines the link. Their horizontal gap reduces from (24px) to (18px) on mobile. The home page and `/mixes` open listening; `/timelines` opens source correction. No chip or tag component is currently implemented.

### Cards / Containers

The timeline and empty state use the listening surface and panel radius without an outline or shadow. Timeline padding reduces from the panel inset to (16px 12px) on mobile. Corrections and evidence remain directly on the page ground; they are not individually boxed cards. The empty state has a maximum width of (760px), with (48px 24px) padding.

The full mix player reuses the listening surface and panel radius, with the panel inset on desktop and (18px 14px) on mobile. Tracklists, transitions and previews stay on the page ground; thin dividers separate track rows and preview alternatives.

### Mix playback and comparison

The full mix panel pairs its heading with an outlined MP3 download link and a full-width native audio player (52px high). A quiet label-size note explains track seeking or retention of the previous playable version. The two latest associated matched previews use native audio players (42px high), compact titles and caption-size duration, handoff and song-pair metadata. Preview download links are underlined supporting text.

Tracklist rows are full-width seek buttons, at least (60px) high, with a muted label-size timestamp beside a wrapping body-size filename. Transition buttons show the saved style and a caption-size time range; they seek the full mix to the handoff. Preview handoff buttons start playback four seconds before the displayed handoff, explained by their tooltip. Starting any player pauses the others; loading never autoplays audio.

Unavailable mix audio hides the full player and disables track/transition seeking while retaining the saved details. Missing previews and request failures use explicit text and the existing status/error vocabulary. Native media controls remain platform-rendered; static design examples demonstrate their layout without supplying audio or playback behavior.

### Musical timeline

Gray peak envelopes support the lime energy trace; pale strips show available vocal activity. Fine gray beats, pale downbeats and amber phrase candidates have distinct heights and weights. A white playhead and labeled time axis orient seeking. Whole-song, 60-second and 30-second views share the same visual grammar. Dense beat lines are omitted when more than (240) are visible; downbeats and phrase candidates remain.

The SVG supports pointer seeking; the native range and audio controls provide familiar playback and keyboard access. Unknown vocals are labeled in the chart and evidence copy. Confidence remains explicitly uncalibrated; no percentage badge or implied musical approval is established.

### Correction table and status

The table uses a sticky muted heading, horizontal row dividers, left-aligned marker names and right-aligned times/actions. Time buttons seek; Remove buttons modify markers. The footer exposes saved/unsaved state and original-estimate restoration. Revision history and model provenance use quiet text, aligned evidence values and underlined candidate links. Status messages use amber, with rose reserved for errors; the message region announces updates politely.

## Do's and Don'ts

### Do:
- **Do** retain the flat black ground, compact Inter type and tabular timing columns.
- **Do** preserve lime keyboard focus and clear disabled, unsaved, saving and error states.
- **Do** generate musical geometry from actual analysis and label unavailable evidence explicitly.
- **Do** let filenames, legends and grouped toolbar fields wrap at narrow widths.
- **Do** keep original predictions and correction revisions visibly distinguishable.

### Don't:
- **Don't** add decorative glow, shadows or motion to the listening workspace.
- **Don't** invent waveform details, vocal certainty, calibrated confidence or listening approval.
- **Don't** use amber as proof that a marker was manually edited.
- **Don't** replace familiar native playback controls with unexplained decorative controls.
- **Don't** introduce unlicensed imagery or a new type family without updating the established visual system.
