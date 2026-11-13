# CLAUDE.md

Rules for writing and changing Python code in this repository. They apply to every change, including small fixes.

## 1. Code must explain itself

A reader should understand what the code does and why from the names and structure alone, without running it and without relying on comments.

### Names carry the meaning

- Name things after what they mean in the domain, not their type or position: `overdue_invoices`, not `data`, `lst`, `tmp`, `x`, `res`.
- No abbreviations unless they are standard in the domain (`url`, `id`, `http` are fine; `usr_cnt`, `proc_ord` are not).
- Functions and methods are verbs that state the outcome: `calculate_net_total`, `send_reminder_email`.
- Booleans read as a yes/no question: `is_active`, `has_expired`, `can_retry`.
- Collections are plural, single items singular: `for order in orders`.
- Include the unit when it matters: `timeout_seconds`, `price_cents`.
- Replace magic values with named constants: `MAX_LOGIN_ATTEMPTS = 5`.
- Short names (`i`, `e`, `f`) only in a scope of a few lines.

### Functions are small and do one thing

- Do not put a whole workflow in one function. Split it into steps, each a well-named function, so the top-level function reads like a summary of the process.
- One level of abstraction per function: a function either coordinates steps or does the detailed work, not both.
- Name complex conditions and expressions instead of inlining them:

```python
# avoid
if u.age >= 18 and u.verified and not u.banned and u.country in ALLOWED:

# prefer
is_eligible = user.is_adult and user.is_verified and not user.is_banned
if is_eligible and user.country in ALLOWED_COUNTRIES:
```

- Prefer early returns over deep nesting. More than two levels of indentation in a function is a sign to extract.
- Few parameters. When several values always travel together, group them in a dataclass.
- No boolean flag parameters that switch behaviour; write two functions.
- Separate functions that compute a value from functions that cause side effects (I/O, DB, network).

### Example

```python
# avoid: one function, unclear names, everything mixed
def process(d):
    r = []
    for i in d:
        if i["s"] == 1 and i["a"] > 0:
            r.append(i["a"] * 0.9)
    db.save(sum(r))
    return sum(r)

# prefer: the top-level function reads as the process
def record_discounted_revenue(orders: list[Order], ledger: Ledger) -> Decimal:
    payable_orders = select_payable_orders(orders)
    discounted_total = sum_with_discount(payable_orders, LOYALTY_DISCOUNT_RATE)
    ledger.record_revenue(discounted_total)
    return discounted_total
```

### Comments and types

- Type hints on every function signature; they are part of the meaning.
- Comments explain why (a business rule, a trade-off, a workaround), never what. If a comment is needed to explain what the code does, rename or extract instead.
- No commented-out code; git history keeps it.

## 2. Follow SOLID

All new and modified code must satisfy these. Never introduce a new violation while fixing something else.

- **Single Responsibility**: a module, class or function has one reason to change. Keep business rules, I/O (database, HTTP, files) and presentation apart.
- **Open/Closed**: add a new variant by adding code, not by editing an existing `if/elif` or `isinstance` chain. Use polymorphism, a registry, or a strategy function.
- **Liskov Substitution**: a subclass works anywhere its base does. Same signature, no `NotImplementedError` overrides, no stricter preconditions. Prefer composition when there is no true "is-a".
- **Interface Segregation**: depend on the smallest interface needed. Use small `typing.Protocol`s; pass `user.email` rather than `user` when that is all that is used.
- **Dependency Inversion**: business logic receives its dependencies (DB clients, HTTP sessions, clock, config) through parameters or the constructor, typed against a `Protocol`. Concrete objects are created at the application entry point only.

Stay pragmatic: do not add an interface for a single implementation with no foreseeable second one, and do not split a small cohesive class just to satisfy a rule. If following a principle would add more complexity than it removes, keep the simpler code and say so.

## 3. When changing existing code

- Keep behaviour the same unless the task says otherwise. Run the tests, linter and type checker before and after; no new failures.
- Apply the rules above to the code you touch. Rename unclear names and extract oversized functions in the area you are working on, as a separate commit from the functional change.
- Larger restructuring (public API changes, cross-module refactors, code without tests) is proposed first, not done unasked.
- Remove code that your change makes unused.

## 4. Codebase maintenance

For clean-up tasks (dead code, unused imports, tech debt, SOLID review), use the `python:maintain-codebase` skill. It removes dead code with Vulture, verifies nothing broke, saves the maintenance rules, and reviews the code against SOLID.
