# Epic PRD — Next-step suggestions for beginners

**Suggested total:** 15 points · **Backlog:** [docs/tasks/05-next-step-suggestions/](../../tasks/05-next-step-suggestions/README.md)

## Summary

Help beginners know what to do next: at moments when the user is likely to need a next step (and at the start of a chat), show three short suggestions as pills just above the message box; clicking one puts it in the box as ordinary text, and the user sends it.

## Background

Client request (2026-11-14): "I want beginners to easily know what to do after each step; recommend 3 sentences depending on the current context." Follow-up: suggestions should be "smart" and appear only when the user needs them, not after every reply; the client leaves the exact rules to the PO. Today a reply ends with nothing after it, and a new chat shows only the greeting "Hi! What would you like to research today?".

## Requirement Analysis

| Item | Finding |
|---|---|
| Actors | Beginner researcher (main); experienced user (may not want it) |
| Goals | Get a sensible next step when stuck; start a chat without a blank-page moment |
| Business value | Fewer stuck or abandoned sessions; beginners learn the usual analysis flow *(assumed)* |
| Rules (stated) | Three one-sentence suggestions based on the current context; pills above the message box; click fills the box as ordinary text, the user sends; hidden while the box has text, back when emptied; long pills scroll on hover; only when the user needs them |
| Rules (assumed, PO) | When "needed" means: after a finished step, after an error, when the user seems stuck, when the reply asks a choice; not when the next step is already clear, not for small talk (STORY-02); user's language; off-switch, on by default |
| Data | Recent chat, tools used this turn, pending approvals, project datasets, notebook state |
| Ambiguities | None left for the client; STORY-02 rules are PO assumptions |

## Estimation Log

| Candidate story | Complexity | Uncertainty | Effort | Points | Action |
|---|---|---|---|---|---|
| Context-aware next-step suggestions everywhere | M | M | M | 8 | ✂️ Split (by workflow step) to keep each part small |
| ↳ STORY-01: After each reply | M | M | M | 5 | Re-estimated below |
| ↳ STORY-03: At chat start | L | L | L | 2 | ✅ Keep |
| ↳ STORY-05: On/off switch | L | L | L | 1 | ✅ Keep |
| STORY-01 + hover-scroll for long pills (PO, 2026-11-14) | M | M | H | 8 | ✂️ Split (by business rule): hover-scroll becomes its own story |
| ↳ STORY-04: Scroll a long suggestion on hover | L | L | L | 2 | ✅ Keep |
| STORY-01 + "smart: only when needed" (PO, 2026-11-14) | M | H | M | 13 | ✂️ Split (by business rule): what/how vs. when |
| ↳ STORY-01: Pills above the message box (what & how) | M | M | M | 5 | ✅ Keep |
| ↳ STORY-02: Only when the user needs them (when) | M | H | L | 5 | ✅ Keep |

## Ticket Tree

```
Epic: Next-step suggestions for beginners  (total: 15 points)
├── STORY-01: Show three clickable next-step pills above the message box  (5 pts, High, depends on: —)
├── STORY-02: Show next-step suggestions only when the user is likely to need them  (5 pts, High, depends on: STORY-01)
├── STORY-03: Suggest three first steps when a chat starts  (2 pts, Medium, depends on: STORY-01)
├── STORY-04: Scroll a long suggestion's text when the pill is hovered  (2 pts, Medium, depends on: STORY-01)
└── STORY-05: Let the user turn next-step suggestions on or off  (1 pt, Low, depends on: STORY-01)
```

## Decisions (PO, 2026-11-14)

1. Suggestions sit just above the message box; clicking one puts its text in the box, and the user sends it (STORY-01, STORY-03).
2. While the message box has any text (typed or from a clicked pill), the suggestions are hidden (STORY-01).
3. Text put in the box by a click is ordinary text: the user can edit, delete or send it, the same as typed text (STORY-01).
4. Suggestions are pills; a long one is cut off and its text scrolls slowly while hovered, so the whole sentence can be read; clicking puts the full sentence in the box (STORY-04).
5. When the message box is emptied without sending, the same three suggestions come back (STORY-01).
6. Suggestions are not shown after every reply; the app decides when the user needs one. The client leaves the rules to the PO (STORY-02).

## Open Questions

- None for the client. STORY-02's "when" rules and STORY-05's off-switch are PO assumptions, open to change in team review.
