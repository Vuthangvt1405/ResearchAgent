# STORY-05: Download a Kaggle dataset from a pasted Kaggle link

[Epic PRD](../../requirements/02-project-created-datasets/README.md) · [Sprint backlog](README.md)

**Summary:** Download a Kaggle dataset from a pasted Kaggle link
**Type:** Story | **Epic:** Project-created datasets | **Priority:** Medium | **Labels:** datasets, download, kaggle | **Components:** assistant, dataset download, settings
**Story points (suggested):** 8 (**at the limit**) — Complexity M, Uncertainty H, Effort M — Kaggle needs the user's own account to download, which this app has never stored. Recommend a 1-day **spike** first (how Kaggle downloads work for this app, where the account key would live); re-estimate after it.

## User Story

As a **researcher who found a dataset on Kaggle**, I want **to paste its Kaggle link and have it downloaded into my project**, so that **I can use the many datasets that are only on Kaggle (for example `vikrishnan/iris-dataset`)**.

## Background

Kaggle is where many classic datasets live; the assistant even named Kaggle's Iris dataset when it recreated `Iris.csv` on 2026-11-14. Today Kaggle links are refused ("Downloads work for Hugging Face and Zenodo datasets only"). Unlike Hugging Face and Zenodo, Kaggle only allows downloads for a signed-in Kaggle account.

## Acceptance Criteria

**AC1 — Kaggle link is downloaded**
Given the user has connected their Kaggle account and pastes `https://www.kaggle.com/datasets/vikrishnan/iris-dataset`
When they ask the assistant to download it
Then a card labelled "Kaggle" appears in the Datasets tab, goes `downloading` → `ready`, and shows the files, size, licence from Kaggle and the `/work/datasets/…` paths

**AC2 — No Kaggle account connected**
Given the user has not connected a Kaggle account
When they paste a Kaggle link and ask to download it
Then nothing is downloaded and the assistant replies "To download from Kaggle, connect your Kaggle account in Settings first." with a pointer to where that is

**AC3 — Account key stays private**
Given a Kaggle account is connected
When the user, the assistant or notebook code looks at chat messages, tool results, notebook cells, logs or the project folder
Then the Kaggle key does not appear anywhere in them

**AC4 — Kaggle refuses the download**
Given the dataset needs the user to accept rules on Kaggle first, is private, or no longer exists
When the download is tried
Then the card is `failed` with a one-line reason (e.g. "Accept this dataset's rules on kaggle.com first") and the assistant passes it on

**AC5 — Shared with other projects**
Given another project already downloaded the same Kaggle dataset version
When this project asks for it
Then it is `ready` at once, without downloading again

**AC6 — Disconnect**
Given a Kaggle account is connected
When the user disconnects it in Settings
Then the key is removed and later Kaggle downloads in all of the user's projects behave as in AC2; already-downloaded datasets stay

**AC7 — One account for all projects**
Given the user connected their Kaggle account while in project A
When they paste a Kaggle link in project B
Then the download works without connecting again

## Developer Notes

- **Context & intent:** first source that needs the user's credentials. Everything else in the dataset flow sends no tokens (`USER_AGENT` note in `researchchat/workspace/dataset_sources.py`, A1/SEC14); this story changes that for Kaggle only.
- **Spike first:** confirm Kaggle's download API for datasets, rate limits, how versions are identified (for pool reuse, AC5), and how rules-acceptance errors look.
- **Likely areas:** `parse_ref` and the `UNSUPPORTED_SOURCE` error in `dataset_sources.py` (Kaggle is already named there as unsupported), a new source handler, `Source` literal in `datasets_store.py`, pool index, a settings place for the key, card label in `DatasetCard.tsx`.
- **Security:** the key is a secret: never pass it to the model, the kernel container or the project folder; never log it. Only the download code on the server uses it.
- **Dev decisions:** where the key is stored, how the Settings screen looks, Kaggle competitions vs. datasets (datasets only here).
- **Testing hints:** mock Kaggle API responses for success, 401/403 (no account / rules not accepted), 404; a test that the key never appears in tool results or notebook output.

## Out of Scope

- Kaggle competitions, notebooks and models.
- Searching Kaggle from the assistant (`dataset_search`); only pasted links.
- Other sites that need a login.

## Dependencies

- Spike (1 day) before implementation. Reuses STORY-02's "user gave this link" rule if that lands first, but does not require it.

## Open Questions

- [x] Each user connects their own Kaggle account, once, in Settings (PO, 2026-11-14).
- [x] A connected Kaggle account is used for all of that user's projects (PO, 2026-11-14).
