# SPIKE-01: Measure where the assistant's reply time goes

[Epic PRD](../../requirements/03-faster-replies/README.md) · [Sprint backlog](README.md)

**Summary:** Measure where the assistant's reply time goes
**Type:** Spike (time-box: 1 day) | **Epic:** Faster assistant replies | **Priority:** Highest | **Labels:** performance, spike | **Components:** agent loop, tools
**Story points (suggested):** — (time-boxed, not pointed)

## Goal

Get baseline numbers so the stories in this epic have real targets and the team fixes the biggest delay first. Today nobody knows how much of a slow reply is model thinking, tool work (search, page reading, notebook), or resending a long chat.

## Questions to answer

1. For each reply: time to first visible activity, time to first words of the answer, total time.
2. Per model round: time spent thinking vs. writing; how many rounds a typical message uses.
3. Per tool call: time for `web_search`, `read_page`, `notebook_run` (incl. a cold notebook start), `dataset_*`.
4. How round time grows as a chat gets longer (size of what is resent each round).
5. How much the "Thinking effort" setting (Off / Low / Model default) changes time and answer quality on the same questions.

## Method (hints)

- Add temporary timing logs around `stream_round` and `run_tool_call` in `app.py` / `researchchat/tools/__init__.py`; the progress group already measures total seconds (`researchchat/progress.py`).
- Run a fixed set of ~10 prompts: a greeting, a fact question, a question needing 1 search, one needing 3+ searches and page reads, a notebook task on a cold and a warm kernel, and the same prompts again after a long chat.

## Output

- A short report in `docs/research/faster-replies-baseline.md`: a table of the numbers above, the top 3 delays, and the speed targets the dev team sets for STORY-01 to STORY-04 (the client leaves targets and methods to the dev team).
- Re-estimate STORY-01 to STORY-04 with the numbers.

## Out of Scope

- Changing behaviour; this spike only measures.
