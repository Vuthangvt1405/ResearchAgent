# STORY-02: Keep all imports in one setup cell at the top of the notebook

[Epic PRD](../../requirements/04-notebook-style-cells/README.md) · [Sprint backlog](README.md)

**Summary:** Keep all imports in one setup cell at the top of the notebook
**Type:** Story | **Epic:** Notebook-style assistant cells | **Priority:** Medium | **Labels:** notebook, assistant | **Components:** assistant, notebook tools
**Story points (suggested):** 5 — Complexity M, Uncertainty M, Effort M — the assistant can today only add cells at the end, so it needs a way to add to the top cell, plus rules for not overwriting the user's code.

## User Story

As a **researcher using the project notebook with the assistant**, I want **all imports kept together in one setup cell at the top**, so that **I can see at a glance which libraries the analysis uses and re-run the notebook from the top in order**.

## Background

In the user's Jupyter habit, imports sit in the first cell and other cells hold only the work. Today the assistant scatters imports across every cell it adds (see STORY-01). Once it stops repeating imports, new imports need a home: the setup cell at the top.

## Acceptance Criteria

**AC1 — Setup cell is created**
Given the notebook has no imports cell at the top
When the assistant needs its first import
Then it adds a cell at the top of the notebook containing only imports, runs it, and puts the work in a separate cell below

**AC2 — New import goes to the setup cell**
Given the top setup cell contains `import pandas as pd` and the assistant now needs matplotlib
When it adds a plotting cell
Then `import matplotlib.pyplot as plt` is added to the setup cell, the setup cell is run again, and the plotting cell contains no import

**AC3 — No duplicates in the setup cell**
Given the setup cell already contains `import numpy as np`
When the assistant needs numpy again
Then the setup cell is unchanged

**AC4 — The user sees what changed**
Given the assistant added an import to the setup cell
When it replies in the chat
Then the reply says which import it added to the setup cell

**AC5 — Setup cell the user wrote**
Given the user wrote the top imports cell themselves
When the assistant needs a new import
Then it adds the import to the user's cell without asking, leaves the rest of that cell unchanged, re-runs it, and says in its reply which import it added

**AC6 — Installing a library**
Given the assistant needs a library that isn't installed
When it installs it
Then the install happens once (its own cell or the setup cell, not repeated in later cells), and the following cells can import it without a "No module named …" error

## Developer Notes

- **Context & intent:** one place for dependencies, so "Run all" from the top works and the notebook reads cleanly.
- **Likely areas:** `researchchat/tools/notebook_run.py` only appends a cell at the end (`run_for_model` in `researchchat/workspace/service.py`); the notebook service already has `add_cell` with a position, `update_cell` and `run_cell`, so the assistant probably needs a small tool or option to update/run the setup cell. Keep the existing risky-code approval for anything it runs. *(assumption: verify)*
- **Install bug seen (AC6):** in the `default` project `!pip install scikit-learn` succeeded but the next cell still raised `ModuleNotFoundError: sklearn`, three times. The kernel runs with a read-only root and `HOME=/tmp`, so user installs land in `/tmp/.local`, which likely isn't on the running kernel's import path. Dev to confirm and fix; also note installs vanish when the kernel restarts (tmpfs).
- **Dev decisions:** how the assistant recognises "the setup cell" (first code cell with only imports?), whether to keep imports sorted, whether to mark the setup cell.
- **Edge cases:** the user deleted or moved the setup cell; a setup cell that also has non-import code; the notebook was edited in the panel at the same time (stale version).
- **Testing hints:** start from an empty notebook, ask for a pandas step then a plot; assert one top cell with both imports and no imports below.

## Out of Scope

- Reorganising imports already scattered in existing cells.
- Pinning library versions or a requirements file.

## Dependencies

- STORY-01 (the assistant must first stop repeating imports).

## Open Questions

- None. Answered by the PO on 2026-11-14: the assistant may add imports to a setup cell the user wrote, without asking, and tells the user (AC5).
