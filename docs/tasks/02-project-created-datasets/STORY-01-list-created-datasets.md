# STORY-01: Show data files created in the notebook in the Datasets tab

[Epic PRD](../../requirements/02-project-created-datasets/README.md) · [Sprint backlog](README.md)

**Summary:** Show data files created in the notebook in the Datasets tab
**Type:** Story | **Epic:** Project-created datasets | **Priority:** High | **Labels:** datasets, notebook, panel, ux | **Components:** Datasets tab, notebook, assistant
**Story points (suggested):** 5 — Complexity M, Uncertainty L, Effort M — a new kind of dataset entry (no catalog, no pool link) that must behave correctly for duplicates, removal and delete; product questions are now answered.

## User Story

As a **researcher working in a project**, I want **every data file created in my notebook, by the assistant or by my own code, to show up in the Datasets tab**, so that **I can see what data my project has, find its path, and load it again without asking where the file went**.

## Background

Today the Datasets tab only lists datasets downloaded from a catalog (HuggingFace, Zenodo). When the user asks "create an iris dataset", the assistant often writes the file with notebook code (`df.to_csv('Iris.csv')`). The file exists in the project folder (`workspaces/default/files/Iris.csv`, seen by the kernel as `/work/Iris.csv`), but nothing tells the Datasets tab about it, so the user sees "it says it created the dataset, but it isn't there".

Seen in the `default` project on 2026-11-14: the assistant re-created `Iris.csv` in about five cells, then ran three "does the file exist?" cells, because neither it nor the user could see the file in the panel. This is a missing capability, not a regression.

## Acceptance Criteria

**AC1 — File created by the assistant appears**
Given a project whose Datasets tab does not list `Iris.csv`
When the assistant runs notebook code that saves a data file (e.g. `Iris.csv`) in the project's working folder
Then within the same assistant turn the Datasets tab shows a card for it with its name, size, `ready` status and notebook path (`/work/Iris.csv`), without reloading the page

**AC2 — File created by the user's own code appears**
Given a project whose Datasets tab does not list `results.csv`
When the user runs a notebook cell themselves that saves `results.csv` in the working folder
Then after the cell finishes the Datasets tab shows a card for `results.csv`, exactly as in AC1

**AC3 — Created and downloaded datasets are told apart in one list**
Given the tab lists a downloaded dataset `hf-scikit-learn--iris` and a created file `Iris.csv`
When the user looks at the list
Then both are in the same list; the created one is labelled **"Created by myself"** and shows no source, licence or "shared with" information; the downloaded one looks as it does today

**AC4 — Saving again does not duplicate**
Given `Iris.csv` is already listed as a created dataset
When it is saved again at the same path with new contents
Then the tab still shows exactly one card for it, with the updated size

**AC5 — Only data files count**
Given a cell saves `Iris.csv`, `plot.png` and `model.pkl` in the working folder
When the Datasets tab refreshes
Then only `Iris.csv` gets a card *(data file types: CSV, TSV, JSON/JSONL, Parquet, Excel — dev to confirm the list in the PR)*

**AC6 — Copy load code works**
Given a created dataset `Iris.csv` is listed
When the user presses "Copy load code" (or the insert-into-notebook action downloaded datasets have)
Then the code loads the file from `/work/Iris.csv` and runs without error in the project's notebook

**AC7 — File removed outside the tab**
Given `Iris.csv` is listed as a created dataset
When notebook code deletes or renames the file
Then the card shows the existing `missing` status, and the assistant's dataset list reports it as `missing`

**AC8 — Deleting a created dataset warns that it is the only copy**
Given `Iris.csv` is listed as a created dataset
When the user presses Delete on its card
Then the confirmation says the file will be permanently removed from the project and the app keeps no other copy of it (the user can still make it again by re-running the code or asking the assistant to download it); on Confirm the file and card are gone, on Cancel nothing changes

**AC9 — The assistant can see created datasets**
Given the assistant has just saved `Iris.csv` with notebook code
When it lists the project's datasets (e.g. the user asks "list my datasets")
Then the list includes `Iris.csv` with its `/work/Iris.csv` path, so the assistant does not create the file again or run cells to check whether it exists. The reply does not need to say where the file was saved: data is always saved in the project's working folder.

**AC10 — Only the project's own files are listed**
Given notebook code writes a file outside the project's working folder, or creates a link pointing outside it
When the Datasets tab refreshes
Then no card is shown for it, and no other project's Datasets tab changes. Links the app itself made into the dataset pool (`/work/datasets/…`) are not affected: they keep showing as downloaded datasets.

**AC11 — The user is told when a created file went missing**
Given `Iris.csv` is listed as a created dataset and the file was deleted or renamed outside the Datasets tab
When the user opens that workspace (starts a chat on it, or switches to it)
Then a notification says that `Iris.csv` was deleted or renamed and can't be found, once per opening; the card keeps showing `missing` until the user deletes it

## Developer Notes

- **Context & intent:** the user's mental model is "data in my project = my datasets", whoever made it. The fix is about visibility and trust, not a new data source.
- **Where the gap is (likely):** `researchchat/workspace/datasets_store.py` reads `workspaces/<project>/datasets.json`, which only knows pool-linked catalog datasets (`source` is `huggingface | zenodo`). Notebook code (both `researchchat/tools/notebook_run.py` and user-run cells) writes straight to `files/` and never touches the manifest. The panel lists from `public/panel/src/components/DatasetsTab.tsx` / `DatasetCard.tsx`; the model sees `researchchat/tools/dataset_list.py`.
- **Because user-run cells count (AC2),** detection can't rely only on the assistant calling a tool; something has to notice new files after any cell run. *(assumption: verify against the codebase)*
- **Keep the safety rule:** `datasets.json` sits outside `files/` on purpose so kernel code can't edit it. The service decides what is listed and checks the path (inside `files/`, no symlink escape; reuse the `safe_relpath` style checks).
- **Dev decisions (not for the PO):** detection method (scan after each run vs. watching), exact data extensions, manifest field/format change and migration, where the "Created by myself" source value lives, refresh timing.
- **Data:** name, path, size, status, created/updated time; no licence, revision, pool entry or "shared with".
- **Edge cases:** the same path saved many times in one turn (AC4); a file still being written when the tab refreshes; very large files; names with spaces or quotes in load code; files under `files/datasets/` are pool links and must not be listed twice.
- **In-flight work to respect:** uncommitted changes from another session touch `researchchat/workspace/actions.py`, `dataset_service.py` and add `download_summary.py`. Build on top once it lands.
- **Testing hints:** reproduce in the `default` project by asking "create an iris dataset", then run your own `df.to_csv('results.csv')` cell. Unit-test the listing rules (duplicates, non-data files, missing, outside path, symlink) without a kernel.

## Out of Scope

- Reusing an already-downloaded dataset instead of creating a file: [STORY-04](STORY-04-reuse-existing-dataset.md).
- File tree and file preview inside a dataset (NB-5, [plan](../../plans/NB-5-dataset-unpack-preview-plan.md)).
- New catalogs, downloads from pasted links, uploads from the user's computer.
- Sharing created files between projects (the shared pool is for catalog downloads only).
- Stopping a project's kernel from reading pool datasets that are not in its own tab: [STORY-03](STORY-03-project-reads-only-its-own-datasets.md).
- Checking that a created file is the real, published data.

## Dependencies

- None blocking. Builds on NB-3 / NB-4 dataset storage ([done plans](../../plans/done/)); merge after the in-flight download-summary work.

## Open Questions

- None left. Answered by the PO on 2026-11-14: every data file counts (AC1, AC5); files from the user's own cells count (AC2); one list (AC3); label "Created by myself" (AC3).
