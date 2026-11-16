# STORY-01: Run the assistant's independent tool calls at the same time

[Epic PRD](../../requirements/03-faster-replies/README.md) · [Sprint backlog](README.md)

**Summary:** Run the assistant's independent tool calls at the same time
**Type:** Story | **Epic:** Faster assistant replies | **Priority:** High | **Labels:** performance, tools | **Components:** agent loop, tools
**Story points (suggested):** 3 — Complexity M, Uncertainty L, Effort L — one loop change, but tool steps, progress and result order must stay correct.

## User Story

As a **researcher asking a question that needs several searches or page reads**, I want **the assistant to do those lookups at the same time instead of one after another**, so that **I get my answer sooner**.

## Background

When the model asks for several tools in one round (e.g. three web searches, or reading four pages), the app runs them one by one and waits for each before starting the next. A search can take up to about 10 s and a page read up to about 15 s, so four page reads can mean a minute of waiting that could be the time of the slowest one.

## Acceptance Criteria

**AC1 — Lookups run together**
Given the model asks for 3 web searches in the same round
When they run
Then all 3 start at once, and the round takes about as long as the slowest of the 3, not the sum of all 3 (the dev team sets the exact check)

**AC2 — Steps still shown clearly**
Given several tools run at the same time
When the user opens the progress group
Then each tool still has its own step with its own title and result, listed in the order the model asked for them

**AC3 — One failure doesn't stop the others**
Given 3 page reads run together and one site times out
When the round finishes
Then the other 2 results are used, and the failed step shows its usual error message ("The site took too long to respond.")

**AC4 — Notebook code still runs in order**
Given the model asks to run 2 notebook cells in the same round
When they run
Then they run one after the other in the order asked, as today (the notebook depends on order)

**AC5 — Approvals still work**
Given one of the tools needs the user's approval (risky code, large download) while others run
When the approval is shown
Then the other tools carry on, and the approval behaves exactly as today (Run / Skip, Download / Skip)

## Developer Notes

- **Likely areas:** `app.py` `on_message` loops `for c in calls: await run_tool_call(c, progress)`; `run_tool_call` in `researchchat/tools/__init__.py` opens a `cl.Step` per call; `Progress` in `researchchat/progress.py` shows the current activity label.
- **Dev decisions:** which tools may run together (searches, page reads, dataset search/list: yes; `notebook_run`, `dataset_download`, `dataset_delete`: keep in order, they change state); a cap on how many run at once (e.g. 4) to be polite to search engines.
- **Edge cases:** tool results must be added to the history in the model's order with the right `tool_call_id`; the progress label when several things are happening ("Reading 3 pages…").
- **Security:** unchanged; each tool keeps its own checks (public URLs only, approvals).
- **Testing hints:** fake tools that sleep 2 s each; assert 3 together take ~2 s, results keep order, one raising doesn't drop the others.

## Out of Scope

- Making a single search or page read faster.
- Changing which tools the model chooses.

## Dependencies

- None (SPIKE-01 numbers help show the gain).

## Open Questions

- None.
