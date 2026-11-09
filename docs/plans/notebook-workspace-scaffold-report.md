# Scaffold Report: Project Notebook Workspace
Status: Scaffolded — awaiting verification · Plan: [notebook-workspace-plan.md](notebook-workspace-plan.md) · Date: 2026-11-09

## 9. Scaffold report

### File tree

```
.chainlit/config.toml                 ✏️ custom_js = "/public/custom.js"
.gitignore                            ✏️ workspaces/
README.md                             ✏️ layout + "Notebook workspace (in progress)"
app.py                                ✏️ imports the nb_* actions; TODO hooks only (no calls, app runs as before)
config.toml                           ✏️ [notebook] and [notebook.docker]
pytest.ini                            ✏️ registers the `docker` marker (plan revision, see below)
requirements.txt                      ✏️ jupyter_client>=8.6, nbformat>=5.10 (installed: 8.10.0, 5.11.1)
researchchat/config.py                ✏️ reads [notebook] values
researchchat/tools/__init__.py        ✏️ NOTEBOOK_TOOLS list; both tools in the name lookup
researchchat/tools/notebook_run.py    🆕 DEFINITION, ask_approval, run
researchchat/tools/notebook_read.py   🆕 DEFINITION, run
researchchat/workspace/__init__.py    🆕 ErrorCode, WorkspaceError
researchchat/workspace/store.py       🆕 Project, slug regex, file + cell functions
researchchat/workspace/kernels.py     🆕 Output, RunResult, DockerSettings, KernelRegistry
researchchat/workspace/risk.py        🆕 reason texts, pattern sets, check()
researchchat/workspace/service.py     🆕 NotebookProps TypedDicts, NotebookService
researchchat/workspace/panel.py       🆕 PanelRegistry
researchchat/workspace/actions.py     🆕 12 nb_* action callbacks + payload allow-list
public/elements/Notebook.jsx          🆕 panel components (placeholder render)
public/custom.js                      🆕 project bar functions (mount() not called yet)
docker/kernel.Dockerfile              🆕 python:3.12-slim, installs kernel-requirements.txt, non-root
docker/kernel-requirements.txt        🆕 ipykernel, numpy, pandas, matplotlib (pinned)
tests/test_workspace_store.py         🆕 G1
tests/test_workspace_service.py       🆕 G2, S
tests/test_workspace_kernels.py       🆕 G3, G4, G5, G9 (marked docker)
tests/test_workspace_risk.py          🆕 G7
tests/test_notebook_tools.py          🆕 G6, G8
```

**Plan revisions found while scaffolding**
- `pytest.ini` wasn't in the file list, but it's needed to register the `docker` test marker. Added.
- `researchchat/settings.py` (the "Notebook" switch, assumption H) was missing from the file list. It's **not changed** in the scaffold, because nothing needs it to build. It's added to the plan for the implementation step.
- The test total in the plan was 92; the tables hold **90** unique tests (the security group reuses 4 tests from other groups). The plan now says 90.
- `TOOLS` stays the web search list, so the existing `test_both_tools_are_registered` still passes. Notebook tools are a separate `NOTEBOOK_TOOLS`, which matches the separate switch.

### Build and test result

| Check | Command | Result |
|---|---|---|
| Compile | `python -m compileall -q researchchat app.py tests` | ✅ pass |
| Import | `python -c "import app"` | ✅ pass; `NOTEBOOK_TOOLS` = notebook_read, notebook_run |
| Tests | `pytest -q` | ✅ **90 failed (all new, on purpose), 29 passed (all existing)** |
| Tests without Docker | `pytest -q -m "not docker"` | 61 failed, 29 passed, 29 deselected |
| App | browser on port 8001 | ✅ chat loads, greeting shows, `/public/custom.js` 200, no console errors |

Not done: the Docker image wasn't built, and Docker Desktop wasn't running.

### TODO map

`grep -rn "TODO(" researchchat app.py public docker` lists all remaining work:

| Where | Plan refs | Note |
|---|---|---|
| `researchchat/tools/notebook_read.py:26` | AC17, SEC14, G8 |  service.read_for_model(session project) |
| `researchchat/tools/notebook_run.py:38` | AC11, SEC1, G6✅4, G6❌1, G6❌2 |  |
| `researchchat/tools/notebook_run.py:44` | AC10, AC11, AC20, G6 |  empty code -> error without asking (G6❌3); |
| `researchchat/workspace/actions.py:37` | SEC2, S2 |  |
| `researchchat/workspace/actions.py:43` | SEC9, G2❌4 |  allow-list only, ignore unknown fields (S2) |
| `researchchat/workspace/actions.py:49` | SEC8 |  |
| `researchchat/workspace/actions.py:116` | AC18, SEC2, G1✅6, G1❌3 |  check the id against list_projects, set the session, reload the panel |
| `researchchat/workspace/actions.py:122` | AC18, G1✅7 |  create, then switch the session to it |
| `researchchat/workspace/kernels.py:78` | AC20, G9❌5 |  `docker info`; never fall back to running on the host |
| `researchchat/workspace/kernels.py:82` | AC20 |  off, starting, idle, busy, dead, unavailable |
| `researchchat/workspace/kernels.py:87` | AC19, SEC4, SEC10, SEC11, G9✅1, G9❌1–3, G9❌6 |  flags from the plan §4.1, |
| `researchchat/workspace/kernels.py:93` | AC2, AC3, AC4, AC8, AC12, AC14, G3, G4❌1 |  cap text at max_output_chars |
| `researchchat/workspace/kernels.py:99` | AC17, G8✅2, G8✅3 |  must not change execution_count |
| `researchchat/workspace/kernels.py:103` | AC8, G4✅1 |  docker kill --signal SIGINT |
| `researchchat/workspace/kernels.py:107` | AC9, G4✅2, G3❌4 |  remove the container and start a fresh one |
| `researchchat/workspace/kernels.py:111` | G4✅4 |  docker stop, delete the connection file |
| `researchchat/workspace/kernels.py:116` | G4✅4 |  |
| `researchchat/workspace/kernels.py:121` | G9✅3 |  |
| `researchchat/workspace/panel.py:19` | AC1 |  cl.ElementSidebar.set_title / set_elements with cl.CustomElement(ELEMENT_NAME, props) |
| `researchchat/workspace/panel.py:24` | AC7 |  |
| `researchchat/workspace/panel.py:29` | AC7, G5✅2 |  |
| `researchchat/workspace/risk.py:29` | AC11, SEC1, SEC12, SEC13, G7 |  parse with ast (after pulling out IPython ! and % lines), |
| `researchchat/workspace/service.py:64` | AC1 |  |
| `researchchat/workspace/service.py:70` | AC5, AC15, G2✅2, G2✅3, G2✅8, G2❌1, G2❌5 |  |
| `researchchat/workspace/service.py:74` | AC5, SEC8, SEC9, G2✅1, G2❌1–3, S8 |  |
| `researchchat/workspace/service.py:78` | AC5, G2✅6 |  |
| `researchchat/workspace/service.py:82` | AC5, G2✅4, G2✅5, G2❌4 |  |
| `researchchat/workspace/service.py:86` | G2✅7 |  |
| `researchchat/workspace/service.py:93` | AC2, AC3, AC7, AC12, AC20, G2❌6 NOT_CODE, G3, G5✅2 |  one run at a time (queue, G4✅3) |
| `researchchat/workspace/service.py:97` | AC16, G3✅6, G3✅7 |  skip notes, stop at the first error |
| `researchchat/workspace/service.py:101` | AC8, G4✅1 |  ignores version |
| `researchchat/workspace/service.py:105` | AC9, G4✅2 |  ignores version; cells and outputs kept |
| `researchchat/workspace/service.py:111` | AC18 |  |
| `researchchat/workspace/service.py:115` | AC18, G1✅7 |  BAD_NAME for unusable names |
| `researchchat/workspace/service.py:122` | AC17, SEC14, G8 |  cut to NOTEBOOK_READ_MAX_CHARS, images as [image WxH] |
| `researchchat/workspace/service.py:127` | AC10, G6✅1–3 |  "[cell n] out: ...", <= 4,000 chars |
| `researchchat/workspace/store.py:36` | AC18, G1✅2 |  "Tokyo Housing!!" -> "tokyo-housing"; BAD_NAME if nothing is left |
| `researchchat/workspace/store.py:42` | SEC3, S3a, S3b |  check PROJECT_ID_RE, resolve, and require the path to stay under root |
| `researchchat/workspace/store.py:48` | AC1, G1✅1, G1❌2 |  unique id (tokyo-housing-2 on clash), never overwrite |
| `researchchat/workspace/store.py:54` | G1✅3 |  |
| `researchchat/workspace/store.py:60` | AC18 |  |
| `researchchat/workspace/store.py:66` | AC18, G1❌3 |  |
| `researchchat/workspace/store.py:72` | AC5, G1✅4 |  |
| `researchchat/workspace/store.py:78` | AC5, G1✅5, G1❌1 |  validate with nbformat; old file intact if the write fails |
| `researchchat/workspace/store.py:84` | SEC8, G2✅1 |  |
| `researchchat/workspace/store.py:90` | SEC8, G2✅1 |  |
| `researchchat/workspace/store.py:96` | AC15, G2✅2, G2✅3, G2✅8, G2❌5 |  BAD_TYPE for other types; NOT_FOUND for unknown after_id |
| `researchchat/workspace/store.py:102` | AC5, G2✅1, G2❌2, G2❌3 |  NOT_FOUND, TOO_LARGE over MAX_SOURCE_BYTES |
| `researchchat/workspace/store.py:107` | AC5, G2✅6, G2❌2 |  |
| `researchchat/workspace/store.py:113` | AC5, G2✅4, G2✅5, G2❌4 |  |
| `researchchat/workspace/store.py:119` | G2✅7 |  |
| `researchchat/workspace/store.py:125` | G2❌2 |  |
| `app.py:15` | AC18, SEC5, S5 |  refuse to start when Chainlit's host isn't localhost |
| `app.py:16` | G9✅3 |  remove leftover kernel containers on startup |
| `app.py:35` | AC1, AC18, G1✅3 |  pick the last-used project (default on first start), |
| `app.py:40` | AC7 |  add @cl.on_chat_end to unregister this chat's panel |
| `app.py:41` | AC10, AC17, H |  send NOTEBOOK_TOOLS when the "Notebook" switch is on |
| `public/custom.js:14` | AC18 |  locate Chainlit's message box; null when the layout changed |
| `public/custom.js:19` | AC18 |  current project name, switch list, "New project" |
| `public/custom.js:24` | AC18 |  insert the bar under the composer, keep it there with a |
| `public/custom.js:30` | AC18 |  call mount() once it is implemented. Not called yet, so the |
| `public/elements/Notebook.jsx:19` | AC15, SEC6 |  build React elements (headings, bold, italic, code, lists, |
| `public/elements/Notebook.jsx:25` | AC2, AC4, AC14, SEC6 |  stdout/stderr/result/error as text in SCROLL_BOX, |
| `public/elements/Notebook.jsx:31` | AC2, AC14 |  [n] label, Textarea (Shift+Enter runs), status badge, outputs |
| `public/elements/Notebook.jsx:36` | AC15 |  formatted view; double-click to edit; Shift+Enter or blur saves |
| `public/elements/Notebook.jsx:41` | AC1, AC5, AC7, AC8, AC9, AC18, AC20 |  |

### Suggested first test

`tests/test_workspace_store.py::test_new_project_has_empty_notebook_and_files_dir` (G1✅1). It needs only `store.create_project`, no Docker, and everything else builds on it.

## 10. Verification

### 10a. Self-verification

| # | Check | Result |
|---|---|---|
| V1 | Every file in "Files affected" exists; no extras | ✅ all listed files exist. Extras: `pytest.ini` (needed for the marker, now in the plan). `settings.py` deferred to implementation |
| V2 | Actions match §4.2 | ✅ 12 callbacks: the 9 cell/kernel actions + `nb_list_projects`, `nb_switch_project`, `nb_create_project` |
| V3 | DTO fields match §4.3 | ✅ `NotebookProps`, `ProjectRef`, `CellProps` (incl. `type`), `OutputProps`, `ErrorProps`; payload allow-list `FIELDS` matches the payload table |
| V4 | Storage layout and config match §3.3 | ✅ layout in the `store.py` docstring, `PROJECT_ID_RE`, `[notebook]` + `[notebook.docker]`; nothing written to `workspaces/` |
| V5 | Security wiring from §5 present | ✅ project only from session (`session_project`), payload allow-list, 100 KB limit, Docker flags documented in `kernels.py`, risk check hook, host check TODO in `app.py` |
| V6 | Every planned test exists with its exact name | ✅ planned 90 / found 90, no duplicate names (generated from the plan tables) |
| V7 | No logic leaked | ✅ new bodies are `NotImplementedError` + TODO; actions only read the payload and call the service; `custom.js` doesn't run anything |
| V8 | Build passes; new tests fail; existing pass | ✅ see above |

### 10b. Please verify

```
Please verify before I implement any logic:
☐ File locations and class/method names look right for our codebase
☐ Action names, payload fields and error codes are what you want
☐ NotebookProps fields (names, types) are final — the panel contract is about to be locked in
☐ Storage layout and [notebook] config are correct
☐ The test list is complete — any missing negative or security case?
☐ TODO map covers all the work
```

## 11. Implementation status (2026-11-09)

Status: Implemented and verified — 148 tests pass (incl. 30 Docker tests)

| Area | Tests | Result |
|---|---|---|
| G1 projects, G2 editing, S security | 25 (+ parametrized cases) | ✅ pass |
| G6 notebook_run, G8 notebook_read | 14 | ✅ pass |
| G7 risk check | 16 | ✅ pass |
| G3, G4, G5, G9 Docker kernel | 30 | ✅ pass (image `researchchat-kernel:1` built; Docker 29.9.2) |
| Existing tests | 30 | ✅ pass (`test_settings` now expects the new Notebook switch) |

**Checked in the browser:** panel opens on the right; note Markdown renders, `<script>` stays text and `javascript:` links aren't links; running with Docker down shows the callout and resets the cell; two tabs on one project: tab B's new cell appears in tab A while tab A keeps its cursor and unsaved text; block menu add/move/delete; project bar under the message box.

**Changes from the plan made while implementing**
- Kernels return outputs in nbformat form (so the `.ipynb` stays exact); the panel still gets `OutputProps`.
- Chainlit recompiles a custom element on every props change, which remounts it. The panel keeps its state on `window` and restores the cursor; edit actions aren't pushed back to the chat that made them (`panel.skip_session`).
- A failed run (e.g. Docker down) pushes a final update so no panel stays on "running".
- Typing saves while a cell runs: separate edit and run locks per project; a STALE save is retried once when that cell wasn't changed elsewhere.
- Names with no Latin letters become `project`, `project-2`… instead of `BAD_NAME`.
- Notes open with one click (Notion style), not a double-click.
- New test helper `tests/conftest.py` (fake kernels, Docker skip).
- Panel restyled like a Notion page at the user's request.

**Found and fixed once Docker was running**
- Cleanup removed *every* `rc-kernel-*` container, so the test suite killed the running app's kernel; the model's runs then failed silently (4 unrun cells). Containers now carry a `researchchat.scope` label (hash of the workspaces folder) in their name and label, and cleanup only removes its own scope. New test `test_cleanup_leaves_other_apps_kernels_alone` (G9✅4); total 91 planned tests.
- The Run / Skip question for risky model code was nested inside the collapsed tool-step group, so it was invisible. It now shows at the top level of the chat.
- `execute` now ignores shell replies that aren't for its own request; shell output's CRLF line endings are normalised.

**End-to-end in the app:** "compute the mean of [3, 5, 10] and draw a bar chart" ran without asking, added a cell with the output and the chart, and the model answered 6.0. `!ls -la /work` asked Run / Skip with the reason "runs a shell command"; Skip ran nothing, Run listed the sandboxed `/work` folder.
