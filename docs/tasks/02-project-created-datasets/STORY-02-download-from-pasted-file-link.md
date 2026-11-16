# STORY-02: Download a dataset file from a link I paste into the chat

[Epic PRD](../../requirements/02-project-created-datasets/README.md) · [Sprint backlog](README.md)

**Summary:** Download a dataset file from a link I paste into the chat
**Type:** Story | **Epic:** Project-created datasets | **Priority:** High | **Labels:** datasets, download, security | **Components:** assistant, dataset download, Datasets tab
**Story points (suggested):** 8 (**at the limit**) — Complexity H, Uncertainty M, Effort M — fetching from any public website is security-critical, and unlike catalogs there is no declared size, checksum or licence to rely on. If the team's estimate comes out higher, split off AC7 (GitHub page links) into its own story.

## User Story

As a **researcher who found a dataset file on the web**, I want **to paste its link into the chat and have the assistant download it into my project**, so that **I can work with data from sources other than Hugging Face and Zenodo without downloading and uploading it by hand**.

## Background

Today the assistant can only download from Hugging Face and Zenodo (their page links already work). For any other link it says the source isn't supported, and it may then try to recreate the data itself in the notebook (as happened with `Iris.csv` on 2026-11-14). The PO wants to paste a source link and have it downloaded into the shared pool, then loaded like any other dataset.

## Acceptance Criteria

**AC1 — Pasted file link is downloaded**
Given the user pastes `https://example.org/data/iris.csv` and says "download this"
When the assistant starts the download
Then a card appears in the Datasets tab with status `downloading`, then `ready`, with the file name, size and notebook path under `/work/datasets/…`, labelled with the website it came from (`example.org`)

**AC2 — Only links the user gave are downloaded**
Given the user's message contains no link
When the assistant decides it wants data from some website
Then it does not download from any address it came up with itself; it shows the link to the user and asks them to paste it if they want it

**AC3 — Another project already has it**
Given another project downloaded the same link earlier and its file is unchanged
When the user pastes that link in this project
Then the dataset is `ready` at once without downloading again, as catalog datasets are today

**AC4 — Link is a web page, not a file**
Given the user pastes a link that opens a normal web page (e.g. an article)
When the download is tried
Then nothing is saved and the assistant says "This link opens a web page, not a data file. Paste the link to the file itself."

**AC5 — Link can't be reached or is not allowed**
Given the link is broken (404), needs a login, is not `https`, or points to a private/local network address
When the download is tried
Then nothing is saved, the card (if shown) is `failed` with a one-line reason, and the assistant tells the user why

**AC6 — Large file asks first**
Given the file is larger than the size that already asks for approval for catalog downloads
When the download is about to start
Then the user sees the same Download / Skip prompt with the size; when the website doesn't tell the size in advance, the prompt says "size unknown", and the download stops with `failed` if it goes past the project's maximum

**AC7 — GitHub file page links work**
Given the user pastes a GitHub link to a file, e.g. `https://github.com/org/repo/blob/main/iris.csv`
When the assistant downloads it
Then the file's contents are downloaded (not the GitHub web page around it)

**AC8 — No licence is invented**
Given the website gives no licence information
When the card is shown
Then the licence field says "Unknown — check the source" and the assistant does not claim a licence

## Developer Notes

- **Context & intent:** let the user bring their own data source, safely. The user is the only one who may supply the address (AC2).
- **Security is the main risk:** `researchchat/workspace/dataset_sources.py` deliberately never takes URLs from model text and re-checks every redirect for HTTPS and public addresses (SEC1). Keep all of that. The new rule is narrower: a URL is allowed only if it appears verbatim in the user's own message in this chat; the tool should check that, not trust the model. *(assumption: verify how user messages are reachable from the tool)*
- **No catalog metadata:** no declared size, checksum or licence. Size limits must be enforced while streaming (AC6); pool identity likely needs the URL plus a content hash so AC3 doesn't serve a changed file. Dev decision.
- **Likely areas:** `parse_ref` / `UNSUPPORTED_SOURCE` in `dataset_sources.py`, a new source type in `datasets_store.py` (`Source` literal) and the pool index (`dataset_pool.py`), `researchchat/tools/dataset_download.py` description and `SOURCE_NAMES`, card label in `public/panel/src/components/DatasetCard.tsx`. Prefer adding a new source handler over growing the `if host == …` chain (CLAUDE.md Open/Closed).
- **Dev decisions:** how to tell a web page from a data file (content type, extension), GitHub `blob` → raw conversion, the per-file maximum, timeouts.
- **Archives:** a pasted `.zip` downloads packed; unpacking is NB-5.
- **Testing hints:** a local HTTPS test server for happy path and 404; tests for private-address, `http://`, redirect to a private address, oversized stream without a declared size, a URL the model invented (not in the user's message).

## Out of Scope

- Kaggle dataset pages (need the user's Kaggle account): [STORY-05](STORY-05-download-from-kaggle-link.md).
- Links that need the user to log in, and Google Drive / Dropbox share pages.
- Downloading a whole website or folder listing; only the one file the link points to.
- Unpacking archives (NB-5).

## Dependencies

- Uses the NB-3 / NB-4 download and pool machinery. Independent of STORY-01 and STORY-04.

## Open Questions

- None left. Answered by the PO on 2026-11-14: links from any public website are allowed (AC1); the safety checks in AC2 and AC5 still apply.
