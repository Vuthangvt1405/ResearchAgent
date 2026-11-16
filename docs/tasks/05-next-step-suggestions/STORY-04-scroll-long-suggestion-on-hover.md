# STORY-04: Scroll a long suggestion's text when the pill is hovered

[Epic PRD](../../requirements/05-next-step-suggestions/README.md) · [Sprint backlog](README.md)

**Summary:** Scroll a long suggestion's text when the pill is hovered
**Type:** Story | **Epic:** Next-step suggestions for beginners | **Priority:** Medium | **Labels:** chat, ux, ui | **Components:** chat UI
**Story points (suggested):** 2 — Complexity L, Uncertainty L, Effort L — one visual behaviour on the suggestion pills from STORY-01, plus touch and keyboard cases.

## User Story

As a **beginner choosing a suggested next step**, I want **a long suggestion's text to scroll slowly inside its pill while I hover over it**, so that **I can read the whole sentence before I pick it, while the pills stay small above the message box**.

## Background

STORY-01 shows three one-sentence suggestions as pills above the message box. Some sentences are longer than a pill, so they are cut off with "…". The client wants to read the rest by hovering: the text scrolls slowly until the end is visible. Clicking still puts the full sentence in the message box.

## Acceptance Criteria

**AC1 — Long text scrolls on hover**
Given a suggestion's text is longer than its pill and is shown cut off with "…"
When the user holds the mouse over the pill
Then after a short pause the text scrolls slowly sideways until its last word is visible, then stops there *(assumption: sideways, at reading speed, stops at the end)*

**AC2 — Back to the start when the mouse leaves**
Given the text has scrolled
When the mouse leaves the pill
Then the text goes back to the start with "…" again

**AC3 — Short text doesn't move**
Given a suggestion fits in its pill
When the user hovers over it
Then the text does not move

**AC4 — Click uses the full sentence**
Given a pill is cut off or partly scrolled
When the user clicks it
Then the full sentence (not the cut-off part) is put in the message box, as in STORY-01 AC3

**AC5 — Keyboard**
Given the user moves to a pill with the Tab key
When the pill has focus
Then the text scrolls as in AC1, and Enter puts it in the message box

**AC6 — Touch screens**
Given the user is on a touch screen (no hover)
When they tap a cut-off pill
Then the full sentence goes into the message box, where they can read it before sending *(assumption: no scrolling on touch)*

## Developer Notes

- **Context & intent:** keep the three pills on one tidy row above the message box, while long sentences stay readable.
- **Likely areas:** the suggestion pill component built in STORY-01 (custom chat UI, probably `public/custom.js` / a custom element). Plain CSS (overflow hidden, ellipsis, a transform animation on hover) is likely enough. *(assumption: verify)*
- **Dev decisions:** scroll speed and the pause before scrolling; whether the pill also shows the full text as a tooltip.
- **Accessibility:** users who turned on "reduce motion" in their system settings should not get the moving text; show the full text as a tooltip instead. The pill's accessible name is the full sentence, so screen readers read all of it.
- **Edge cases:** very long sentences (scroll time grows; keep speed steady), narrow windows where all three pills are cut off, right-to-left text.
- **Testing hints:** a suggestion of ~25 words; check hover, mouse-out, Tab focus, touch emulation, and reduced-motion mode.

## Out of Scope

- Wrapping pills onto several lines.
- Changing how suggestions are chosen (STORY-01).

## Dependencies

- STORY-01 (the pills must exist).

## Open Questions

- None.
