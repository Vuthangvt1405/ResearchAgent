# STORY-03: A project can read only the datasets in its own Datasets tab

[Epic PRD](../../requirements/02-project-created-datasets/README.md) · [Sprint backlog](README.md)

**Summary:** A project can read only the datasets in its own Datasets tab
**Type:** Story | **Epic:** Project-created datasets | **Priority:** High | **Labels:** datasets, security, kernel, pool | **Components:** kernel container, dataset pool
**Story points (suggested):** 5 — Complexity M, Uncertainty M, Effort M — changes how the pool is mounted into each kernel; uncertainty is making a dataset readable right after it is downloaded while the kernel is already running.

## User Story

As a **researcher with several projects**, I want **the notebook and the assistant in a project to read only the datasets shown in that project's Datasets tab**, so that **what a project can use is exactly what I see in its tab, and one project never reads data that belongs to another**.

## Background

NB-4 stores each downloaded file once in a shared pool (`workspaces/.dataset-pool/`) and links it into the projects that use it (`files/datasets/<id>/`). To make those links work inside the kernel, the **whole** pool folder is mounted read-only in every project's kernel at `/.dataset-pool` (`researchchat/workspace/kernels.py`, `run_arguments`). So code in any project can run `os.listdir('/.dataset-pool')` and read every dataset any project has downloaded, even when it is not in that project's tab.

The right way for project A to use B's data already exists: A's assistant calls `dataset_download` for it. If the pool already has the files, they are linked into A straight away with no new download; if B is still downloading them, A joins B's job and gets the files when it finishes (`DatasetService._plan_fetch` / `_queue_downloads`, NB-4 AC16/AC17). The dataset then shows in A's tab and A can read it. That path must keep working.

The PO decided on 2026-11-14 that the other path, reading `/.dataset-pool` directly, is not allowed: a project may read only the datasets its own Datasets tab shows. This is a change to existing NB-4 behaviour, not a bug in STORY-01.

## Acceptance Criteria

**AC1 — Own downloaded dataset is readable**
Given project A's Datasets tab lists `hf-scikit-learn--iris` (`ready`)
When A's notebook reads `/work/datasets/hf-scikit-learn--iris/…`
Then the file loads as it does today

**AC2 — Another project's dataset is not readable directly**
Given project B has downloaded `zenodo-123` and project A has not asked for it (A's tab does not list it)
When A's notebook lists `/.dataset-pool` or opens any path of `zenodo-123`'s pool files
Then the files are not there (not found / empty folder), and nothing about `zenodo-123` is shown to A

**AC2a — Asking for a dataset another project already has reuses it**
Given B's `zenodo-123` is `ready` in the pool
When A's assistant downloads `zenodo-123`
Then nothing is downloaded again; `zenodo-123` appears in A's tab as `ready` and A's notebook can read it at `/work/datasets/zenodo-123/…` straight away

**AC2b — Asking for a dataset another project is still downloading joins that download**
Given B is still downloading `zenodo-123` (`queued` or `downloading`)
When A's assistant downloads `zenodo-123`
Then no second download starts; A's tab shows the card with the same progress, and when the download finishes A's notebook can read it (and AC4 applies)

**AC3 — Dataset shared by both projects**
Given projects A and B both list the same pool dataset
When either notebook reads it
Then it loads in both, and the bytes are still stored only once

**AC4 — Newly downloaded dataset is readable without a restart**
Given A's kernel is running and the user downloads a new dataset into A
When the download finishes and the card shows `ready`
Then A's notebook can read it straight away, without the user restarting the kernel *(if a restart is unavoidable, dev raises it with the PO before building)*

**AC5 — Deleted dataset stops being readable**
Given A lists `hf-scikit-learn--iris`
When the user deletes it from A's Datasets tab
Then A's notebook can no longer read its files, and B (if it still lists the dataset) is not affected

**AC6 — Links cannot widen access**
Given A's notebook code creates a symlink or relative path pointing into the pool (e.g. `../../.dataset-pool/<other-entry>/…`)
When it reads through it
Then no file outside A's own datasets is reachable

**AC7 — The assistant sees the same set**
Given the assistant runs code or calls `dataset_list` in project A
When it looks for data
Then it can read and list only A's datasets (downloaded and created, see STORY-01), exactly what A's tab shows

## Developer Notes

- **Context & intent:** "the tab is the boundary". What a project can read = what its Datasets tab lists. The pool stays shared for storage only.
- **Where the gap is:** `KernelManager.run_arguments` in `researchchat/workspace/kernels.py` bind-mounts the whole `mounts.pool_dir` at `KERNEL_POOL_ROOT`. Links are written by `DatasetPool.link_files` / `link_target` in `researchchat/workspace/dataset_pool.py` as relative paths that land on that mount.
- **Dev decisions (not for the PO):** how each kernel gets only its own entries (e.g. one read-only mount per linked entry, a per-project view folder, or copying/hard-linking into the project), how AC4 works with a running container, and whether the link format changes (with a migration for existing projects).
- **Keep:** pool files stay read-only in every kernel; `datasets.json` stays outside `files/`; the app never trusts a link it finds (SEC23).
- **Edge cases:** a download finishing while a cell is running; the same entry linked under two dataset ids; existing projects created before this change; kernel restart after the change.
- **Testing hints:** unit-test which entries a project's kernel is given (pure function of the project's `datasets.json` + pool index) without Docker; one integration test with two projects proving AC2.

## Out of Scope

- Sharing datasets between projects on purpose (a "use in another project" action).
- Created files from STORY-01: they already live in the project's own `files/` and are only visible to that project.
- Multi-user accounts or permissions.

## Dependencies

- Builds on NB-4 ([done plan](../../plans/done/NB-4-dataset-pool-plan.md)). Independent of STORY-01, STORY-02, STORY-04 and STORY-05; AC7 covers created files once STORY-01 lands.

## Open Questions

- AC4: is a kernel restart after a download acceptable if keeping the kernel running turns out to be costly? (Ask the PO only if dev finds it necessary.)
