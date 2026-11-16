# STORY-02: Answer simple messages quickly without deep thinking

[Epic PRD](../../requirements/03-faster-replies/README.md) · [Sprint backlog](README.md)

**Summary:** Answer simple messages quickly without deep thinking
**Type:** Story | **Epic:** Faster assistant replies | **Priority:** High | **Labels:** performance, thinking | **Components:** agent loop, settings
**Story points (suggested):** 5 — Complexity M, Uncertainty M, Effort M — the app must judge which messages are simple, and answer quality on harder ones must not drop.

## User Story

As a **researcher sending a quick message (a greeting, a short follow-up, a simple fact)**, I want **the assistant to answer it right away instead of thinking at length first**, so that **short exchanges feel instant and I keep my flow**.

## Background

Every message today uses the same thinking effort ("Model default" unless the user changes it in settings), so "thanks!" or "show the first 5 rows" waits for the same reasoning as a hard research question. Users can set "Thinking effort" to Off or Low, but beginners don't know that setting exists.

## Acceptance Criteria

**AC1 — Simple message, quick answer**
Given "Thinking effort" is left at its default
When the user sends a simple message (e.g. "thanks", "what is 2+2?", "show the first 5 rows of df")
Then the first words of the answer appear clearly sooner than in the SPIKE-01 baseline for the same message (the dev team sets the target in the spike report)

**AC2 — Hard question still gets full thinking**
Given "Thinking effort" is left at its default
When the user asks a multi-step research or analysis question (e.g. "compare these 3 datasets and recommend one for regression")
Then the assistant thinks as it does today, and its answer quality on the SPIKE-01 test prompts is no worse than before (judged side by side by the team)

**AC3 — User's own choice wins**
Given the user picked a thinking effort in settings (Off, Low, Medium, High)
When they send any message
Then that effort is used for every message, as today

**AC4 — Thinking display unchanged**
Given "Show thinking" is on
When a message is answered quickly
Then no empty thinking box is shown; when thinking happens, it is shown as today

**AC5 — Clear setting label**
Given the user opens the chat settings
When they look at "Thinking effort"
Then the default option is labelled "Automatic (quick for simple messages)" *(assumption: wording)*

## Developer Notes

- **Context & intent:** adaptive thinking: little or none for small messages, full for hard ones. When unsure, think (quality first). *(assumption)*
- **Likely areas:** `reasoning_body` in `researchchat/settings.py` and `[thinking]` in `config.toml` (default level, labels); `on_message` in `app.py` where `extra_body` is built per round.
- **Dev decisions:** how to classify a message as simple (rules: length, small-talk words, follow-up without tools; or a cheap classifier call); whether later rounds in a tool-heavy turn may think less than the first; whether a faster model is used for simple messages.
- **Edge cases:** a short message that is actually hard ("why?" after a complex answer); non-English messages; tool rounds.
- **Testing hints:** the SPIKE-01 prompt set; measure time to first words before/after; side-by-side quality check on the hard prompts.

## Out of Scope

- Changing the model or provider.
- Removing the "Thinking effort" setting.

## Dependencies

- SPIKE-01 (baseline and quality check prompts).

## Open Questions

- None. Dev decision (client, 2026-11-14): how much to think on simple messages; AC2 still protects quality on hard questions.
