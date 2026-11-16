# STORY-02: Show next-step suggestions only when the user is likely to need them

[Epic PRD](../../requirements/05-next-step-suggestions/README.md) · [Sprint backlog](README.md)

**Summary:** Show next-step suggestions only when the user is likely to need them
**Type:** Story | **Epic:** Next-step suggestions for beginners | **Priority:** High | **Labels:** chat, assistant, ux | **Components:** assistant, chat
**Story points (suggested):** 5 — Complexity M, Uncertainty H, Effort L — few rules, but "needs help now" is a judgement; it has to be checked against a set of real conversation moments and tuned.

## User Story

As a **beginner researcher chatting with the assistant**, I want **suggestions to appear only at moments when I'm likely to need a next step**, so that **they help me when I'm stuck and stay out of the way the rest of the time**.

## Background

Client feedback (2026-11-14): "I don't want suggestions after every message. The suggestion is smart: it knows when I need a suggestion." The client doesn't want to define the rules; they want the app to judge. The rules below are the PO's proposal of what "needs a suggestion" means, so it can be built and tested. They are marked *(assumption)* and can be changed without the client's input.

## Acceptance Criteria

**AC1 — After a finished step** *(assumption)*
Given the assistant just finished a step with a natural next step (a dataset finished downloading, a notebook cell ran and showed results, an analysis question was answered)
When the reply is shown
Then pills appear (STORY-01)

**AC2 — After something went wrong** *(assumption)*
Given the reply reports an error (a cell failed, a download failed, "Error: …")
When it is shown
Then pills appear, and at least one helps recover (e.g. "Try a smaller part of the dataset.")

**AC3 — When the user seems stuck** *(assumption)*
Given the user's message is a short request for direction, such as "what now?", "next?", "help", "I don't know what to do"
When the assistant replies
Then pills appear

**AC4 — The reply asked a choice** *(assumption)*
Given the reply ends by asking the user to choose (e.g. "Do you want a bar chart or a line chart?")
When it is shown
Then pills appear with the likely answers (e.g. "Bar chart.", "Line chart.")

**AC5 — No pills when the next step is already clear** *(assumption)*
Given the reply tells the user exactly one thing to do (e.g. "Press Run all, then ask me again.", "Wait for the download to finish.") or a Run / Skip or Download / Skip approval is showing
When it is shown
Then no pills appear

**AC6 — No pills for small talk** *(assumption)*
Given the user's message is a greeting, thanks or goodbye ("thanks!", "ok", "bye")
When the assistant replies
Then no pills appear

**AC7 — No repeats** *(assumption)*
Given pills were shown for the previous reply
When the next reply is also due for pills
Then none of the new pills repeats a suggestion the user already saw or already did in this chat

**AC8 — Judged on a fixed test set**
Given a test set of at least 30 labelled conversation moments (show / don't show), covering AC1–AC6
When the app's decisions are compared with the labels
Then at least 90% match *(assumption: target to tune)*, and every AC5 "approval is showing" moment is a "don't show"

## Developer Notes

- **Context & intent:** fewer, better-timed suggestions. When in doubt, don't show: a missing suggestion costs less than noise. *(assumption)*
- **Likely areas:** the same place STORY-01 produces suggestions (after the reply in `app.py` `on_message`); the decision can use what tools ran this turn, whether an approval is pending, and the last user and assistant messages.
- **Dev decisions:** rule-based checks (tool results, pending approvals) vs. letting the suggestion model also answer "is a suggestion useful now?" (likely a mix: hard rules for AC5, model judgement for AC1–AC4); how to build and keep the test set.
- **Tuning idea (not required):** if the user ignores pills several replies in a row, show them less often. Tune in implementation; not an AC.
- **Edge cases:** a reply that both finished a step and asks a question (AC4 wins: answers as pills); a long tool-heavy turn that ends in an approval (AC5 wins: no pills).
- **Testing hints:** build the labelled test set from real chats in the `default` project (download done, cell error, "what now?", "thanks", "press Run all").

## Out of Scope

- What the pills say and how they behave (STORY-01).
- Starting suggestions for a new chat (STORY-03, always shown).
- Learning per-user habits across chats.

## Dependencies

- STORY-01 (the pills).

## Open Questions

- None. The client delegated the "when" rules to the PO (2026-11-14); the rules above are PO assumptions that can be changed in review.
