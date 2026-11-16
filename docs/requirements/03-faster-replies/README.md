# Epic PRD — Faster assistant replies

**Suggested total:** 16 points + 1-day spike · **Backlog:** [docs/tasks/03-faster-replies/](../../tasks/03-faster-replies/README.md)

## Summary

Make the assistant answer sooner: measure where reply time goes, then cut the biggest delays (tools running one after another, thinking hard on simple messages, long chats resent in full, the notebook's cold start).

## Background

Client feedback (2026-11-14): "The agent calling the tools or thinking is too slow; I want it to respond faster." No timings are recorded today, so the first ticket measures them.

What the code shows (2026-11-14):
- Tools asked for in the same round run one after another (`app.py`: `for c in calls: await run_tool_call(...)`); a search can take ~10 s, a page read ~15 s.
- Every message uses the same thinking effort ("Model default"), even "thanks".
- Every model call resends the whole chat including old page texts (≤ 8,000 chars each) and notebook reads (≤ 12,000), so long chats get slower.
- The notebook (Docker) starts only at the first cell run (up to 60 s allowed) and stops after 30 idle minutes.
- One message may use up to 25 model rounds.

## Requirement Analysis

| Item | Finding |
|---|---|
| Actors | Researcher chatting with the assistant |
| Goal | Get answers sooner, during tool use and thinking |
| Business value | Less waiting, users stay in flow and keep using the app *(assumed)* |
| Rules (stated) | Faster tool use and thinking |
| Rules (assumed) | Answer quality must not drop on hard questions; safety approvals unchanged |
| Data | Reply timings (to measure), chat history size, thinking settings |
| Ambiguities | None left: all trade-offs are dev decisions |

## Estimation Log

| Candidate | Complexity | Uncertainty | Effort | Points | Action |
|---|---|---|---|---|---|
| Make the assistant respond faster | H | H | H | 21 | ✂️ Split (by cause of delay) + spike for the unknowns |
| ↳ SPIKE-01: Measure where time goes | — | — | — | 1 day | Time-boxed |
| ↳ STORY-01: Run tool calls together | M | L | L | 3 | ✅ Keep |
| ↳ STORY-02: Quick answers for simple messages | M | M | M | 5 | ✅ Keep |
| ↳ STORY-03: Keep long chats fast | M | M | M | 5 | ✅ Keep |
| ↳ STORY-04: Warm up the notebook | L | M | L | 3 | ✅ Keep |

Re-estimate and re-order after SPIKE-01.

## Ticket Tree

```
Epic: Faster assistant replies  (total: 16 points + spike)
├── SPIKE-01: Measure where the assistant's reply time goes  (1 day, Highest)
├── STORY-01: Run the assistant's independent tool calls at the same time  (3 pts, High, depends on: —)
├── STORY-02: Answer simple messages quickly without deep thinking  (5 pts, High, depends on: SPIKE-01)
├── STORY-03: Keep replies fast as a chat gets long  (5 pts, Medium, depends on: SPIKE-01)
└── STORY-04: Start the notebook in the background when a chat opens  (3 pts, Medium, depends on: —)
```

## Out of Scope

- Switching to a different AI model or provider.
- Faster internet, search engines or Docker itself.

## Decisions (PO, 2026-11-14)

1. The client sets no time limits. How to optimise and the speed targets are the dev team's choice, based on SPIKE-01; every story must be measurably faster than the SPIKE-01 baseline.
2. The speed trade-offs are dev decisions too: thinking less on simple messages (STORY-02), re-reading old pages in long chats (STORY-03), and starting the notebook early at the cost of memory (STORY-04). Answer quality on hard questions must not drop.

## Open Questions

- None.
