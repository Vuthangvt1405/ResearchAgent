---
name: maintain-codebase
description: Maintain a Python codebase - find and remove dead code with Vulture, verify nothing broke (tests, imports, lint, types), lock in maintenance rules, review/refactor the code against the SOLID principles, decide whether the folder structure is worth reorganising now or later, and log the tech debt found along the way. Use this skill whenever the user asks to maintain, clean up, tidy, prune, or refactor a Python project, remove dead/unused code, unused imports, functions, classes or variables, run vulture, find, list or reduce tech debt, reorganise or review the folder/package structure, check or enforce SOLID, or says things like "clean this repo", "what code is unused", "is this still used", or "make this codebase healthier", even if they never mention Vulture, SOLID or tech debt by name.
---

# Maintain a Python codebase

A maintenance pass in five phases: **remove dead code → verify → lock in rules → SOLID review → folder structure review**, with a **tech debt log** kept throughout. The pass ends with a report and a numbered **action plan**; once the user verifies it, the approved items move to action (see "Review gate: from plan to action"). The order matters. Deleting dead code first shrinks the surface you have to reason about, so the SOLID and structure reviews are done on code that actually runs.

Two principles drive everything below:

1. **Vulture's output is a list of suspects, not a verdict.** It matches names across the files you give it and ignores scope, so dynamic Python (`getattr`, framework hooks, entry points, plugins, templates) produces false positives. Every finding below 100% confidence needs evidence before deletion.
2. **Behaviour must not change.** This is maintenance. Each change is small, verified, and revertible. If you cannot verify a change, do not make it silently; report it.

## Tech debt log (runs through every phase)

You read a large part of the codebase during this pass: triaging Vulture findings, grepping for usages, reviewing classes. Use that reading. Whenever you notice tech debt, **write it down immediately** in a running log (a scratch file such as `.maintenance/tech-debt.md`, not committed unless the user wants it) with the location, what the problem is, and what it costs. Notes taken at the moment are accurate; a list reconstructed from memory at the end is not.

The default is to **log, not fix**. Fixing everything you pass turns a reviewable maintenance pass into a sprawling diff, and many debt items need a decision from the user. Fix on the spot only when the fix is trivial, clearly behaviour-preserving, and inside code you are already changing.

What counts as tech debt, how to search for it deliberately, and how to rate impact and effort are in `references/structure-and-debt.md`. Read it before Phase 1 so you know what to watch for.

## Phase 0 - Preflight

Before touching anything:

- **Git state.** Run `git status`. If the tree is dirty, tell the user and ask whether to continue (their uncommitted work would get mixed into your changes). Work on a new branch such as `chore/maintain-codebase` unless the user says otherwise.
- **Project shape.** Read `pyproject.toml` / `setup.cfg` / `setup.py` to learn: source paths (`src/`, package dirs), test paths, how tools are run (`uv run`, `poetry run`, `hatch run`, plain venv), declared entry points and plugins (`[project.scripts]`, `[project.entry-points]`), and whether this is a **library** (public API consumed by others) or an **application**. For a library, anything exported publicly is used by definition even if nothing in the repo calls it.
- **Frameworks.** Note Django, FastAPI/Flask, Celery, Click/Typer, pytest, Pydantic, SQLAlchemy, etc. Each one calls code implicitly. See `references/vulture.md` for the per-framework list.
- **Baseline.** Run the project's existing checks and record the results *before* any change: test suite, linter (ruff/flake8), type checker (mypy/pyright) if configured. Pre-existing failures are not yours to fix, but you need to know them so you can tell a regression from old breakage. If there are no tests at all, say so now: verification will be weaker and you should be more conservative in Phase 1.
- **Install Vulture** if missing, using the project's own tool runner as a dev dependency (`uv add --dev vulture`, `poetry add --group dev vulture`, or `pip install vulture`). Reuse any existing `[tool.vulture]` config and whitelist.

## Phase 1 - Find and remove dead code

### 1. Scan

Scan source **and tests together** so code exercised only by tests is not flagged for deletion:

```bash
vulture <src_paths> <test_paths> [whitelist.py] --min-confidence 60 --sort-by-size
```

Exclude generated and vendored code (`--exclude "*/migrations/*,*/.venv/*,*_pb2.py"`). Exit code 3 means dead code was found, 0 means clean, 1/2 mean bad input or arguments.

Optionally also scan source alone. Anything reported there but not in the combined scan is used *only by tests*: possibly dead in production. Do not delete these on your own; list them for the user.

### 2. Triage every finding

Confidence tells you how much evidence you need:

| Confidence | What it is | How to treat it |
|---|---|---|
| 100% | unreachable code, unused function/method/class arguments | Unreachable code: remove. Arguments: usually **keep the signature** (see below). |
| 90% | unused imports | Remove after checking for re-exports and side-effect imports. |
| 60% | unused attribute, class, function, method, property, variable | Suspect only. Prove it is unused before deleting. |

For each 60% and 90% finding, search for evidence of use that Vulture cannot see:

- `grep -rn "<name>"` across the **whole repo, not just `.py` files**: templates, YAML/TOML/JSON config, docs, shell scripts, CI files, SQL, notebooks.
- String-based access: `getattr`, `globals()`, `importlib.import_module`, dotted-path strings in settings, `__all__`.
- Implicit callers: framework hooks, decorators that register things, dunder methods, overrides of a base class or Protocol method, serializer/ORM/Pydantic fields, pytest fixtures and hooks, entry points.
- Public API of a library: anything exported from a package `__init__.py` or documented.

Then classify each finding as exactly one of:

- **Remove** - no use found anywhere.
- **False positive** - it is used implicitly. Add it to the whitelist (Phase 3), do not touch the code.
- **Uncertain** - plausible dynamic or external use you cannot rule out. Leave it and list it for the user. A wrongly kept function costs a few lines; a wrongly deleted one costs a production incident.

Special cases:

- **Unused arguments.** If the function is an override, callback, hook, fixture, or part of a public API, the signature is a contract. Keep the parameter and rename it with a leading underscore (`_event`) or add `del event`. Only drop the parameter when you can update every caller.
- **Unused imports in `__init__.py`** are usually re-exports. Keep them and make it explicit with `__all__`.
- **Side-effect imports** (registering models, signals, plugins) must stay; whitelist them.
- **Unused local variables** whose right-hand side has side effects: keep the call, drop only the binding.

### 3. Remove in small batches

Remove in order of certainty (unreachable code → imports → functions/classes), one coherent batch at a time (per module or per feature), and run Phase 2 after each batch. Small batches make a failure trivial to locate and revert.

When deleting something, also delete what only existed for it: its now-unused imports, private helpers, tests that test only the removed code, fixtures, docs and config entries. Do not leave commented-out code behind; git history is the archive.

### 4. Re-scan until stable

Deleting code exposes more dead code (helpers of the deleted function). Re-run Vulture and repeat triage until a scan produces no new **Remove** findings.

## Phase 2 - Verify nothing broke

Run after every batch, cheapest check first:

1. `python -m compileall -q <src_paths>` - syntax.
2. Import smoke test - import the top-level package(s) and CLI entry points (`python -c "import mypkg"`, `mypkg --help`). Catches removed names that are imported elsewhere.
3. Linter - `ruff check` / `flake8`, mainly for undefined names (F821) and broken imports.
4. Type checker, if the project uses one.
5. Full test suite.

Compare with the Phase 0 baseline. The rule is **no new failures**. If something fails:

- Revert that batch (`git checkout -- <files>` or `git revert`), find the specific deletion responsible, reclassify it as a false positive, add it to the whitelist, and re-apply the rest.
- Never "fix" a failure by deleting or weakening the test, and never push forward with a red suite.

When a batch is green, commit it with a message that says what was removed and why (`chore: remove unused export helpers (vulture)`). One commit per batch keeps every step revertible.

## Phase 3 - Lock in the maintenance rules

Make the clean state stay clean, so the next run starts from signal rather than noise:

- **Whitelist.** Put confirmed false positives in a `vulture_whitelist.py` at the repo root (start from `vulture <paths> --make-whitelist`, then keep only the entries you classified as false positives). Prefer the whitelist over `--ignore-names` or `# noqa`: it is plain Python, lives in one reviewable place, and adds no noise to the code.
- **Config.** Persist the scan settings in `pyproject.toml` so `vulture` with no arguments reproduces your scan:

  ```toml
  [tool.vulture]
  paths = ["src", "tests", "vulture_whitelist.py"]
  exclude = ["*/migrations/*"]
  min_confidence = 80
  sort_by_size = true
  ```

  Use 60 for manual maintenance passes; a higher value such as 80 suits automated gates, where false positives block people.
- **Automation.** If the repo already uses pre-commit or CI, *offer* to add Vulture there (snippets in `references/vulture.md`). Do not add new infrastructure the user did not ask for.

## Phase 4 - SOLID review

Now review the remaining code against SOLID. Read `references/solid-python.md` first: it has the Python-specific smells, detection hints, and fix patterns for each principle.

| Principle | Question to ask of each module/class |
|---|---|
| **S**ingle Responsibility | Does it have more than one reason to change (e.g. business rules + I/O + formatting)? |
| **O**pen/Closed | Does adding a new variant mean editing an `if/elif` or `isinstance` chain in existing code? |
| **L**iskov Substitution | Can every subclass stand in for its base without callers noticing (same signature, no `NotImplementedError`, no stricter preconditions)? |
| **I**nterface Segregation | Are implementers forced to provide methods they do not need? Do callers depend on a fat interface for one method? |
| **D**ependency Inversion | Does high-level logic construct its own concrete dependencies (DB clients, HTTP sessions, `datetime.now()`) instead of receiving them? |

How to apply it:

- **Scope.** Default to the modules you touched plus the highest-traffic core modules; review the whole codebase if the user asked for a full pass. Say which scope you used.
- **Your own changes always comply.** Any code you write or restructure during this skill must satisfy SOLID. Never introduce a new violation while fixing something else.
- **Fix what is clear and safe now.** Small, mechanical, behaviour-preserving refactors with test coverage (extract a class or function, inject a dependency through the constructor with the old default, replace a type-switch with a registry or polymorphism, split a fat ABC into Protocols). After each refactor run Phase 2 again and commit separately from dead-code commits (`refactor: ...`).
- **Propose what is large or risky.** Refactors that change public APIs, span many modules, or touch code without tests go in the report as recommendations with a concrete plan, and wait for the user's go-ahead.
- **Stay pragmatic.** SOLID serves changeability; it is not a goal in itself. Do not add an interface for a single implementation with no foreseeable second one, and do not split a small cohesive class to hit a rule. If satisfying a principle would add more complexity than it removes, say so in the report instead of doing it. A violation is something that makes a realistic change harder, not merely something that deviates from a textbook shape.
- **Refactors can create dead code.** After Phase 4 changes, run Vulture once more and close the loop.

## Phase 5 - Folder structure review

Decide whether the folder/package tree should be reorganised, and if so, **whether now is the right time**. Moving files is the most disruptive kind of refactor: it touches every import, conflicts with every open branch, and can break things tests do not cover (config paths, Docker, CI, dotted-path strings). So the output of this phase is a reasoned decision, and a move happens only when the decision supports it. Details, smells and the checklist are in `references/structure-and-debt.md`.

1. **Map the tree.** List the packages and modules (`tree -d -I ".venv|__pycache__|node_modules|.git"` or `find`), with file counts and sizes. Note what each top-level folder is for.
2. **Find the structural problems.** Does the layout tell a new reader where things live? Look for dumping-ground modules (`utils`, `helpers`, `common`, `misc`), folders with too many unrelated files, deep nesting with one file per level, one feature scattered over many folders, layers mixed together, circular imports, tests that do not mirror the source, and folders left nearly empty by the dead-code removal.
3. **Estimate the benefit** of each candidate change in terms of **readability** (can someone find the code and guess what a folder contains?) and **maintainability** (does a typical change touch one place instead of five? are dependencies between packages clearer?).
4. **Estimate the cost**: files moved, import statements to rewrite, references outside Python code, whether public import paths change, how well tests cover the affected code, and how many open branches/PRs would conflict (`git branch -r`, ask the user if unknown).
5. **Give one verdict per candidate change:**

   | Verdict | When | What you do |
   |---|---|---|
   | **Optimize now** | Clear benefit, low cost: few files, internal modules only, mechanical import updates, covered by tests, no public path changes | Do it in this pass (rules below). |
   | **Optimize later** | Clear benefit but high cost or risk right now: many files, public API paths, weak tests, active branches that would conflict, a release in progress | Do not move anything. Write a step-by-step migration plan in the report and add it to the tech debt log. |
   | **Leave as is** | Benefit is cosmetic or a matter of taste; the current layout is consistent and people can find things | Say so and why. A stable, familiar layout has value. |

   If benefit and cost are both high, the verdict is *later*, and the user decides. Never start a large restructuring unasked.

6. **When the verdict is "optimize now":**
   - Use `git mv` so history follows the file, and move without editing content in the same commit (git then records it as a rename).
   - Update every reference: imports, `pyproject.toml` (packages, entry points, tool paths, `[tool.vulture] paths`), test config, `mock.patch("dotted.path")` strings, settings with dotted paths, Dockerfile, CI files, docs, and the Vulture whitelist.
   - If a moved module may be imported from outside the repo, leave a thin re-export at the old path and note it as debt to remove later.
   - One structural change per commit (`refactor(structure): ...`), Phase 2 verification after each, then re-run Vulture.

## Final report

End with the report below. Use the real numbers. The reader was not watching you work and may not know the code well, so every section must be understandable on its own: say what the thing is, not just where it is.

````markdown
# Maintenance report: <project>

## Summary
<2-3 sentences: what was done, net lines removed, overall health>

## What changed: folder tree after maintenance
<the tree as it is now, on the branch. Show every folder that contains a change in full;
collapse untouched folders to one line with a file count. Mark every affected file:>

```text
src/shop/
├── orders/
│   ├── service.py            [MODIFIED]  removed 3 unused methods; repository now injected
│   ├── pricing.py            [NEW]       price and discount rules, extracted from service.py
│   └── repository.py         [NEW]       database access for orders, extracted from service.py
├── dates.py                  [SPLIT]     from utils.py: date helpers
├── text.py                   [SPLIT]     from utils.py: string helpers
├── utils.py                  [DELETED]   split into dates.py and text.py
├── legacy/                   [DELETED]   whole package was unused
├── notifications/            [MOVED]     from src/shop/misc/notify/
└── payments/                 (unchanged, 6 files)
vulture_whitelist.py          [NEW]       confirmed false positives for Vulture
pyproject.toml                [MODIFIED]  added [tool.vulture]
```

Legend: [NEW] created · [SPLIT] created by splitting a larger file · [MOVED] same content, new path · [MODIFIED] edited in place · [DELETED] removed

### Files split into smaller files
| Original file (lines) | New files (lines) | What each new file holds | Why it was split |

### New files created
| File | Purpose | Where its content came from (extracted from X / written new) |

<If structure changes are proposed but NOT done, add a second tree titled
"Proposed tree (not applied)" with the same markers, so the user sees the target before approving.>

## Dead code removed
| File | Item | Type | Confidence | Evidence it was unused |

## Kept (false positives - whitelisted)
| Item | Why it is actually used |

## Needs your decision (uncertain / test-only)
| Item | Why it is uncertain | Suggested action |

## Verification
| Check | Baseline | After |
(compile, imports, lint, types, tests - with counts; note pre-existing failures)

## Maintenance rules added
<whitelist, pyproject config, hooks/CI - or "none, offered: ...">

## SOLID review (scope: <scope>)
### Fixed
| Location | Principle | Problem | Change made |
### Recommended (not done)
| Location | Principle | Problem | Proposed refactor | Risk/effort |

## Folder structure (verdict: optimize now / optimize later / leave as is)
| Problem found | Proposed change | Benefit (readability, maintainability) | Cost (files, imports, risk) | Verdict |
<for "later": the migration plan in ordered steps>

## Tech debt found

### Overview (sorted by priority: high impact + small effort first)
| # | Title | Location | Category | Impact (H/M/L) | Effort (S/M/L) | Status (open / fixed in this pass) |

### Details
<one block per row above, same numbering. A one-line "Problem" cell is not enough:
the reader must be able to understand and judge the item without opening the file.>

#### TD-1: <short title>
- **Where:** `path/file.py:120-164`, function `sync_inventory` (plus other occurrences if grouped)
- **What this code is for:** <one or two sentences on the role of this code in the system>
- **What is wrong:** <the concrete problem, with a short snippet (3-10 lines) or the exact evidence, e.g. search result counts>
- **Why it matters:** <the consequence: which bug it can cause, which change it makes hard, who hits it and how often>
- **If left alone:** <what happens over time; say so if the answer is "nothing much">
- **Suggested fix:** <concrete steps, not "refactor this">, effort S/M/L, anything that must be done first (e.g. add tests)

## Proposed action plan (for your review)
<every item that is recommended but NOT done: SOLID recommendations, "optimize later" moves,
tech debt items with Status "open". One numbered row each, so the user can approve by number.
Write "None" if nothing is left.>

| # | Action | Source (TD-n / SOLID / structure) | Files touched | Effort | Risk | Needs first |
|---|---|---|---|---|---|---|

Reply with the numbers to approve (for example "approve 1, 3, 4"), "approve all", or "skip 2". Nothing in this table is done until you approve it.

## Commits
<list of commits on branch>

## Open questions
<always the LAST section. Everything you did not understand or could not decide during the pass.
Write "None" if there are none.>

1. **<the question, answerable in a sentence>**
   - Context: <where it came up: file, finding, or phase, and what you saw>
   - What I assumed / did meanwhile: <the safe default you took, e.g. "left the code untouched">
   - What changes depending on your answer: <option A → ..., option B → ...>
````

Rules for the report:

- **The tree shows the real end state.** Build it from `git diff --stat --name-status <base>...HEAD` plus the actual tree, not from memory. Every [NEW], [SPLIT], [MOVED] and [DELETED] entry must correspond to a real change on the branch, and every such change must appear in the tree.
- **Tech debt details carry the context.** If you cannot fill in "What this code is for" or "Why it matters", you do not understand the item well enough yet: read more, or move it to Open questions.
- **Open questions come last and are never guessed away.** See the open-questions section below.
- **Save the report to a file as well as showing it:** `.maintenance/maintenance-report-<YYYY-MM-DD>.md` in the repo (add `.maintenance/` to `.git/info/exclude` so it is never committed), and tell the user the path. Re-save it after every action round so the statuses stay true.
- **End with the action plan.** The report always closes the review stage with the "Proposed action plan" table, so the user can verify it and move to action (next section).

## Review gate: from plan to action

The pass has two stages. **Stage 1 (review)** is everything above: it changes only what is safe and clear (dead code, whitelist, small covered refactors) and ends with the report and the **Proposed action plan**. **Stage 2 (action)** starts only when the user verifies the plan.

- **What counts as verification.** An explicit message from the user approving items ("approve 1 and 3", "verified, go ahead", "approve all", "do the later items"). Silence, a thumbs-up on the report, or "looks good" about the report as a whole is not approval of the risky items: ask which numbers. Approval covers only the numbers named; it does not carry over to later passes.
- **Execute only approved rows, in the plan's order,** respecting each row's "Needs first" (for example add tests before splitting a function). One commit per row, `refactor: ...` / `refactor(structure): ...` / `test: ...`, with Phase 2 verification before each commit. If verification fails, revert that row, say why, and continue with the next approved row only if it does not depend on the failed one.
- **Stay inside the approved scope.** If an approved action reveals new debt or needs a wider change (public API, other modules, an unexpected test dependency), stop that row, log it, and ask; do not widen the change on your own.
- **Structure moves** (an approved "optimize later" item) follow the Phase 5 rules for "optimize now": `git mv` without content edits, update every reference, one structural change per commit, shim for externally imported paths. Before moving, re-check `git branch -r` and tell the user which branches will conflict.
- **After the action round:** re-run Vulture and the full checks, update statuses in the Tech debt overview ("fixed in this pass"), the folder tree, the Commits list and the saved report file, then show a short summary of what was done, what failed or was skipped, and what is still open. Rows the user skipped stay in the plan as open.
- **Never push, open a PR or merge** as part of action unless the user asked for that separately.

## Open questions (collect through every phase)

Whenever you hit something you do not understand or cannot decide from the code alone, do not guess and do not silently skip it. Take the safe default (normally: leave the code as it is), add the question to a running list next to the tech debt log, and carry on. Typical cases: a function that looks unused but has a name suggesting external callers; business rules whose intent is unclear; two conflicting conventions with no way to tell which is the intended one; whether modules are imported by other repositories; whether a failing baseline test is known.

Stop and ask immediately only when the answer blocks the whole pass (for example a dirty git tree, or no way to run the tests). Everything else goes to the **Open questions** section at the very end of the report, each with its context, the assumption you worked under, and what would change depending on the answer, so the user can answer all of them in one reply.

If the user asked only for part of this (for example "just find dead code, don't delete"), run only the relevant phases, but still do Phase 0, still verify after any change you make, and still keep the tech debt log, since it costs almost nothing while you are already reading the code.
