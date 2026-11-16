# Epic PRD — Notebook-style assistant cells

**Suggested total:** 12 points · **Backlog:** [docs/tasks/04-notebook-style-cells/](../../tasks/04-notebook-style-cells/README.md)

## Summary

The assistant should write notebook cells the way a person uses Jupyter: imports once in a setup cell at the top, then small cells that each do one step and use what earlier cells created, instead of a full self-contained script in every cell.

## Background

Client feedback (2026-11-14): "When the agent creates a new cell, it writes the whole code with imports and everything. In Jupyter I put the imports on top, and in each block I just write the function or syntax I need to execute." In the `default` project almost every assistant cell repeats `import pandas as pd` / `import os` and reloads the data; the same iris-loading block appears five times.

Findings while analysing:
- Variables do persist between cells while the kernel runs; the assistant just doesn't rely on them. It can't see which modules are already imported (the variable list it gets leaves modules out).
- The kernel stops after 30 idle minutes and on app restart, wiping variables, which pushes the assistant towards self-contained cells.
- `!pip install scikit-learn` succeeded but the next cell still couldn't import it (three times), another reason cells felt disconnected.

## Requirement Analysis

| Item | Finding |
|---|---|
| Actors | Researcher (writes and runs cells too), the assistant (adds and runs cells) |
| Goals | A notebook that reads as one connected analysis: setup on top, one step per cell |
| Business value | Notebooks the user can follow, edit and re-run; less duplicated code; fewer wasted runs *(assumed)* |
| Rules (stated) | Imports at the top; each later cell holds only the step's own code |
| Rules (assumed) | One step per cell for multi-step requests; the assistant says when it changed the setup cell |
| Data | Notebook cells, kernel variables and imported modules |
| Ambiguities | Resolved: see Decisions |

## Estimation Log

| Candidate story | Complexity | Uncertainty | Effort | Points | Action |
|---|---|---|---|---|---|
| Assistant writes connected, Jupyter-style cells | M | H | H | 13 | ✂️ Split (by business rule) |
| ↳ STORY-01: Build on earlier cells, no repeated setup | M | M | M | 5 | ✅ Keep |
| ↳ STORY-02: Imports in one setup cell at the top | M | M | M | 5 | ✅ Keep |
| ↳ STORY-03: Re-run earlier cells after a restart | L | M | L | 3 | Re-scoped after PO decision ↓ |
| ↳ STORY-03: Tell the user to re-run after a restart | L | L | L | 2 | ✅ Keep |

## Ticket Tree

```
Epic: Notebook-style assistant cells  (total: 12 points)
├── STORY-01: Make the assistant's cells build on earlier cells instead of repeating setup  (5 pts, High, depends on: —)
├── STORY-02: Keep all imports in one setup cell at the top of the notebook  (5 pts, Medium, depends on: STORY-01)
└── STORY-03: Tell the user to re-run the notebook after a kernel restart  (2 pts, Medium, depends on: STORY-01)
```

## Decisions (PO, 2026-11-14)

1. The assistant may add imports to a setup cell the user wrote, without asking, and says what it added (STORY-02).
2. After a kernel restart the user re-runs the cells themselves, as in Jupyter; the assistant only tells them (STORY-03).

## Open Questions

- None. STORY-01's "one step per cell" assumption is still open for the PO to confirm or reject.
