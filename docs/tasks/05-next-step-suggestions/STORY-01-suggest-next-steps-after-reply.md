# STORY-01: Show three clickable next-step pills above the message box

[Epic PRD](../../requirements/05-next-step-suggestions/README.md) · [Sprint backlog](README.md)

**Summary:** Show three clickable next-step pills above the message box
**Type:** Story | **Epic:** Next-step suggestions for beginners | **Priority:** High | **Labels:** chat, onboarding, assistant, ux | **Components:** chat, assistant
**Story points (suggested):** 5 — Complexity M, Uncertainty M, Effort M — pills above the message box that fill it on click (custom chat UI work), and suggestions that fit the current situation (chat, notebook, datasets).

## User Story

As a **beginner researcher who doesn't yet know what to ask next**, I want **three short suggested next steps shown as pills just above the message box, based on what just happened**, so that **I can pick one, adjust it if I want, and send it instead of getting stuck**.

## Background

Today a reply ends with nothing after it; the only guidance is the greeting "Hi! What would you like to research today?". Beginners often don't know the next sensible step (e.g. after downloading a dataset: look at it, clean it, plot it). The client wants three one-sentence recommendations that depend on the current context.

This story covers **what** the pills say and **how** they behave. **When** they appear is decided by [STORY-02](STORY-02-suggest-only-when-needed.md) (the client wants them only when the user needs them, not after every reply). Until STORY-02 ships, pills appear only after a reply in which the assistant finished an action (downloaded data, ran a notebook cell, or hit an error) *(assumption: simple interim rule)*.

## Acceptance Criteria

**AC1 — Three pills appear**
Given the assistant has finished a reply and suggestions are due (see STORY-02)
When the reply is shown
Then exactly three suggestions appear as pills just above the message box, each one sentence written as something the user could say (e.g. "Show the first 10 rows of the iris data."); a sentence too long for its pill is shown cut off with "…" (see STORY-04)

**AC2 — Suggestions fit what just happened**
Given the assistant just downloaded the iris dataset into the project
When the pills appear
Then they are about that dataset (e.g. look at it, summarise it, plot it), not generic questions unrelated to the chat

**AC3 — Click puts the text in the message box**
Given pills are shown and the message box is empty
When the user clicks one
Then its full text appears in the message box with the cursor at the end, nothing is sent, and from then on it is ordinary text, exactly as if the user had typed it: they can edit it, delete it, or press Send (or Enter)

**AC4 — Hidden while the message box has text**
Given pills are shown
When the message box gets any text, whether typed or put there by clicking a pill
Then the pills disappear and can't be clicked; when the message box is emptied again without sending, the same three pills come back

**AC5 — Pills match the latest reply**
Given pills are shown
When the user sends any message
Then the pills disappear while the assistant works; after the next reply, new pills appear only if suggestions are due (STORY-02)

**AC6 — Suggestions are things the app can do**
Given the project has no datasets and the notebook is empty
When pills appear
Then none of them refers to data, files or variables that don't exist, and none asks for something the app can't do (e.g. no "download from Kaggle" until that feature exists)

**AC7 — Same language as the user**
Given the user writes in Vietnamese
When pills appear
Then they are in Vietnamese

**AC8 — Normal safety rules still apply**
Given a message that came from a pill leads the assistant to run risky code or start a large download
When that happens
Then the usual Run / Skip or Download / Skip approval is shown, exactly as for a typed message

## Developer Notes

- **Context & intent:** a guide for beginners; suggestions should teach the natural next step of an analysis (inspect → clean → explore → model → explain), not advertise features.
- **Likely areas:** `app.py` `on_message` (the reply is sent at the end; suggestions are produced after it). Chainlit's built-in `cl.Action` buttons sit under a message and run a server callback; they can't fill the message box, so this probably needs a small custom element plus `public/custom.js` to show pills above the composer, set its text, and watch whether it is empty. *(assumption: verify against the codebase and Chainlit version)*
- **Context to use:** the last few messages, what tools ran this turn (download, notebook run, search), the project's datasets (`dataset_list`) and notebook state. Don't send file contents beyond what the model already saw.
- **Dev decisions:** generate suggestions with a separate small model call after the reply vs. asking the main model to append them; how many past messages to use; caching.
- **Visible effect to keep small:** the reply itself must not wait for the suggestions; they appear right after it. Target: within 3 s of the reply finishing *(assumption: tune in implementation)*.
- **Security:** suggestion text comes from the model and may echo text from web pages or datasets; show it as plain text only (no HTML or links). Sending goes through the normal message path, so approvals still apply (AC8).
- **Edge cases:** narrow/mobile windows (pills wrap, stay above the box); the user clicks while a reply is still running (no pills shown then); suggestion generation fails (show no pills, change nothing else).
- **Testing hints:** scripted turns: after a download, after a notebook error, a Vietnamese conversation, an empty project; assert 3 pills, language, no references to missing data; UI test for click → box filled, typing hides pills, emptying brings them back.

## Out of Scope

- Deciding when pills are shown: [STORY-02](STORY-02-suggest-only-when-needed.md).
- Pills at the very start of a chat: [STORY-03](STORY-03-suggest-first-steps-at-chat-start.md).
- Turning pills off: [STORY-05](STORY-05-turn-suggestions-on-or-off.md).
- Reading a long pill by hovering: [STORY-04](STORY-04-scroll-long-suggestion-on-hover.md).
- Tutorials, tooltips or a guided tour of the app; pills inside the notebook panel.

## Dependencies

- None. Release together with STORY-02 if possible; otherwise use the interim rule in Background.

## Open Questions

- None. Answered by the PO on 2026-11-14: pills sit above the message box; a click puts the text in the box as ordinary text; pills hide while the box has text and come back when it is emptied; the user sends.
