# SOLID in Python: smells, detection, fixes

Use this as a lens for Phase 4. For each principle: what a violation looks like in Python, how to spot it quickly, and the smallest refactor that fixes it. Python is duck-typed, so prefer `typing.Protocol`, plain functions and composition over deep class hierarchies.

## Contents
- S - Single Responsibility
- O - Open/Closed
- L - Liskov Substitution
- I - Interface Segregation
- D - Dependency Inversion
- When NOT to refactor
- Safe refactoring procedure

## S - Single Responsibility

*A module/class/function has one reason to change.*

**Smells**
- Class or module named `Manager`, `Helper`, `Utils`, `Handler` that keeps growing.
- One function that validates input, talks to a DB/HTTP API, applies business rules, and formats output.
- Import list mixing layers (`requests`, `sqlalchemy`, `jinja2`, domain modules) in one file.
- Methods that use disjoint subsets of `self` attributes (low cohesion).
- A test needs many unrelated mocks to exercise one method.

**Detect**: very long files/classes/functions; many unrelated imports; `ruff` complexity rules (`C901`, `PLR0912`, `PLR0915`) if available.

**Fix**: extract by reason-to-change: pure domain logic, I/O (repositories/clients), presentation. Keep the old entry point as a thin orchestrator so callers do not change.

```python
# before
class ReportService:
    def run(self, user_id):
        rows = psycopg.connect(DSN).execute(SQL, [user_id]).fetchall()   # persistence
        total = sum(r.amount for r in rows if not r.refunded)            # business rule
        smtplib.SMTP(HOST).sendmail(FROM, TO, f"Total: {total}")         # delivery

# after
class ReportService:
    def __init__(self, orders: OrderRepository, notifier: Notifier): ...
    def run(self, user_id):
        total = net_total(self.orders.for_user(user_id))   # pure function
        self.notifier.send(f"Total: {total}")
```

## O - Open/Closed

*Add behaviour by adding code, not by editing existing, working code.*

**Smells**
- `if kind == "a": ... elif kind == "b": ...` or `isinstance` ladders, especially the *same* ladder repeated in several places.
- Every new variant requires touching a central function.
- Boolean flag parameters that switch behaviour (`def export(data, as_csv=False, as_xml=False)`).

**Detect**: `grep -rn "elif .* ==" `, `grep -rn "isinstance("`, repeated `match` statements on the same discriminator.

**Fix**: polymorphism (`Protocol` + one class per variant), a registry dict / decorator, `functools.singledispatch`, or passing a strategy callable.

```python
EXPORTERS: dict[str, Callable[[Data], bytes]] = {}

def exporter(fmt):
    def register(fn):
        EXPORTERS[fmt] = fn
        return fn
    return register

@exporter("csv")
def to_csv(data): ...

def export(data, fmt):
    return EXPORTERS[fmt](data)      # new formats never edit this function
```

Note: functions registered by decorator look unused to Vulture. Add them to the whitelist or `ignore_decorators`.

A single `if/elif` in one place with two or three stable cases is fine. Refactor when the ladder is duplicated or keeps growing.

## L - Liskov Substitution

*A subclass must be usable wherever its base is expected.*

**Smells**
- Override raises `NotImplementedError` or is an empty `pass` for a method the base promises.
- Override changes the signature (fewer params, different types, different return type, returns `None` where base returns a value).
- Override adds stricter preconditions or raises new exception types callers do not expect.
- Callers check `isinstance(x, SubClass)` to special-case one child.
- Inheritance used for code reuse where there is no real "is-a" (classic: `Square(Rectangle)`, `ReadOnlyFile(File)` with a throwing `write`).

**Detect**: `grep -rn "NotImplementedError"` outside abstract bases; mypy/pyright override errors; `isinstance` checks against subclasses in callers.

**Fix**: narrow the base to what all children truly support (pair with ISP), replace inheritance with composition, or make the hierarchy honest (separate `Readable` / `Writable`).

## I - Interface Segregation

*Clients should not depend on methods they do not use.*

**Smells**
- Large ABC where most implementers stub several methods.
- A function accepts a rich object but uses one attribute/method of it.
- "God" protocol/service object passed everywhere.

**Fix**: small role-based `Protocol`s; depend on the narrowest one.

```python
class Reader(Protocol):
    def read(self, key: str) -> bytes: ...

class Writer(Protocol):
    def write(self, key: str, data: bytes) -> None: ...

def load_config(store: Reader) -> Config: ...     # needs only read
```

Often the narrowest interface is just a callable or a plain value: pass `user.email`, not `user`.

## D - Dependency Inversion

*High-level policy depends on abstractions; details are injected.*

**Smells**
- Business logic instantiates its collaborators: `requests.Session()`, `boto3.client(...)`, DB engines, `open(...)` on fixed paths inside domain functions.
- Module-level singletons and globals imported by domain code; reads of `os.environ` deep inside logic.
- Hidden inputs: `datetime.now()`, `random`, `uuid4()` inline.
- Tests rely heavily on `mock.patch("module.path.Thing")`: a strong sign the dependency should be a parameter.
- Domain package imports from infrastructure/framework packages (wrong direction).

**Fix**: constructor or parameter injection, typed against a `Protocol`. Keep behaviour identical by defaulting to the current concrete implementation at the *composition root* (main/app factory), not inside the domain.

```python
class Clock(Protocol):
    def now(self) -> datetime: ...

class TokenService:
    def __init__(self, store: TokenStore, clock: Clock):
        self._store, self._clock = store, clock
```

For a minimal, backwards-compatible first step: `def __init__(self, session: Session | None = None): self._session = session or Session()`.

## When NOT to refactor

SOLID exists to make change cheap. Skip or only report when:

- There is one implementation and no realistic second one: an interface adds indirection without benefit (YAGNI).
- The code is a small script, a one-off migration, or generated/vendored.
- The class is small and cohesive; splitting it would scatter one idea over several files.
- The code has no tests and the refactor is not mechanical. Recommend adding characterisation tests first.
- The change would alter a public API. Propose it; do not do it unasked.

Report these as "reviewed, intentionally left" with the reason, so the user can see the principle was considered.

## Safe refactoring procedure

1. Confirm tests cover the code (run them, or check coverage). If not, write a characterisation test that pins current behaviour first.
2. One refactor at a time; keep public names and signatures stable (leave a thin delegating wrapper if needed).
3. Run Phase 2 verification.
4. Commit as `refactor:` separately from dead-code removal.
5. Re-run Vulture: extractions often orphan old helpers.
