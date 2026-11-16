# STORY-03: Suggest three first steps when a chat starts

[Epic PRD](../../requirements/05-next-step-suggestions/README.md) · [Sprint backlog](README.md)

**Summary:** Suggest three first steps when a chat starts
**Type:** Story | **Epic:** Next-step suggestions for beginners | **Priority:** Medium | **Labels:** chat, onboarding, ux | **Components:** chat
**Story points (suggested):** 2 — Complexity L, Uncertainty L, Effort L — the greeting already exists; it only needs three suggestions chosen from the project's current state.

## User Story

As a **beginner opening a new chat**, I want **three suggested first steps above the message box that fit my project**, so that **I know how to start without having to think up the first question**.

## Background

A new chat shows only "Hi! What would you like to research today?". A beginner facing an empty box often doesn't know what the app can do. The suggestions from STORY-01 start after the first reply; this story covers the moment before it.

## Acceptance Criteria

**AC1 — Empty project**
Given the project has no datasets and an empty notebook
When a new chat starts
Then three suggestions about getting started appear above the message box (e.g. "Find a dataset about house prices.", "Download the iris dataset and show it.", "Explain what this app can do.")

**AC2 — Project with data**
Given the project has a ready dataset `hf-scikit-learn--iris`
When a new chat starts
Then at least one suggestion uses that dataset by name (e.g. "Summarise the iris dataset.")

**AC3 — Project with notebook work**
Given the notebook already has cells
When a new chat starts
Then at least one suggestion continues that work (e.g. "Explain what my notebook does so far.")

**AC4 — Same behaviour as STORY-01**
Given starting suggestions are shown
When the user clicks one
Then it behaves as in STORY-01 AC3–AC5 (text goes into the message box as ordinary text for the user to send; pills hide while the box has text)

**AC5 — Shown at once**
Given a new chat starts
When the greeting appears
Then the suggestions appear with it, without waiting for the assistant *(assumption: picked from fixed templates filled with the project's data, so no delay)*

## Developer Notes

- **Likely areas:** `on_chat_start` in `app.py` sends the greeting; reuse STORY-01's suggestion chips above the message box. Chainlit's "starters" (`@cl.set_starters`) are fixed per app and send at once, so they don't fit. *(assumption: verify)*
- **Dev decisions:** fixed templates vs. a model call; how to pick the dataset when there are many (most recent).
- **Testing hints:** start chats in an empty project, a project with one dataset, and one with notebook cells.

## Out of Scope

- Suggestions after replies (STORY-01).
- Changing the greeting text.

## Dependencies

- STORY-01 (shares the click behaviour).

## Open Questions

- None.
