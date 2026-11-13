# Epic Plan: Dataset Download & Management
Status: Split into NB-3, NB-4, NB-5 — each awaiting answers · Source: chat request · Date: 2026-11-11 (rev. 4)

The assistant downloads datasets found with `dataset_search` into your project, in the background, so you keep chatting. Downloaded data sits in one shared pool, so other projects reuse it without downloading again. Archives are unpacked automatically. After a download you can see each dataset's size, look at the data inside, open it in the notebook, and delete it.

This file is the overview. Each ticket has its own full plan (requirements, schema, endpoints, security, tests):

| Ticket | Plan | What it delivers | ACs | Tests | Depends on |
|---|---|---|---|---|---|
| **NB-3** | [done/NB-3-dataset-download-plan.md](done/NB-3-dataset-download-plan.md) | background download into the project's `files/datasets/`, disk check, Download/Skip, queue, finish messages, `dataset_list`, delete, cancel, Datasets panel (download and ready rows) | AC1–AC14, AC21, AC24–AC28 | 80 | — |
| **NB-4** | [NB-4-dataset-pool-plan.md](done/NB-4-dataset-pool-plan.md) | shared pool with read-only `/pool` mount and symlinks, reuse across projects, shared jobs, per-project delete and cancel, migration of NB-3 data | AC15–AC18, AC29–AC30, pool parts of AC25/27/28 | 21 | NB-3 |
| **NB-5** | [NB-5-dataset-unpack-preview-plan.md](NB-5-dataset-unpack-preview-plan.md) | safe automatic unpacking; file tree, previews and Open in notebook in the panel; `pyarrow` in the kernel | AC19–AC20, AC22–AC23 | 20 | NB-3, NB-4 |

**Order:** NB-3 → NB-4 → NB-5. Each ships on its own: after NB-3 you can download and manage datasets; NB-4 makes them shared; NB-5 adds unpacking and browsing. AC and test numbers (G1–G14, S) are shared across the three plans, so a number means the same thing everywhere.

**Total:** 30 ACs, 121 tests (80 + 21 + 20), 1 of them needs Docker.

## AC map

| AC | Short description | Ticket |
|---|---|---|
| AC1 | `dataset_download` starts in the background and returns at once | NB-3 |
| AC2 | chatting never blocked by a download | NB-3 |
| AC3 | finish message to the chat + note for the model | NB-3 |
| AC4 | `files` filter | NB-3 |
| AC5 | disk check at start (no size cap) | NB-3 |
| AC6 | disk full during download | NB-3 |
| AC7 | Download/Skip above 200 MB | NB-3 |
| AC8 | status, progress, licence while downloading | NB-3 |
| AC9 | failures: checksum, network, stall | NB-3 |
| AC10 | app-wide queue, 2 at a time | NB-3 |
| AC11 | only missing files downloaded again | NB-3 |
| AC12 | no new revision without `update: true` | NB-3 |
| AC13 | unsupported, gated, restricted datasets refused | NB-3 |
| AC14 | download survives closing or switching the chat | NB-3 |
| AC15 | another project reuses pooled data without downloading | NB-4 |
| AC16 | only files missing from the pool are downloaded | NB-4 |
| AC17 | same files for two projects downloaded once | NB-4 |
| AC18 | pooled data read-only in the kernel | NB-4 |
| AC19 | archives unpacked automatically | NB-5 |
| AC20 | unsafe or too-big archives kept packed with a warning | NB-5 |
| AC21 | ready row shows name, size, file count | NB-3 |
| AC22 | file tree and previews | NB-5 |
| AC23 | Open in notebook | NB-5 |
| AC24 | `dataset_list` for the model | NB-3 |
| AC25 | delete from the panel (NB-4 adds "also used by", pool cleanup) | NB-3, NB-4 |
| AC26 | model delete asks Delete/Keep | NB-3 |
| AC27 | cancel (NB-4: per project for shared downloads) | NB-3, NB-4 |
| AC28 | `missing` files (NB-4: re-linked from the pool) | NB-3, NB-4 |
| AC29 | NB-3 data migrated into the pool | NB-4 |
| AC30 | older pooled revision reused unless `update: true` | NB-4 |

## UI design (Datasets section of the Notebook panel)

Shared by all three tickets; each plan says which parts it builds. The section sits under the notebook's header, follows the panel's Notion-like style (`rcnb-*` classes, `lucide-react` icons), and is collapsed to one line when empty. A clickable mockup was shown in the chat on 2026-11-11.

**Part 1 — Collapsed / empty** (NB-3)
```
▸ Datasets · none yet — ask the assistant to find and download one
```

**Part 2 — While downloading: status, progress, licence, Cancel** (NB-3; the unpacking row is NB-5)
```
▾ Datasets · 3 · 1.6 GB
  ┌──────────────────────────────────────────────────────────────┐
  │ ⬇ Credit Card Fraud Detection        Zenodo   cc-by-4.0      │
  │ Downloading ███████░░░░░░░░  41 / 144 MB · 3.2 MB/s   [Cancel]│
  ├──────────────────────────────────────────────────────────────┤
  │ ⏳ SensEURCity air quality            Zenodo   cc-by-4.0      │
  │ Waiting · 2nd in queue · 5.7 GB                      [Cancel]│
  ├──────────────────────────────────────────────────────────────┤
  │ 📦 images-dataset                     Hugging Face   mit      │
  │ Unpacking images.zip … 3,100 / 8,000 files                    │
  └──────────────────────────────────────────────────────────────┘
```

**Part 3 — When ready: name, size, file count, no status** (NB-3; the "not unpacked" warning row is NB-5)
```
  ▸ 🗂 David-Egea/Creditcard-fraud-detection      143.8 MB · 1 file   ⋯
  ▸ 🗂 twitter financial news                      2.1 MB · 3 files   ⋯
  ▸ ⚠ satellite-tiles      not unpacked: not enough disk   1.2 GB   ⋯
  ▸ ✕ old-census           failed: checksum mismatch        [Retry] ⋯
```
`⋯` menu: Open · Copy path · Delete.

**Part 4 — Opened: details, file tree, preview** (details line NB-3; "also used by" NB-4; file tree, preview and Open in notebook NB-5)
```
  ▾ 🗂 David-Egea/Creditcard-fraud-detection      143.8 MB · 1 file
     Hugging Face · mit · added 2 h ago · also used by 1 other project
     /work/datasets/hf-david-egea--creditcard-fraud-detection   [Copy]
     ┌ Files ─────────────────────┐ ┌ creditcard.csv · first 20 rows ──────────────┐
     │ 📄 creditcard.csv  143.8 MB│ │ Time │ V1     │ V2    │ … │ Amount │ Class   │
     │                            │ │ 0    │ -1.360 │ -0.073│ … │ 149.62 │ 0       │
     │                            │ │ 0    │  1.192 │  0.266│ … │   2.69 │ 0       │
     │                            │ │ …  (more rows not shown)                     │
     └────────────────────────────┘ └──────────────────────────────────────────────┘
                                                     [Open in notebook]  [Delete]
```
On a narrow panel the file tree sits above the preview. Wide tables scroll sideways inside their own box.

**Part 5 — Delete confirm, inside the panel** (NB-3; the "also used by" line is NB-4)
```
  Delete "Credit Card Fraud Detection" from this project?
  Also used by 2 other projects, so this frees 0 MB.          [Delete]  [Keep]
```

**Part 6 — In the chat** (NB-3; the "wasn't unpacked" message is NB-5)
```
┌ The assistant wants to download a dataset ────────────────────┐
│ SensEURCity air quality · Zenodo · cc-by-4.0                   │
│ 42 files · 5.7 GB to download · 212 GB free                    │
│                                         [Download]  [Skip]     │
└────────────────────────────────────────────────────────────────┘
✅ Dataset SensEURCity air quality is ready (5.7 GB) at /work/datasets/zenodo-17858205/
⚠ Dataset satellite-tiles is ready, but images.zip wasn't unpacked: not enough disk (needs 9.4 GB, 6.1 GB free).
❌ Download of old-census failed: checksum mismatch on census.csv. Ask me to try again.
```

## Open questions, by ticket

| Ticket | Question | Default |
|---|---|---|
| NB-3 Q1 | add `max_queued = 10` per project and a `dataset_cancel` tool for the model? | not included yet |
| NB-3 Q2 | one app-wide queue, 2 downloads at a time (replaces A8)? | yes |
| NB-4 Q1 | remove a dataset from the pool as soon as no project uses it? | yes |
| NB-4 Q2 | move NB-3 datasets into the pool automatically on first start? | yes |
| NB-5 Q1 | remove archives after unpacking? | yes |
| NB-5 Q2 | add `pyarrow` to the kernel image for Parquet? | yes |

New assumptions: A11, A12, A14 (NB-4); A13, A15 (NB-5).

## Decision log

| # | Question / request | Answer | What changed in the plan |
|---|---|---|---|
| D1 | Size limits (2 GB per dataset, 10 GB per project) | "Don't need to check max size, just check disk has enough" | Removed size caps; free-disk check with reserved space and a margin (AC5); disk re-checked during download (AC6) |
| D2 | Waiting vs background | "Download can run in the background so the user can continue chatting" | Tool returns at once; job queue; finish messages and a one-time note for the model (AC1–AC3, Group 10) |
| D3 | Idempotency with different file selections | "ok" to checking per file | One record per dataset; only missing files fetched (AC11, Group 6) |
| D4 | Hugging Face file limits; `name` vs `source_id` | "Yes, add both" | File-list pages followed with early stop; `name` from `pretty_name` (Group 2) |
| D5 | Questions and assumptions of rev. 2 | Status, progress and licence only while downloading; after success see size, data inside, delete; not ML models. A shared pool. Hugging Face + Zenodo first. Margin 0. Keep asking above 200 MB. The model may delete with permission. Unpack automatically. More UI. Ticket NB-3. A5: never update unless the user asks. Other assumptions: yes | Panel shows different things per stage; file browser, preview and Open in notebook; shared pool; `min_free_disk_mb = 0`; unpacking; `update` flag (AC12); UI design and mockup |
| D6 | Split the 28-AC plan into tickets? | "Yes, split it" | Three plans: NB-3 (download and manage, 80 tests), NB-4 (pool, 21 tests), NB-5 (unpack and preview, 20 tests). NB-3 stores data in the project first; NB-4 adds the pool plus a migration of NB-3 data (new AC29) and AC30 for pooled revisions. This file became the overview |

No files or data were changed while planning, other than the plan files.
