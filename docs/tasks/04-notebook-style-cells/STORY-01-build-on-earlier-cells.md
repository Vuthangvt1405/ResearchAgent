# STORY-01: Make the assistant's cells build on earlier cells instead of repeating setup

[Epic PRD](../../requirements/04-notebook-style-cells/README.md) · [Sprint backlog](README.md)

**Summary:** Make the assistant's cells build on earlier cells instead of repeating setup
**Type:** Story | **Epic:** Notebook-style assistant cells | **Priority:** High | **Labels:** notebook, assistant, ux | **Components:** assistant, notebook tools
**Story points (suggested):** 5 — Complexity M, Uncertainty M, Effort M — mostly assistant behaviour, but the assistant needs to know what earlier cells already set up, and model behaviour needs scripted checks.

## User Story

As a **researcher using the project notebook with the assistant**, I want **each cell the assistant adds to contain only the new step, using the imports and variables earlier cells already created**, so that **my notebook reads like one connected analysis I can follow, edit and re-run, instead of a pile of copy-pasted scripts**.

## Background

Today every cell the assistant adds is a self-contained script: it starts with `import pandas as pd`, `import os`, reloads or recreates the data, and only then does the new step. In the `default` project (2026-11-14) almost every assistant cell begins with the same imports, and the same "load iris" block appears in five cells. In a normal Jupyter notebook, imports and data loading happen once near the top, and later cells just use `df`, `plt`, etc.

## Acceptance Criteria

**AC1 — No repeated imports**
Given an earlier cell has run `import pandas as pd` and the kernel is still running
When the assistant adds a cell that uses pandas
Then the new cell does not contain `import pandas as pd` (or any other import already done in this kernel)

**AC2 — Existing variables are reused**
Given an earlier cell created a DataFrame `df` and the kernel is still running
When the user asks "show the mean of each column"
Then the assistant's new cell uses `df` directly (e.g. `df.mean(numeric_only=True)`) and does not reload or recreate the data

**AC3 — One step per cell**
Given the user asks "load the iris data, clean it and plot sepal length"
When the assistant does the work
Then it adds separate cells for load, clean and plot, each containing only its own step, in that order

**AC4 — Cell fails because something is missing**
Given the assistant's cell fails with `NameError` or `ModuleNotFoundError` for a name earlier cells were supposed to provide
When the assistant fixes it
Then it fixes the root cause (adds the missing import or step per STORY-02 / STORY-03) and re-runs, instead of copying all earlier setup into a new cell

**AC5 — First cell in an empty notebook**
Given the notebook has no cells and the kernel has no variables
When the assistant adds its first cell
Then that cell holds the needed imports (and data loading if asked); later cells follow AC1–AC3

**AC6 — User's own cells count too**
Given the user wrote and ran a cell `import numpy as np` / `arr = np.arange(10)` themselves
When the assistant adds a cell working on `arr`
Then it uses `np` and `arr` without re-importing or recreating them

**AC7 — Short, readable cells**
Given the assistant adds a cell for one step
When the user looks at it
Then it contains no leftover diagnostic code from other steps (e.g. `print(os.getcwd())`, file-existence checks) unless the user asked for it

## Developer Notes

- **Context & intent:** the user wants the classic notebook style: setup once, then small cells that build on state. The assistant currently writes defensive, self-contained code because it doesn't know what the kernel already has.
- **What the assistant can see today (likely):** `researchchat/tools/notebook_read.py` returns cells, outputs and variable names, but `VARIABLES_EXPR` in `researchchat/workspace/kernels.py` deliberately drops modules, so the assistant can't tell `pd` is already imported. Giving it imported modules (name → module) is a likely fix. It also only sees this if it calls `notebook_read`; consider including a short kernel summary in `notebook_run` results. *(assumption: verify against the codebase)*
- **Instructions:** the `notebook_run` tool description and `[chat].system_prompt` in `config.toml` are where the style rule probably lives ("one step per cell, reuse existing imports/variables").
- **Dev decisions:** whether to strip duplicate imports automatically or only instruct the model; how much kernel state to show the model each turn.
- **Edge cases:** an import under an alias (`import pandas as pandas_lib`); a variable overwritten by a later cell; very long notebooks where `notebook_read` is trimmed.
- **Testing hints:** scripted conversations against a kernel with `pd` and `df` defined; assert the new cell's source has no repeated import and references `df`. Reproduce with the `default` project.

## Out of Scope

- Moving imports into one top cell: [STORY-02](STORY-02-keep-imports-in-setup-cell.md).
- What to do when the kernel restarted and variables are gone: [STORY-03](STORY-03-tell-user-after-restart.md).
- Tidying up the user's existing cells.
- How code blocks are shown in the chat.

## Dependencies

- None.

## Open Questions

- None. *(assumption: AC3's "one step per cell" applies to every multi-step request; confirm if you prefer fewer, bigger cells)*
