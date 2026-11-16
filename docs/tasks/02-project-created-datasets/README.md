# Sprint Backlog — Project-created datasets

[Epic PRD](../../requirements/02-project-created-datasets/README.md)

| # | Story | Points | Priority | Depends on | Status |
|---|---|---|---|---|---|
| 1 | [STORY-01: Show data files created in the notebook in the Datasets tab](STORY-01-list-created-datasets.md) | 5 | High | — | Ready |
| 2 | [STORY-02: Download a dataset file from a link I paste into the chat](STORY-02-download-from-pasted-file-link.md) | 8 (at the limit) | High | — | Ready |
| 3 | [STORY-03: A project can read only the datasets in its own Datasets tab](STORY-03-project-reads-only-its-own-datasets.md) | 5 | High | — | Ready |
| 4 | [STORY-04: Reuse a dataset the project already has instead of creating a copy](STORY-04-reuse-existing-dataset.md) | 3 | Medium | STORY-01 (AC2, AC6 only) | Ready |
| 5 | [STORY-05: Download a Kaggle dataset from a pasted Kaggle link](STORY-05-download-from-kaggle-link.md) | 8 (at the limit) | Medium | 1-day spike | Ready (spike first) |

Total: 29 points.

## Later sprints

Not ready yet and not in this sprint. Turn into a story (with `jira-story-writer`) when it's picked up.

| Item | Why it's here | Raised in |
|---|---|---|
| Created datasets in very large working folders | STORY-01 scans the whole `/work` folder after every cell run with no limit. That's fine for normal projects (about 38 ms for 50,000 files on Linux), but a venv, `node_modules` or a cloned repo in `/work` (100,000+ files), or slow Docker Desktop folders on Windows/Mac, could add up to seconds per run. A loop that writes thousands of CSVs would also put thousands of cards in the tab. Decide on scan limits or a folder watcher, and how the tab shows very many created files. | [STORY-01 plan, A9](../../plans/PCD-1-created-datasets-plan.md) |
