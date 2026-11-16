# STORY-04: Reuse a dataset the project already has instead of creating a copy

[Epic PRD](../../requirements/02-project-created-datasets/README.md) · [Sprint backlog](README.md)

**Summary:** Reuse a dataset the project already has instead of creating a copy
**Type:** Story | **Epic:** Project-created datasets | **Priority:** Medium | **Labels:** datasets, assistant | **Components:** assistant, dataset tools
**Story points (suggested):** 3 — Complexity L, Uncertainty M, Effort L — mostly assistant behaviour (tool descriptions / instructions) plus tests; uncertainty is how reliably the model follows it.

## User Story

As a **researcher asking the assistant for data**, I want **the assistant to use a dataset my project already has when it matches my request**, so that **I don't end up with duplicate or made-up copies of the same data**.

## Background

On 2026-11-14 the `default` project already had the downloaded `hf-scikit-learn--iris` dataset (`ready`). Asked to create an iris dataset, the assistant ignored it and wrote a new `Iris.csv` with notebook code, once even generating random numbers it described as the real Iris data. The PO decided the assistant should reuse what exists.

## Acceptance Criteria

**AC1 — Ready matching dataset is reused**
Given the project has a `ready` dataset `hf-scikit-learn--iris`
When the user asks "create an iris dataset" (or "get me the iris data")
Then the assistant does not download or save a new copy; it replies that the project already has it, gives its notebook path (`/work/datasets/hf-scikit-learn--iris/…`) and loads it from there if the user asked to work with it

**AC2 — Created file is reused too**
Given the project lists a created dataset `Iris.csv` ("Created by myself", see STORY-01)
When the user asks for iris data
Then the assistant uses `/work/Iris.csv` and does not create another file

**AC3 — No match: normal behaviour**
Given the project has no dataset matching the request
When the user asks for iris data
Then the assistant searches and downloads as today, and nothing is reused

**AC4 — Dataset not usable**
Given the matching dataset is `missing` or `failed`
When the user asks for that data
Then the assistant says the existing one is not usable and offers to download it again, instead of silently creating a new file

**AC5 — User explicitly wants a new copy**
Given the project has a `ready` iris dataset
When the user says "make a new iris file anyway" or asks for a different version
Then the assistant creates or downloads it as asked

**AC6 — Several matches**
Given the project has two datasets that match (e.g. a downloaded iris and a created `Iris.csv`)
When the user asks for iris data
Then the assistant names both and asks which to use, without creating a new one

## Developer Notes

- **Context & intent:** avoid duplicates and fabricated data; the project's existing datasets are the first place to look.
- **Affected areas (likely):** assistant instructions and tool descriptions (`researchchat/tools/dataset_list.py`, `dataset_search.py`, `dataset_download.py`, `notebook_run.py`), so the model checks `dataset_list` before searching or writing data. *(assumption: verify against the codebase)*
- **Dev decision:** how "matching" is judged (model judgement over names vs. a simple name check), and whether `dataset_search` returns already-present datasets first.
- **Testing hints:** scripted conversations against a project with `hf-scikit-learn--iris` ready; assert no `dataset_download` call and no new file under `files/`.

## Out of Scope

- Listing created files in the tab (STORY-01).
- Detecting duplicates by file contents.
- Downloading from a pasted source link (see the epic PRD, pending confirmation).

## Dependencies

- AC2 and AC6 need STORY-01 (created files must be listed). AC1, AC3–AC5 can ship without it.

## Open Questions

- None.
