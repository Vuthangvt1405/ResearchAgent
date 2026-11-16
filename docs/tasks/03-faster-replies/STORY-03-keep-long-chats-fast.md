# STORY-03: Keep replies fast as a chat gets long

[Epic PRD](../../requirements/03-faster-replies/README.md) · [Sprint backlog](README.md)

**Summary:** Keep replies fast as a chat gets long
**Type:** Story | **Epic:** Faster assistant replies | **Priority:** Medium | **Labels:** performance, context | **Components:** agent loop
**Story points (suggested):** 5 — Complexity M, Uncertainty M, Effort M — shrinking what is resent each round without making the assistant lose track of the conversation.

## User Story

As a **researcher in a long chat with many searches and notebook runs**, I want **replies late in the chat to come about as fast as early ones**, so that **I don't have to start a new chat just because the old one got slow**.

## Background

Each time the model is called, the app sends the whole chat again, including every old tool result: full page texts (up to 8,000 characters each), notebook reads (up to 12,000) and search results. A long research chat can carry dozens of these, so every round gets slower (and costs more) as the chat grows, even when the old results are no longer needed.

## Acceptance Criteria

**AC1 — Late replies stay fast**
Given a chat with 20 earlier turns that used web search, page reading and the notebook
When the user asks a new simple question
Then the time to first words is close to the same question asked in a fresh chat (the dev team sets the allowed difference in the spike report)

**AC2 — Recent work is remembered**
Given the user asks about a page or result from the last 3 turns *(assumption)*
When the assistant answers
Then it uses that content without reading or running it again

**AC3 — Older work can be recovered**
Given the user asks about a page the assistant read much earlier in the chat
When the assistant needs its details
Then it still knows the page's title, address and what it was used for, and reads it again if it needs the full text

**AC4 — Conversation itself is kept**
Given a long chat
When the assistant answers
Then everything the user and assistant said to each other (not tool results) is still taken into account

**AC5 — No visible change to the chat**
Given the chat has been shortened behind the scenes
When the user scrolls up
Then every earlier message and tool step is still shown as before

## Developer Notes

- **Context & intent:** resend less, not forget more: big old tool outputs are the cost, the conversation is the value.
- **Likely areas:** `history` in `app.py` `on_message` (tool results are appended as `{"role": "tool", ...}` and resent every round); the model-facing results built in `researchchat/tools/*.py`.
- **Dev decisions:** which old results to shorten and how (replace with a one-line summary + URL/cell id), how many recent turns stay full, whether to use the provider's prompt caching so an unchanged prefix is cheaper and faster.
- **Edge cases:** a notebook read that is still the latest state; tool results the model is mid-way through using in the current turn (never shorten those).
- **Testing hints:** a scripted 20-turn chat; compare time to first words and request size at turn 1 vs. turn 20, before and after.

## Out of Scope

- Summarising the user's own messages.
- Saving chats between app restarts.

## Dependencies

- SPIKE-01 (how much of the delay this actually is).

## Open Questions

- None. Dev decision (client, 2026-11-14): when an old page may be re-read instead of kept in full; AC2–AC4 still apply.
