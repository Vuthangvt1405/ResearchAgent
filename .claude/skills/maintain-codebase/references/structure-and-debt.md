# Folder structure and tech debt reference

## Contents
- Part A - Tech debt: categories and how to find them
- Part A - Rating and prioritising
- Part B - Size limits: folder width, Rule of Three, depth cap
- Part B - Folder structure smells
- Part B - What a good Python layout looks like
- Part B - Cost checklist
- Part B - Worked verdict examples
- Part B - Writing an "optimize later" migration plan

---

## Part A - Tech debt

Tech debt is anything that makes the next change slower, riskier or harder to understand than it needs to be. Log what you see while doing the other phases, and run the quick searches below once to catch what you did not happen to read.

### Categories and detection

| Category | What to look for | Quick search |
|---|---|---|
| Deferred work | `TODO`, `FIXME`, `HACK`, `XXX`, "temporary", "workaround" | `grep -rnE "TODO|FIXME|HACK|XXX|temporary|workaround" --include="*.py"` |
| Duplication | Same logic copy-pasted in several places, parallel `if/elif` ladders | noticed while grepping usages; `ruff` / `pylint --disable=all --enable=duplicate-code` if available |
| Complexity | Very long functions/classes/files, deep nesting, many parameters | `wc -l` sorted; `ruff check --select C901,PLR0912,PLR0913,PLR0915` if ruff is present |
| Unclear code | Names like `data`, `tmp`, `x`, `mgr`; magic numbers; whole workflow in one function | reading during triage |
| Error handling | Bare `except:`, `except Exception: pass`, swallowed errors, errors logged and ignored | `grep -rnE "except( Exception)?:\s*$" -A1 --include="*.py"` |
| Typing gaps | Public functions without type hints, widespread `Any`, many `# type: ignore` | `grep -rn "type: ignore" --include="*.py" \| wc -l` |
| Suppressed checks | `# noqa`, `# pylint: disable`, skipped/xfail tests without a reason | `grep -rnE "noqa|pylint: disable|pytest.mark.skip|xfail" --include="*.py"` |
| Test debt | Modules with no tests, tests that only patch everything, slow or flaky tests | compare `src/` tree to `tests/` tree; coverage report if available |
| Dependency debt | Unpinned or very old dependencies, unused dependencies, deprecated APIs, deprecation warnings in the test output | read `pyproject.toml`/`requirements*.txt`; warnings summary from pytest |
| Config / secrets | Hard-coded URLs, credentials, paths, environment-specific values in code | `grep -rnE "(password|secret|api_key|token)\s*=" --include="*.py"` |
| Coupling | Circular imports, imports inside functions to dodge cycles, domain code importing infrastructure | `grep -rnE "^\s+(from|import) " --include="*.py"` (indented imports) |
| Compatibility leftovers | Shims for Python versions no longer supported, feature flags that are always on/off, deprecated aliases | `grep -rnE "sys.version_info|six\.|__future__" --include="*.py"` |
| Structure | See Part B | - |
| Docs drift | README/docstrings that describe removed or renamed things | noticed during dead-code removal |

Report secrets found in code to the user prominently, at the top of the report, not as an ordinary row.

### Log entry format

Capture the context at the moment you see the problem; it is expensive to reconstruct later. Each entry needs enough for someone who has never opened the file:

```markdown
### <short title>
- Where: `path/to/file.py:120-164`, function/class name
- Category: <from the table above>
- What this code is for: its role in the system, 1-2 sentences
- What is wrong: the concrete problem + a 3-10 line snippet or the exact evidence
- Why it matters: the consequence (bug risk, blocked change, who hits it, how often)
- If left alone: what happens over time
- Suggested fix: concrete steps; prerequisites (e.g. tests first)
- Impact: H/M/L. Effort: S/M/L.
```

Weak: "`sync.py:88` - bare except." Good: "`sync.py:88`, `sync_inventory` runs nightly to copy stock levels from the warehouse API. The whole loop is wrapped in `except Exception: pass`, so when the API returns an error the job reports success and stock stays stale; nobody finds out until customers order items that are out of stock. Fix: catch `WarehouseApiError`, log it, and let the job fail."

### Rating

- **Impact** - how much it hurts: H = causes bugs, blocks changes, or is hit on most changes in that area; M = slows work or confuses readers regularly; L = cosmetic or rarely touched code.
- **Effort** - S = under an hour, mechanical; M = a day or so, needs tests; L = multi-day or cross-module.
- **Priority order** in the report: H/S first (quick wins), then H/M, H/L, M/S, and so on. Debt in code that changes often matters more than debt in stable code; `git log --format= --name-only --since="6 months ago" | sort | uniq -c | sort -rn | head -20` shows the hotspots.

Group repeated instances ("bare except in 14 places, e.g. a.py:10, b.py:88") instead of listing 14 rows.

---

## Part B - Folder structure

### Size limits

Three measurable rules. They turn "this folder feels messy" into a number you can report, and they apply both to the review and to any folder you create or fill.

| Rule | Limit | Why |
|---|---|---|
| **Folder width (7 ± 2)** | Aim for 5-9 entries per folder (modules + subfolders, not counting `__init__.py`, `__pycache__`, `py.typed`). Over ~10-12 is a finding. | A developer can take in 5-9 items at a glance, without scrolling and without losing track of what the folder is for. Past ~10-12 the listing stops showing the architecture, and people fall back on fuzzy file search. |
| **Rule of Three (when to split)** | Make a subfolder only when at least 3 files share a distinct sub-domain or responsibility. Never a subfolder for 1 or 2 files. | Splitting earlier adds a navigation tax: clicking through a folder to reach a single file, and a longer import, for no gain in clarity. |
| **Depth cap** | At most 3, at most 4, levels below the root package (`pkg/a/b/c/module.py` is 3). | Deep paths hide where responsibilities live and make every import statement noisy. |

How they work together:

- **A wide folder is split by the Rule of Three.** Group its files by responsibility, and promote only groups of 3 or more into a subfolder. If no such group exists, the folder stays wide; report it rather than inventing folders. A flat folder of 11 files is better than three folders of 2-3 unrelated files each.
- **Splitting must not break the depth cap.** If the only way to narrow a folder adds a fourth or fifth level, prefer a sibling package higher up, or leave it wide.
- **The reverse holds too.** A subfolder with 1-2 files (often left behind by dead-code removal) goes back into its parent, unless the parent would then cross the width limit.
- **Tests mirror the source**, so a split in the source is mirrored in `tests/`, and `tests/` gets the same width check.
- The limits trigger a finding, not a move. The verdict (now / later / leave as is) still comes from benefit vs cost below. A folder at 11 entries with one clean convention can be **leave as is**.

Measuring (run from the repo root; adjust the excludes):

```bash
# width: entries per folder, widest first
find <pkg> tests -type d -not -path "*/__pycache__*" | while read -r d; do
  n=$(find "$d" -mindepth 1 -maxdepth 1 -not -name "__init__.py" -not -name "__pycache__" -not -name "py.typed" | wc -l)
  echo "$n $d"; done | sort -rn | head -20
# Rule of Three: subfolders holding fewer than 3 modules
find <pkg> -type d -not -path "*/__pycache__*" | while read -r d; do
  n=$(find "$d" -maxdepth 1 -name "*.py" -not -name "__init__.py" | wc -l)
  [ "$n" -lt 3 ] && [ "$d" != "<pkg>" ] && echo "$n $d"; done
# depth: deepest modules below the root package
find <pkg> -name "*.py" -not -path "*/__pycache__*" | awk -F/ '{print NF-2, $0}' | sort -rn | head -10
```

Report each folder over a limit with its count and a proposed grouping, for example: "`app/workspace/` has 12 modules (limit ~10-12). Six of them are about datasets (`dataset_service`, `dataset_pool`, `dataset_sources`, `datasets_store`, ...), so the Rule of Three allows `app/workspace/datasets/` at depth 2."

### Smells

- **Dumping grounds**: `utils.py`, `helpers/`, `common/`, `misc/`, `core/` holding unrelated things. Hard to guess what is inside; grows forever.
- **Overfull folder**: more than ~10-12 entries in one folder (see "Size limits"), worst when the modules are unrelated.
- **Premature folder**: a subfolder holding only 1-2 files (breaks the Rule of Three).
- **Giant module**: one file of several thousand lines containing several concepts.
- **Needless depth**: more than 3-4 levels below the root package, or `a/b/c/d/thing.py` where each level has one child.
- **Scattered feature**: changing one feature requires edits in many distant folders (`models/x.py`, `views/x.py`, `services/x.py`, `schemas/x.py`, `utils/x.py`) and the project is large enough for that to hurt.
- **Mixed layers**: HTTP/CLI handlers, business rules and database code in the same module or package (also an SRP/DIP problem).
- **Circular imports** between packages, or imports inside functions to avoid them: the package boundaries are in the wrong place.
- **Inconsistent conventions**: some features grouped by layer, others by feature; mixed naming (`userService.py`, `order_service.py`).
- **Tests do not mirror source**: hard to find the test for a module.
- **Leftovers**: packages nearly empty after dead-code removal, empty `__init__.py`-only folders, scripts and notebooks mixed into the package.
- **Top-level clutter**: importable code at repo root next to config files (no `src/` or single package dir).

### What good looks like

No single correct layout; judge by these properties:

- A new reader can guess where a thing lives from its name, and guess what a folder contains from its name.
- Things that change together live together (high cohesion); packages depend on each other in one direction.
- Every folder within the size limits: 5-9 entries, no subfolder with fewer than 3 files, at most 3-4 levels deep.
- One convention, applied consistently. Small projects: flat and by layer is fine. Larger projects: group by feature/domain, layers inside each.
- `tests/` mirrors the source tree.
- The package's public API is what `__init__.py` exports; internals can then move freely.

Follow the framework's convention where one exists (Django apps, FastAPI routers). Fighting the framework layout costs more than it gives.

### Cost checklist

Count or check each before giving a verdict:

1. Files to move, and import statements to rewrite (`grep -rn "from old.path\|import old.path"`).
2. Non-import references: `pyproject.toml` (packages, entry points, tool config), `setup.cfg`, `MANIFEST.in`, pytest/coverage/mypy/ruff paths, Dockerfile, CI workflows, Makefile, docs, `mock.patch("...")` strings, Django `INSTALLED_APPS`/settings strings, Celery task names, logging config, Alembic/Django migration references, pickled or stored dotted paths.
3. Public import paths: is this a library, or are modules imported by other repos/services? If yes, the old path must keep working (re-export shim) or the change needs a deprecation cycle.
4. Test coverage of the affected code. Low coverage = moves can break things silently.
5. Open branches / PRs touching the same files: every one will conflict.
6. Timing: release freeze, ongoing large feature work.
7. Reviewability: can it be done as a few rename-only commits?

Rough guide: **low cost** = up to roughly 10-15 files, internal only, all references found by grep, tests green and meaningful, no long-lived branches on those files. Anything involving public paths, stored dotted paths, or weak tests is **high cost** regardless of size.

### Worked verdict examples

- *`utils.py` (400 lines) holds date helpers, string helpers and an HTTP retry wrapper; imported from 9 internal modules; tests cover it.* Benefit: clear. Cost: low. → **Optimize now**: split into `dates.py`, `text.py`, `http_retry.py`, update 9 imports.
- *Application grouped by layer with 120 modules; features are scattered; three teams have open branches.* Benefit: high. Cost: high. → **Optimize later**: migration plan, one feature per PR, starting with the least active area.
- *Library where `mylib.core.parser` would read better as `mylib.parsing`.* Public path. → **Optimize later** with a re-export and deprecation warning, only if the user wants it.
- *Small service, 15 modules in one flat package, consistent naming.* Benefit: cosmetic. → **Leave as is**.
- *`legacy/` package where dead-code removal left one 20-line module.* → **Optimize now**: move the module next to its only caller, delete the package.

### Writing an "optimize later" migration plan

Make it executable by someone else later:

1. Target tree (before/after sketch of the affected part only).
2. Ordered steps, each small enough for one PR and independently shippable; least risky and least active areas first.
3. For each step: files moved, references to update, shim needed or not.
4. Preconditions: tests to add first, branches to merge first, announcement to the team.
5. How to verify each step (Phase 2 checks plus any path-specific check such as building the Docker image).
6. When to remove temporary re-export shims.
