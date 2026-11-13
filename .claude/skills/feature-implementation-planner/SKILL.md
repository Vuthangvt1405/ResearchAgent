---
name: feature-implementation-planner
description: Plan a new feature in read-only PLAN MODE before any code is changed - understand the requirement (User Stories + Acceptance Criteria), study the codebase to learn its patterns, map the database schema and entity relationships, design API endpoints and request/response DTOs field by field, review security (OWASP API Top 10), draw one workflow diagram, write a TDD plan with positive tests plus every negative case (incl. security), and finish with questions for the user to confirm, saving the whole plan to a single Markdown plan file; then, only after the user approves the plan, create a compile-ready scaffold (files, DTOs, endpoint signatures, migration file, failing test skeletons) with NO business logic, then stop until the user verifies it. Use this skill whenever the user asks to implement, build, add, or plan a new feature, endpoint, API, or ticket/story, pastes a user story or acceptance criteria, or says things like "implement this ticket", "add a feature for X", "how would you build X in our code", even if they don't explicitly ask for a plan.
---

# Feature Implementation Planner (Plan Mode)

Turn a feature request into a clear, reviewable implementation plan, then a scaffold. Steps 1–8 produce the plan in read-only plan mode; Step 9 builds the scaffold only after the user approves; Step 10 is a hard stop where the agent self-verifies the scaffold and the user must verify it before any logic is written. The plan follows eight steps, always in this order, because each step depends on the one before it: you cannot design the schema without knowing the requirement, and you cannot design DTOs without knowing the schema.

Worked examples: `references/example-output.md` for the plan (Steps 1–8) and `references/example-scaffold.md` for the scaffold (Step 9).

---

## 📄 Plan file: everything goes into one `.md` file

All output of this skill is written to **one Markdown plan file**, so the user can review, comment on, and commit it like any other doc. The conversation gets only a short pointer.

**Where:**
- If the project already keeps feature docs (e.g. `docs/features/`, `docs/specs/`), put it there in a `plans/` subfolder: `docs/features/plans/<ID>-<slug>-plan.md`, e.g. `docs/features/plans/US-4-loading-indicator-plan.md`.
- Otherwise use `docs/plans/<ID>-<slug>-plan.md`. Without a ticket/story id, use the feature slug only.
- If a plan file for this feature already exists, update it instead of creating a second one.

**What goes in it, and when:**

| When | Written to the plan file |
|---|---|
| End of Step 8 | The full plan, Steps 1–8, using the Output template headings |
| User answers questions | The plan updated in place, plus a row per decision in `## Decision log` |
| Step 9 done | A **separate scaffold report file** `<ID>-scaffold-report.md`, next to the plan, with `## 9. Scaffold report`; the plan gets a `## 9–10. Scaffold report & verification` section that only links to it |
| Step 10 done | `## 10. Verification` appended to the scaffold report file (self-check table + user checklist); the status line updated in both files |

Keep a status line under the title and update it at each stage: `Status: Draft — awaiting answers` → `Approved — scaffold pending` → `Scaffolded — awaiting verification` → `Verified — implementing`.

**What goes in the chat reply:** a clickable link to the plan file, a 3–5 line summary (approach, files affected count, test count, schema change yes/no), and the Step 8 questions copied as a numbered list so the user can answer without opening the file. Don't paste the whole plan into the chat.

---

## ⛔ Plan mode: read-only, no changes (Steps 1–8)

Steps 1–8 run in **plan mode**. Its only output is the plan file (see "Plan file" above). The reason: the user wants to review and correct the design before anything is touched, and a half-applied change is harder to review than a plan.

**Allowed (read-only):**
- Reading files, listing directories, searching code (`ls`, `cat`, `grep`, `find`, `rg`)
- Read-only git commands (`git log`, `git show`, `git diff`, `git blame`, `git status`)
- Reading schema files, migrations, ORM entities, and DB docs
- Read-only DB inspection only if the user provides access (`SELECT`, `\d`, `DESCRIBE`) — never against production unless told it is safe
- **The one write exception:** creating and updating the plan `.md` file itself (and its `plans/` folder)

**Not allowed:**
- Creating, editing, renaming, or deleting any other file — including tests, migrations, configs, and "scratch" files in the repo
- Running migrations, seeders, `INSERT`/`UPDATE`/`DELETE`/`ALTER`, or any write to a database
- Installing packages, running generators/scaffolding, formatters that rewrite files, `git commit`/`checkout`/`stash`/`push`
- Writing production code or test code into files. Test names and short illustrative snippets inside the plan text are fine.

Planned changes (new tables, columns, migrations, files) are **described** in the plan, never applied. If a tool or instruction would modify something, stop and list it under Step 8 instead. Plan mode ends after Step 8. The only way out is the user explicitly approving the plan; then Step 9 (scaffold) may create files, within its own strict limits.

---

## Step 1 — Understand the requirement (US + AC)

Restate the requirement in your own words so the user can catch misunderstandings early.

**User Stories**: write one per distinct actor or goal.
> As a **[role]**, I want **[capability]**, so that **[business value]**.

**Acceptance Criteria**: write them as Given/When/Then and number them, so tests can reference them (AC1, AC2, ...).
> **AC1**: Given [precondition], When [action], Then [observable result].

**Input from `jira-story-writer`**: if the requirement is a ticket in that skill's format (Summary, User Story, numbered Given/When/Then ACs, Developer Notes, Out of Scope, Dependencies, Open Questions, story points), or a story file in `docs/features/user-story/`, use it as the source of truth:
- Copy the User Story and ACs as-is, keeping their numbers (AC1, AC2…), so tests and the ticket reference the same IDs.
- Treat Developer Notes as hints to check in Step 2, not as decisions. Anything marked *(assumption)* must be confirmed against the codebase.
- Copy Out of Scope and Dependencies as they are.
- Carry the ticket's Open Questions into Step 8, unless the codebase answers them (then say so and cite the file).
- If the plan shows the story is clearly bigger than its points (e.g. a schema change on a 2-pointer), say so in Step 8 and suggest re-estimating or splitting it with `jira-story-writer`.
- Link the ticket/story in the plan file's `Source:` line.

If there is no ticket and the requirement is rough (a client message, notes, an idea), suggest running `jira-story-writer` first. If the user wants to go on without it, write the US/AC yourself as described here.

Rules:
- If the user supplied US/AC, keep their wording and number them. Add missing ones only as "Proposed AC" so the user can approve them.
- Cover the unhappy paths too: invalid input, not found, unauthorized, conflicts, limits. Missing negative AC is the most common gap.
- List **Out of scope** items explicitly, so scope doesn't creep.
- Anything ambiguous goes into the Step 8 questions. Don't silently guess.

## Step 2 — Explore the codebase and learn its patterns

The new feature should look like it was written by the same team. Before designing anything, find 1–3 existing features most similar to this one and read them end to end.

Look for these, and report what you find:

| Area | What to find |
|---|---|
| Architecture / layering | e.g. controller → service → repository, hexagonal, CQRS |
| Folder & naming conventions | where files live, suffixes (`*Request`, `*Dto`, `*Handler`) |
| API conventions | URL style (plural nouns, kebab-case, versioning `/api/v1`), pagination, response envelope |
| Validation | annotations, validator classes, schema libs |
| Error handling | exception types, global handler, error response shape, error codes |
| Persistence | ORM, migration tool, transaction handling |
| Auth & security | how endpoints are protected (filters, guards, annotations), how the current user/roles are read, existing rate limiting, audit logging, CORS/CSRF config |
| Testing | framework, unit vs integration split, mocks/fakes, test naming, fixtures/builders |

Present your findings as a table, with **file paths as evidence** (e.g. `src/order/OrderController.java:42`). If no codebase is available, say so, state the stack you are assuming, and add "confirm stack" to Step 8.

## Step 3 — Understand the schema and relationships

Most feature bugs come from misunderstanding the data model, so map it before designing the API. Find the schema from the source of truth the project uses: migration files (Flyway, Liquibase, Alembic, Prisma, knex…), ORM entities/models, `schema.sql`, or DB docs.

### 3a. Existing tables/entities involved
For each table the feature reads or writes:

| Table / Entity | Key columns (type, nullable) | Constraints & indexes | Evidence |
|---|---|---|---|

Include primary keys, foreign keys, unique constraints, enums/status columns, soft-delete flags, audit columns (`created_at`, `version` for optimistic locking), and money/time types.

### 3b. Relationships
List every relationship the feature touches:

| From | To | Cardinality | FK / join | Owning side & cascade/fetch | Business meaning |
|---|---|---|---|---|---|

Then add a Mermaid `erDiagram` of only the involved entities. This is a data map, separate from the single workflow diagram in Step 6. Call out risks you notice: N+1 queries from lazy loading, cascades that could delete too much, missing indexes on FKs or lookup columns, nullable columns that the feature assumes are filled.

### 3c. Proposed schema changes (described, not applied)
- New tables/columns: name, type, nullable, default, constraints, and **why** each is needed.
- New indexes and why (which query they serve).
- Migration plan: file name following the project convention, whether it is backward-compatible, how existing rows are backfilled, and how to roll back.
- If no schema change is needed, say so explicitly.

## Step 4 — Implementation idea: endpoints and DTOs

### 4a. Approach summary
Write 3–6 sentences. Say which components are added or changed, which existing pattern is reused (cite the file from Step 2), how it uses the schema from Step 3, and any key design decision with its reason. List the files that **would** be created or modified, but do not touch them.

### 4b. Endpoint design
Fill in this table for each endpoint:

| Method | URL | Purpose | Success | Errors |
|---|---|---|---|---|

Then briefly explain the design choices:
- Why this HTTP method (idempotency, safe vs unsafe)
- Why this URL shape (resource vs action sub-resource, nesting that reflects the Step 3 relationships)
- Versioning
- How it matches the codebase convention

### 4c. DTOs
For **every** request and response DTO, give the JSON shape and then a field table:

| Field | Type | Required | Validation / Format | Maps to (table.column) | Meaning (why it exists) |
|---|---|---|---|---|---|

The "Meaning" column is the important one. Explain what the field represents for the business and why the client needs it; don't just repeat the field name. The "Maps to" column links the API back to the schema. Write "derived" for computed fields.

Also show the **error response** shape, reusing the codebase's existing one. Never expose internal fields in responses (non-public DB ids, password hashes, internal flags), and mention it when you deliberately leave something out.

## Step 5 — Security review

Every new endpoint is new attack surface, so review it before the tests are designed. Then every risk found here becomes a test in Step 7. Use the OWASP API Security Top 10 as a checklist, and only report items that actually apply to this feature. Saying "not applicable, because…" is fine and useful.

| Check | Questions to answer for this feature |
|---|---|
| Authentication | Which endpoints need a logged-in user? What happens with a missing, expired, or malformed token? |
| Object-level authorization (BOLA/IDOR) | Can user A read or modify user B's resource by changing an id in the URL or body? Is ownership checked in the query, not after loading? Do "not yours" and "doesn't exist" return the same response, so ids can't be enumerated? |
| Function-level authorization | Does the endpoint need a role (admin, staff)? Can a normal user call it? |
| Mass assignment / property-level auth | Can the client send fields it must not control (price, discount, status, ownerId, role)? The request DTO must only contain fields the client is allowed to set. |
| Excessive data exposure | Does the response leak internal ids, other users' data, business rules, or stack traces? |
| Input validation & injection | Are all inputs validated (length, format, allow-list)? Are queries parameterized (no string-built SQL/JPQL)? Is any output rendered as HTML (XSS)? Is any input used in file paths, shell, or URLs (SSRF)? |
| Resource consumption & brute force | Can someone guess codes, ids, or passwords by trying many values? Is there rate limiting, pagination with a max size, and a payload size limit? |
| Business logic abuse | Can the flow be replayed, raced (double-apply, double-spend), or done out of order? |
| Sensitive data & logging | Are secrets or tokens kept out of logs? Is the security-relevant action audit-logged (who, what, when)? |

Output a table:

| # | Risk | Where (endpoint/field) | Mitigation in this plan | Test ref |
|---|---|---|---|---|

Each mitigation should name the concrete mechanism and the existing codebase pattern it reuses, from Step 2. Any risk that needs a product decision goes into Step 8, for example whether error messages may reveal that a coupon exists.

## Step 6 — One workflow diagram

Choose **exactly one** diagram, the one that best explains how the feature runs, and say in one sentence why you chose it:
- **Sequence diagram** (default for API features): shows the request flow across client → controller → service → repository/external systems, with error branches drawn using `alt`.
- **Flowchart**: when the feature is mostly decision logic or validation rules.
- **State diagram**: when the feature changes an entity's lifecycle status.

Write it in Mermaid. Include the main error branches and the security checks from Step 5 (authentication, rate limiting, ownership), not only the happy path.

**Check that every diagram (including any `erDiagram`) renders before you finish.** A diagram with a syntax error shows up as an error box, not a picture. After writing the report file, run `bash <this skill's dir>/scripts/check_mermaid.sh <report file>`. It renders every ```` ```mermaid ```` block with the Mermaid CLI and prints `OK`/`FAIL` with the block's line. Fix each `FAIL` and re-run until all pass. Common causes: unquoted labels with `()`, `:`, `/`, `{}` or `"` (wrap them as `A["label (x)"]`), `end` used as a node name, `alt`/`opt`/`loop` without a matching `end`, and arrows with a missing message (`A->>B: msg`). If the check cannot run (no Node/network), say so in the report instead of claiming the diagram was verified.

## Step 7 — TDD test plan (positive baseline + all negative cases)

Tests are written **first** when implementation starts (Red → Green → Refactor). In plan mode you only *describe* them. List groups in the order they should be written: start with the simplest test that forces the core behavior to exist, then add the rules one by one.

### Test groups: one baseline, every way it can fail

Don't trust a single positive/negative pair. A rule usually breaks in several ways, and one negative test only proves one of them. So organize tests in **groups**, one group per rule:

1. **Baseline positive (✅)**: the valid case. Every test in the group shares this setup.
2. **Edge positives (✅, optional)**: other inputs that must still succeed, such as an exact boundary, input normalization (trimmed or lowercase), or an optional field that is absent.
3. **Negatives (❌), as many as needed to cover all the ways the rule can fail.** Each negative changes **exactly one condition** from the baseline. Because only one thing differs, each test proves that *that* condition causes the failure; changing two things at once hides which one mattered.

To find all the negatives, go through this checklist for each rule. Skip only the items that are truly impossible for that rule:

| Category | Typical negative cases |
|---|---|
| Missing / empty | null, absent field, empty string, whitespace only, empty list |
| Format & size | too long, too short, wrong type, invalid characters, wrong enum value |
| Boundaries | just past min/max, just past a date limit, zero, negative numbers |
| Existence | id/code does not exist, soft-deleted, belongs to another tenant |
| State | every disallowed status, not just one (e.g. PAID **and** CANCELLED **and** SHIPPED) |
| Business rules | each rule separately (expired, inactive, limit reached, minimum not met) |
| Conflicts & concurrency | duplicate (unique constraint), stale version (optimistic lock), double submit |
| Security | from Step 5: no/expired/malformed token, other user's resource, missing role, mass-assignment fields, injection payloads, rate limit exceeded, leaked fields in the response |

### Format for each group

Every test goes in **one table per group**: the baseline, edge positives, and negatives, in that order. Don't write tests as prose lines or bullets; a table keeps them easy to scan and compare.

```
### Group N — [rule being proven]  (covers AC#, Security #)  · [unit | integration | API]
Baseline: Given [the shared valid setup] · When [the action under test]

| # | Type | Test name | Changed condition (vs baseline) | Expected result (Then) | Demonstrates |
|---|---|---|---|---|---|
| ✅1 | baseline | `test_name` | — | [observable result] | [what this proves about the system] |
| ✅2 | edge | `test_name` | [the one condition changed] | [still succeeds, and how] | ... |
| ❌1 | negative | `test_name` | [the one condition changed] | status + error code, and state unchanged | ... |
| ❌2 | negative | `test_name` | ... | ... | ... |
```

- `#` numbers ✅ and ❌ rows separately, so tests can be referenced as `G1✅2` or `G1❌3` in the coverage tables and in scaffold TODOs.
- `Type` is `baseline`, `edge`, or `negative`. Each group has exactly one `baseline` row. A negatives-only group (such as injection payloads) may skip it and say so in the Baseline line.
- The Baseline line holds the shared Given and When. Each row only states what it changes and its expected Then; the scaffold test comments in Step 9 are built from these.
- Keep cells short. If a row needs more explanation, add a one-line note under the table.

Put security tests in their own groups (e.g. "Group S1 — Authentication"). This keeps them visible and makes it easy to check that every Step 5 risk has a test.

Guidelines:
- Every negative's expected result should state the response **and** that nothing changed (no DB write, total unchanged). A rejected request that still writes data is a real bug that "returns 422" alone won't catch.
- Include schema-level rules from Step 3 (unique constraints, FK integrity, optimistic-lock conflicts, cascades). These usually need integration tests against a real or test-container DB.
- State the test level for each group, following the codebase's existing test style from Step 2. Security tests for authentication and authorization should go through the real HTTP/security layer (API tests), because mocks can bypass the filters you are trying to test.
- Test names follow the codebase convention. If there is none, use `should_[expected]_when_[condition]`.
- A "Demonstrates" cell must describe behavior, not code. Good: "an expired coupon never reduces the price". Bad: "tests validateCoupon()".

End with two coverage tables, so gaps are visible:
- **AC → tests**: every AC has a baseline plus at least one negative.
- **Security risk (Step 5) → tests**: every risk has at least one test.

## Step 8 — Questions and confirmations

End with a numbered list of everything the user needs to decide or confirm, split into two groups:
- **Questions**: genuine unknowns, such as business rules, edge cases, data ownership, security trade-offs (e.g. detailed error codes vs. hiding what exists), or what to do with existing data during a migration.
- **Assumptions to confirm**: choices you made so the plan could proceed. Give your default for each, so the user can just say "yes".

Finish the plan file with one line confirming that no files or data were changed other than the plan file. Write the file, reply in chat as described in "Plan file", then stop and wait for answers.

When the user answers, update the plan file in place with their decisions and add them to `## Decision log` (question → answer → what changed in the plan). In chat, show only what changed. Then ask: **"Plan approved — shall I create the scaffold?"** Go to Step 9 only on an explicit yes. Answering the questions is not approval by itself.

## Step 9 — Scaffold only (after approval, no business logic)

The scaffold creates the **shape** of the feature, with no behavior yet. This lets the user review structure, names, and wiring in real code before any logic exists, and it gives TDD a ready place to start: the tests exist and fail, and the next step is making them pass one by one.

### What the scaffold includes
Create exactly the files listed in "Files affected" (Step 4.1), and nothing else:

| Part | Include | Leave out (TODO) |
|---|---|---|
| Migration file | The file with the DDL from Step 3.3, named per convention | **Do not run it.** No DB writes |
| Entities / models | New fields, column mappings, relationships, the `version` field | Domain methods with rules |
| DTOs | All fields, types, and declarative validation (`@NotBlank`, `@Size`, `@Pattern`), with each field's meaning from Step 4.3 as a doc comment | Mapping logic |
| Error codes | New enum entries / constants | — |
| Controller / routes | Endpoint mappings, HTTP method, path, auth principal parameter, `@Valid`, security annotations from Step 5 (e.g. `@RateLimited`), delegation to the service | Any `if`, calculation, or query |
| Service / handler | Public method signatures; constructor-injected dependencies | Method bodies: throw a not-implemented error |
| Repository | Interface method signatures (e.g. `findByPublicIdAndCustomerId`) | Custom query bodies |
| Validator / helpers | Class + method signatures | Rule logic |
| Tests | Every test class and every test method from Step 7, named exactly as planned, in the same group order | Arrange/act/assert code |

### Rules
- **No business logic.** No conditionals, calculations, queries, ownership checks, or mapping. Every method body that would hold logic throws the language's not-implemented error, and has a TODO that points back to the plan:
  `// TODO(AC2, SEC2, G1❌2): reject expired coupon — 422 COUPON_EXPIRED, order unchanged`
  Use the TODO tag so `grep -rn "TODO(AC\|TODO(SEC"` lists all the remaining work.
- **Not-implemented errors**, by language: Java/Kotlin `throw new UnsupportedOperationException("TODO: ...")`, C# `throw new NotImplementedException()`, TypeScript `throw new Error("Not implemented: ...")`, Python `raise NotImplementedError("...")`, Go `panic("not implemented: ...")`.
- **Tests are Red on purpose.** Each test method body contains the planned Given / When / Then and Demonstrates as comments, and then fails explicitly: `fail("TODO: not implemented")`, `assert False`, `expect.fail(...)`, or `t.Fatal(...)`. Don't skip or disable them, because skipped tests look green and hide missing work. Keep the shared baseline setup as a TODO in the group's setup method.
- **Follow the Step 2 patterns exactly**: same folders, naming, annotations, dependency injection style, and error types.
- **It must compile/build.** Run the project's compile or type-check (`mvn -q compile test-compile`, `tsc --noEmit`, `go build ./...`, `dotnet build`, `python -m compileall`). If it doesn't compile, fix the scaffold, not by adding logic. Running the test suite is fine: every new test should fail, and every existing test should still pass.
- **Still not allowed:** running migrations, writing to any database, installing new dependencies (if one is needed, ask first), `git commit`/`push`, or editing files outside the "Files affected" list. If a file not on the list must change for the build to compile, stop and ask.

### Scaffold report
Write it to its own file next to the plan, `<ID>-scaffold-report.md` (e.g. `docs/features/plans/US-5-scaffold-report.md`), starting with `# Scaffold Report: [Feature name]` and a line `Status: … · Plan: [link to plan file] · Date: YYYY-MM-DD`, then `## 9. Scaffold report`. In the plan file, add a short `## 9–10. Scaffold report & verification` section that links to it. Neither file is listed in "Files affected" or counts as an extra file. The report contains:
1. **File tree** of created (🆕) and modified (✏️) files.
2. **Build result** (compile command + pass/fail) and **test result** (expected: N new failing tests, 0 broken existing tests).
3. **TODO map**: a table of each TODO → file:line → AC / SEC / test group it belongs to.
4. **Suggested first test** to make green (the simplest baseline ✅ from Group 1).

Then go straight to Step 10 in the same response.

## Step 10 — Verification checkpoint (STOP before logic)

This is a hard gate. The scaffold is the last moment when changing names, endpoints, DTO fields, or the schema is cheap. Once logic and tests are filled in, every structural change costs rework. So the agent checks its own work first, then hands the user a short checklist and **stops**.

### 10a. Self-verification (agent runs this, read-only)
Compare the scaffold against the approved plan, and report each check as ✅ or ❌:

| # | Check | How |
|---|---|---|
| V1 | Every file in "Files affected" exists, and no extra files were created or modified (the plan file and the scaffold report file are the only allowed extras) | `git status` / `git diff --stat` vs Step 4.1 list |
| V2 | Endpoints match Step 4.2 (method, path, status codes) | read the controller/routes |
| V3 | DTO fields match Step 4.3 (names, types, required, validation) | read the DTOs |
| V4 | Migration DDL matches Step 3.3, and it was **not** executed | read the file; no DB writes happened |
| V5 | Security wiring from Step 5 is present (auth principal, rate limit annotation, etc.) | read the controller/config |
| V6 | Every planned test exists, with the exact name, and the count matches Step 7 | list test methods vs plan; report "planned N / found N" |
| V7 | **No logic leaked**: new method bodies only contain TODOs + not-implemented errors; no conditionals, queries, or calculations | `git diff` review of new method bodies |
| V8 | Build passes; new tests fail; existing tests still pass | the command outputs from Step 9 |

If any check is ❌, fix the scaffold (never by adding logic) and re-run the checks before showing the user.

### 10b. Ask the user to verify
Append the self-verification table and the checklist below to the scaffold report file as `## 10. Verification`, and update the status line in both files. In chat, give the link to the scaffold report, the V1–V8 pass/fail summary, and the checklist. These are things only a human can judge:

```
Please verify before I implement any logic:
☐ File locations and class/method names look right for our codebase
☐ Endpoint URLs, HTTP methods, and status codes are what you want
☐ DTO fields (names, types, required) are final — the API contract is about to be locked in
☐ Migration DDL is correct (column types, nullability, FK rule, index)
☐ The test list is complete — any missing negative or security case?
☐ TODO map covers all the work

Reply "verified" to start implementing logic test-by-test,
or tell me what to change in the scaffold.
```

### 10c. Stop and wait
- End the response here. **Do not write any logic in this response**, even if everything passed.
- If the user asks for changes, apply only scaffold-level changes, re-run 10a, show the updated results, and ask again. Repeat until they reply with an explicit "verified" / "approved" / "go ahead".
- Silence, "looks ok?", or questions are not verification. Answer them, then ask again.
- Only after explicit verification may logic implementation start, one test at a time (Red → Green → Refactor), beginning with the suggested first test.

---

## Output template

The plan file uses these exact headings so it is easy to scan:

```
# Feature Plan: [Feature name]
Status: Draft — awaiting answers · Source: [link to story/ticket] · Date: YYYY-MM-DD
## 1. Requirement (User Stories & Acceptance Criteria)
## 2. Codebase Patterns
## 3. Schema & Relationships
### 3.1 Existing Tables
### 3.2 Relationships (+ ER diagram)
### 3.3 Proposed Schema Changes
## 4. Implementation Idea
### 4.1 Approach & Files Affected
### 4.2 Endpoints
### 4.3 DTOs
## 5. Security Review
## 6. Workflow Diagram
## 7. TDD Test Plan
### Functional groups
### Security groups
### Coverage (AC → tests, Security → tests)
## 8. Questions & Confirmations
## Decision log            (added once the user answers)
## 9–10. Scaffold report & verification   (link to <ID>-scaffold-report.md, added after the scaffold)
```

Step 9 (after approval) uses its own report format, "Scaffold report" above, and is always followed by the Step 10 checkpoint in the same response. Both go into the separate scaffold report file; the plan only links to it.
