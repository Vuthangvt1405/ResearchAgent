# Epic PRD — Project-created datasets

**Suggested total:** 29 points · **Backlog:** [docs/tasks/02-project-created-datasets/](../../tasks/02-project-created-datasets/README.md)

## Summary

When the assistant or the user creates a data file in the notebook (e.g. `Iris.csv`), it must show up in the Datasets tab next to downloaded datasets, and the assistant should reuse data the project already has instead of making copies. Users can also paste a dataset link from other sources (any public file link, Kaggle) and have it downloaded into the shared pool.

## Background

Reported 2026-11-14: "when I told the agent to create a dataset, it doesn't appear in Datasets, but it already created ./Iris.csv". Cause: the Datasets tab only lists catalog downloads (HuggingFace, Zenodo, kept in `datasets.json`); files written by notebook code land in the project's `files/` folder and are never listed. The same project already had a downloaded iris dataset that the assistant didn't use.

## Requirement Analysis

| Item | Finding |
|---|---|
| Actors | Researcher (runs their own cells), the assistant (runs notebook code on their behalf) |
| Goals | See every data file the project has in one list; get existing data reused, not duplicated |
| Business value | Trust in the assistant's "I created it"; fewer duplicate or fabricated files; less time asking where data is *(assumed)* |
| Rules (stated by PO) | Every data file counts; files from the user's own cells count; one list; label "Created by myself"; reuse existing datasets |
| Data | File name, path, size, status, created/updated time; no licence/source/pool entry |
| Ambiguities | Pasted-source downloads (see below) |

## Estimation Log

| Candidate story | Complexity | Uncertainty | Effort | Points | Action |
|---|---|---|---|---|---|
| Show assistant-created datasets in the tab (first draft) | M | M | M | 5 | Re-estimated after PO answers |
| ↳ + user-run files count, + reuse existing datasets | M | M | H | 8+ | ✂️ Split (by business rule) |
| ↳ STORY-01: List created data files (assistant and user) | M | L | M | 5 | ✅ Keep |
| ↳ STORY-04: Reuse an existing dataset | L | M | L | 3 | ✅ Keep |
| Download from any pasted dataset link | H | H | H | 13+ | ✂️ Split (by source) |
| ↳ Hugging Face / Zenodo page links | — | — | — | 0 | Already works (`parse_ref` accepts their page URLs) |
| ↳ STORY-02: Public file links (incl. GitHub file links) | H | M | M | 8 | ✅ Keep, at the limit (split off GitHub links if higher) |
| ↳ STORY-05: Kaggle links (needs user's Kaggle account) | M | H | M | 8 | ✅ Keep, at the limit; spike first |

## Ticket Tree

```
Epic: Project-created datasets  (total: 29 points)
├── STORY-01: Show data files created in the notebook in the Datasets tab  (5 pts, High, depends on: —)
├── STORY-02: Download a dataset file from a link I paste into the chat  (8 pts, High, depends on: —)
├── STORY-03: A project can read only the datasets in its own Datasets tab  (5 pts, High, depends on: —)
├── STORY-04: Reuse a dataset the project already has instead of creating a copy  (3 pts, Medium, depends on: STORY-01 for AC2/AC6)
└── STORY-05: Download a Kaggle dataset from a pasted Kaggle link  (8 pts, Medium, depends on: 1-day spike)
```

## Decisions (PO, 2026-11-14)

1. Every data file saved in the notebook counts as a dataset.
2. Files saved by the user's own cells count too.
3. One list for created and downloaded datasets.
4. Label for created files: "Created by myself".
5. The assistant reuses an existing matching dataset.

6. Pasting a dataset link from other sources and having it downloaded into the shared pool is in scope (confirmed 2026-11-14). Hugging Face and Zenodo page links already work today.

7. Pasted links from any public website are allowed (STORY-02).
8. A connected Kaggle account is used for all of a user's projects (STORY-05).

9. Each user connects their own Kaggle account once, in Settings (STORY-05).

## Open Questions

- None. All PO questions answered on 2026-11-14.
