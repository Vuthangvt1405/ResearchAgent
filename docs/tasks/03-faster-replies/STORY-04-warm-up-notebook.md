# STORY-04: Start the notebook in the background when a chat opens

[Epic PRD](../../requirements/03-faster-replies/README.md) · [Sprint backlog](README.md)

**Summary:** Start the notebook in the background when a chat opens
**Type:** Story | **Epic:** Faster assistant replies | **Priority:** Medium | **Labels:** performance, notebook | **Components:** kernel, chat start
**Story points (suggested):** 3 — Complexity L, Uncertainty M, Effort L — the start code exists; the work is starting it early and handling "Docker isn't running" quietly.

## User Story

As a **researcher whose first request runs notebook code**, I want **the notebook to be ready before the assistant needs it**, so that **the first code run doesn't add a long start-up wait to my answer**.

## Background

The notebook engine (a Docker container) starts only when the first cell runs, and starting it can take many seconds (up to 60 s is allowed). It also stops after 30 minutes without use. So the first notebook step of a chat, or the first after a break, is noticeably slower than the rest.

## Acceptance Criteria

**AC1 — Started early**
Given a chat opens in a project with the notebook switched on and the notebook not running
When the chat finishes opening
Then the notebook starts in the background, without delaying the greeting or the user's first message

**AC2 — First run is quick**
Given the background start has finished
When the assistant runs its first cell
Then the cell starts without any notebook start-up wait

**AC3 — User is faster than the start-up**
Given the background start is still going
When the assistant needs to run a cell
Then it waits only for the rest of the start-up (it doesn't start a second one)

**AC4 — Docker not running**
Given Docker isn't running
When a chat opens
Then no error is shown at chat start; the usual "Docker isn't running" message appears only if the user or assistant actually runs a cell

**AC5 — Notebook switched off**
Given the notebook switch is off in settings
When a chat opens
Then the notebook is not started

## Developer Notes

- **Likely areas:** `on_chat_start` in `app.py` (`notebook.open_for_session()`), `KernelManager.start` / `_kernel` in `researchchat/workspace/kernels.py` (already guarded by a per-project lock, which helps AC3).
- **Dev decisions:** start on chat open vs. on the first message; whether the idle stop (30 min) should restart early when the user comes back (e.g. on typing).
- **Non-functional:** each running notebook can use up to 2 GB of memory and 2 CPUs; starting early means it uses that while the user is only chatting.
- **Testing hints:** open a chat, wait, ask for a notebook step; compare first-cell time with today's cold start.

## Out of Scope

- Making the container image smaller or start faster.
- Changing the 30-minute idle stop.

## Dependencies

- None.

## Open Questions

- None. Dev decision (client, 2026-11-14): when to start the notebook early, weighing memory use against the faster first run.
