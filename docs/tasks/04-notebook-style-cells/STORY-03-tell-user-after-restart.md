# STORY-03: Tell the user to re-run the notebook after a kernel restart

[Epic PRD](../../requirements/04-notebook-style-cells/README.md) · [Sprint backlog](README.md)

**Summary:** Tell the user to re-run the notebook after a kernel restart
**Type:** Story | **Epic:** Notebook-style assistant cells | **Priority:** Medium | **Labels:** notebook, assistant, kernel | **Components:** assistant, notebook tools
**Story points (suggested):** 2 — Complexity L, Uncertainty L, Effort L — the assistant only has to notice the restart and say so; nothing is run for the user.

## User Story

As a **researcher returning to my notebook after a break**, I want **the assistant to tell me when the notebook was restarted and I need to re-run it**, so that **I stay in control of running my cells, like in Jupyter, and the assistant doesn't fill the notebook with copies of setup code**.

## Background

The kernel stops after 30 minutes without use and when the app restarts; variables and imports are then gone (in the `default` project the run numbers restart from 1 partway down). Once the assistant writes small cells that build on earlier ones (STORY-01), those cells fail after a restart. Jupyter handles this by leaving it to the user (Run All / Run All Above). The PO chose the same here (2026-11-14): the user re-runs the cells; the assistant only tells them.

## Acceptance Criteria

**AC1 — Restart noticed before writing code**
Given the kernel restarted since the earlier cells ran (their variables are gone)
When the user asks for a step that needs something from earlier cells (e.g. `df`)
Then the assistant does not add or run a cell, and replies: "The notebook was restarted, so earlier results are gone. Press Run all in the notebook, then ask me again."

**AC2 — Restart found from an error**
Given the assistant's cell fails with `NameError` for a name an earlier cell defines, because the kernel restarted
When the assistant reacts
Then it gives the same message as AC1 instead of rewriting the earlier setup into a new cell

**AC3 — Nothing is run for the user**
Given AC1 or AC2 happened
When the assistant replies
Then no earlier cell has been re-run and no new cell has been added

**AC4 — Continues after the user re-runs**
Given the user pressed Run all and the cells ran without error
When they ask again
Then the assistant adds only the new step's cell, using the restored variables (STORY-01)

**AC5 — Nothing to restore**
Given the kernel restarted and the notebook has no earlier code cells
When the user asks for a step
Then the assistant proceeds normally, as with an empty notebook (STORY-01 AC5)

**AC6 — Step doesn't need earlier state**
Given the kernel restarted
When the user asks for something that uses nothing from earlier cells (e.g. "what is 2**10?")
Then the assistant proceeds normally without the restart message

## Developer Notes

- **Context & intent:** match Jupyter: the user owns re-running. The point is to stop the assistant's fallback of pasting all setup into a new cell.
- **Likely areas:** kernel status and execution counts in `researchchat/workspace/kernels.py` / `service.py`; `notebook_read` already says "kernel not running" when the kernel is off. The assistant needs a reliable signal that the kernel restarted since cells last ran. *(assumption: verify)*
- **Dev decisions:** how to detect a restart (cells have run numbers but the kernel has no variables, or kernel start time vs. cell run time); the exact place the message comes from (model instructions vs. a fixed tool result).
- **Edge cases:** the kernel is off (not just restarted) — it starts on the next run, same message applies; the user ran only some cells; Run all fails on one cell (the user sees that in the notebook as usual).
- **Testing hints:** run cells defining `df`, press Restart in the panel, ask for `df.describe()`; assert the message is shown and no cell was added or run.

## Out of Scope

- The assistant re-running earlier cells by itself (decided against by the PO).
- A "Run all" button inside the chat message.
- Keeping the kernel alive longer than 30 minutes (possible separate ticket).
- Keeping installed libraries across restarts (see STORY-02 dev notes).

## Dependencies

- STORY-01.

## Open Questions

- None. Answered by the PO on 2026-11-14: the user re-runs cells themselves; the assistant only tells them.
