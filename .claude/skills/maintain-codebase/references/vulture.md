# Vulture reference

Source: https://github.com/jendrikseipp/vulture

## Contents
- How it works (and why it is wrong sometimes)
- Command cheat sheet
- Confidence values
- Exit codes
- Suppressing false positives
- Common false positives by framework
- Configuration, pre-commit, CI
- Programmatic use

## How it works

Vulture parses every given file with `ast`, records the names that are *defined* and the names that are *used*, and reports definitions whose name is never used. It **ignores scopes and only compares names**. Consequences:

- A method `save` is considered used if *anything* named `save` is used anywhere in the scanned files. So Vulture also has false **negatives**: a clean report does not prove there is no dead code.
- Anything used only by name-as-string, by a framework, or from files you did not pass in is reported as unused (false positive).
- Unreachable code is found after `return`, `break`, `continue`, `raise`, and under unsatisfiable `if`/`while` conditions.

Always pass every path that may use the code (source, tests, scripts, whitelist).

## Command cheat sheet

```bash
vulture src/ tests/                          # basic scan
python -m vulture src/ tests/                # same, without the console script
vulture src/ tests/ --min-confidence 100     # only certain findings
vulture src/ tests/ --sort-by-size           # biggest unused chunks first
vulture src/ tests/ --exclude "*/migrations/*,*/.venv/*,*settings.py"
vulture src/ --ignore-names "visit_*,do_*"
vulture src/ --ignore-decorators "@app.route,@pytest.fixture"
vulture src/ tests/ --make-whitelist > vulture_whitelist.py
vulture src/ tests/ vulture_whitelist.py     # scan with whitelist
vulture --config path/to/pyproject.toml
```

Output format is pyflakes-style: `path:line: unused <type> '<name>' (<N>% confidence)`.

Exclude patterns are matched against **absolute paths**.

## Confidence values

| Code type | Confidence |
|---|---|
| function/method/class argument, unreachable code | 100% |
| import | 90% |
| attribute, class, function, method, property, variable | 60% |

100% means certain *within the analysed files*. Values below 100% are rough estimates based only on the kind of code.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | No dead code found |
| 1 | Invalid input (file missing, syntax error, wrong encoding) |
| 2 | Invalid command line arguments |
| 3 | Dead code found |

Exit code 3 is the normal "findings" result, not a crash.

## Suppressing false positives (in order of preference)

1. **Whitelist module** (recommended). A Python file that "uses" the names, passed as an extra path. `--make-whitelist` generates one; prune it to confirmed false positives only, otherwise it hides real dead code. Hand-written entries look like:

   ```python
   # vulture_whitelist.py
   from mypkg.greeter import Greeter
   Greeter.greet            # called via getattr in cli.py
   ```

   Add a short comment per entry saying *why* it is used; future maintainers need the reason.
2. **Underscore prefix / `del`** for arguments and tuple parts that must exist but are unused: `def handler(_event, ctx)`, `_x, y = pos()`, or `del event` in the body.
3. **`--ignore-decorators`** for registration decorators (`@app.route`, `@celery.task`). Note `@foo.bar(x)` is simplified to `@foo.bar`.
4. **`--ignore-names`** for naming conventions (`visit_*`, `test_*`).
5. **`--exclude`** for whole files/dirs (generated code, migrations).
6. **`# noqa: F401`** (unused import) and **`# noqa: F841`** (unused local) are honoured, but add noise; prefer the whitelist.
7. Unreachable `if False:` blocks: use a named flag (`debug = False` / `if debug:`).
8. Type annotations in string form (`"Sequence"`) can make the import look unused: use `from __future__ import annotations` and real names.

## Common false positives by framework

Check these before deleting anything at 60%:

- **Python itself**: dunder methods, `__all__` exports, names accessed via `getattr`/`globals()`/`importlib`, `TYPE_CHECKING` imports, `Enum` members, dataclass / `NamedTuple` / `TypedDict` fields, `Protocol` and ABC method overrides, `__init__.py` re-exports, side-effect imports.
- **pytest**: fixtures (used by argument name), `conftest.py` hooks (`pytest_*`), `test_*` functions, parametrize ids.
- **Django**: `settings.py` constants, model fields and `Meta`, `urlpatterns`, admin classes, management commands (`Command.handle`), signals/receivers, migrations, middleware methods, template tags/filters, `AppConfig.ready`, form `clean_<field>`.
- **FastAPI / Flask**: route handlers, dependencies, exception handlers, `before_request`/lifespan hooks, Pydantic model fields.
- **Pydantic**: fields, `@field_validator`/`@model_validator`, `model_config`.
- **SQLAlchemy**: columns, relationships, `__tablename__`, event listeners.
- **Celery / RQ**: tasks referenced by name string, signal handlers.
- **Click / Typer / argparse**: command functions, callbacks.
- **Entry points & plugins**: anything named in `[project.scripts]`, `[project.entry-points]`, `setup.py entry_points`.
- **Serialization / reflection**: attributes read via `__dict__`, `vars()`, `asdict`, JSON/ORM mappers, `unittest.mock.patch("dotted.path")` targets.
- **Libraries**: the whole public API.

## Configuration

`pyproject.toml`, section `[tool.vulture]`: take the CLI flag, drop the leading dashes, turn remaining dashes into underscores. CLI options override the file. Vulture reads `pyproject.toml` from the current working directory.

```toml
[tool.vulture]
paths = ["src", "tests", "vulture_whitelist.py"]
exclude = ["*/migrations/*", "*/.venv/*"]
ignore_decorators = ["@app.route", "@require_*"]
ignore_names = ["visit_*", "do_*"]
min_confidence = 80
sort_by_size = true
```

## pre-commit

```yaml
repos:
  - repo: https://github.com/jendrikseipp/vulture
    rev: "v2.3"   # or any later version; pin to the version the project installs
    hooks:
      - id: vulture
```

The hook needs `[tool.vulture] paths` in `pyproject.toml`.

## CI (generic)

```bash
pip install vulture
vulture            # uses [tool.vulture]; non-zero exit fails the job
```

## Programmatic use

```python
import vulture

v = vulture.Vulture()
v.scavenge(["src", "tests"])
for item in v.get_unused_code():   # list of Item objects
    print(item.filename, item.first_lineno, item.typ, item.name, item.confidence)
```

## Complementary tools

- `coverage` finds unused code more reliably, but only for code paths that tests or a real run actually execute. Useful as second evidence for a 60% finding.
- `ruff`/`pyflakes` catch unused imports and locals within a single file.
