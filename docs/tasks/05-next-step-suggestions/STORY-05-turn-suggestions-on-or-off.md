# STORY-05: Let the user turn next-step suggestions on or off

[Epic PRD](../../requirements/05-next-step-suggestions/README.md) · [Sprint backlog](README.md)

**Summary:** Let the user turn next-step suggestions on or off
**Type:** Story | **Epic:** Next-step suggestions for beginners | **Priority:** Low | **Labels:** chat, settings | **Components:** chat settings
**Story points (suggested):** 1 — Complexity L, Uncertainty L, Effort L — one switch next to the existing chat settings (e.g. "Web search").

## User Story

As an **experienced user who no longer needs guidance**, I want **to switch off the suggested next steps**, so that **the chat stays uncluttered**.

## Background

Suggestions help beginners (STORY-01, STORY-03, STORY-02) but can still feel like noise once a user knows the app. The chat already has a settings panel with switches such as "Web search".

## Acceptance Criteria

**AC1 — Switch exists and is on by default**
Given a new chat
When the user opens the chat settings
Then there is a switch "Suggest next steps", turned on

**AC2 — Turning it off**
Given the switch is turned off
When the assistant replies (or a new chat starts in that session)
Then no suggestions are shown

**AC3 — Turning it back on**
Given the switch was off
When the user turns it on and sends a message
Then suggestions appear under the next reply

## Developer Notes

- **Likely areas:** `build_widgets` / `on_settings_update` in `app.py` and the settings defaults in `config.toml` (same pattern as the web search switch). *(assumption: verify)*
- **Dev decision:** whether the choice is remembered across chats (today's settings are per chat session).

## Out of Scope

- Choosing how many suggestions to show.

## Dependencies

- STORY-01.

## Open Questions

- None.
