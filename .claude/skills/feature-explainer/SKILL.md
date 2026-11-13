---
name: feature-explainer
description: Help a new developer understand an EXISTING feature in the codebase - its business intent (why it exists), the request workflow step by step with file references and one diagram, every request/response DTO field explained (type, validation, where it comes from, what it means), business rules and the reason behind each, data touched, gotchas, a glossary, and how to try it locally. Read-only, never changes code; writes the explanation to a single Markdown report file (docs/features/explained/<slug>-explained.md). Use this skill whenever someone asks how a feature, endpoint, module, flow, or API works, asks "what does this code do", "walk me through X", "explain the checkout/login/order flow", "what is this DTO/field for", is onboarding to a codebase, or pastes an endpoint, controller, or class and wants to understand it, even if they don't say "explain".
---

# Feature Explainer (onboarding)

Help a developer who is new to the codebase understand an existing feature well enough to change it safely. A good explanation answers four questions:
1. **Why does this exist?** (intent)
2. **What happens when it runs?** (workflow)
3. **What goes in and comes out?** (DTOs)
4. **What will surprise me?** (rules and gotchas)

This skill explains code that already exists. For designing *new* features, use `feature-implementation-planner`; for writing tickets, use `jira-story-writer`.

See `references/example-output.md` for a complete worked example.

---

## 📄 Report file: the explanation goes into one `.md` file

Write the full explanation to **one Markdown file**, so the newcomer can keep it, re-read it, and share or commit it as onboarding docs. The chat reply gets only a short pointer.

**Where:**
- If the project keeps feature docs (e.g. `docs/features/`), put it in an `explained/` subfolder: `docs/features/explained/<slug>-explained.md`, e.g. `docs/features/explained/chat-session-explained.md`.
- Otherwise use `docs/explained/<slug>-explained.md`.
- If a report for this feature already exists, update it in place instead of creating a second one, and update its `Date:` line.

**File header** (right under the title):
`Date: YYYY-MM-DD · Commit: <short git sha> · Scope: <what was explained>` — so readers know which version of the code it describes and when it may be stale.

**Links:** file references in the report are relative Markdown links from the report's location (e.g. `[ChatServiceBase.cs:47](../../../src/Services/ChatServiceBase.cs#L47)`), so they work in the IDE and on GitHub.

**Chat reply:** a clickable link to the report, a 3–5 line summary (what the feature is, the key design idea, the top 1–2 gotchas), and the offer of deeper dives. Don't paste the whole report into the chat.

**Exception:** a quick question about a single DTO or method (see the end of this file) is answered directly in chat, with no file, unless the user asks for one.

---

## ⛔ Read-only

Only read: browse files, search, and run read-only git commands (`git log`, `git blame`, `git show`). **The one write exception is the report `.md` file itself** (and its `explained/` folder). Never edit any other file, run migrations, write to databases, or call endpoints that change data. Commands that only read (running the existing tests, a `GET` against a local server) are fine if the user asks. The reason: someone who is still learning a codebase should never have it changed underneath them by an explanation.

## Core principles

- **Evidence over guessing.** Back every claim about behavior with a file reference (`OrderService.java:47`). If you didn't read it, don't state it.
- **Separate fact from interpretation.** Behavior comes from the code. *Intent* (why) often has to be inferred, so label it:
  - ✅ **Confirmed**: stated in docs, ADRs, comments, a ticket, a commit message, or a test name.
  - 💭 **Inferred**: your best reading of the code. Say what it's based on.
  - ❓ **Unknown**: you can't tell. Put it in "Open questions for the team".
- **Find the intent where it lives.** Look in test names and descriptions (often the clearest spec), commit messages (`git log --follow <file>`, `git log -S "<identifier>"`), `git blame` on surprising lines, README/docs/ADRs, ticket keys in commits, comments, and validation messages.
- **Write for a newcomer.** Use plain language, define every domain term the first time it appears (and add it to the glossary), and prefer "what it does for the user" over class names. A short analogy is welcome when a concept is abstract.
- **Follow the real path, not the folder structure.** Explain in the order a request actually travels.

## Step 0 — Scope it

Identify what to explain: an endpoint, a feature ("checkout"), a class, or a whole module. If it's broad (e.g. "explain the whole app"), start with a **map**: the main modules, one line each, plus their entry points. Then ask which one to go deep on.

Default depth is an **overview plus one main flow in detail**. Offer deeper dives at the end, rather than explaining everything at once.

If no codebase is available (the user pasted a snippet), explain what's visible, and list what you'd need to see to complete the picture.

## Step 1 — Feature at a glance

In 3–5 sentences: what the feature does, **who** uses it (customer, admin, another service, a cron job), and **why it exists** (the business intent, labeled ✅/💭/❓). Then a quick fact box:

| | |
|---|---|
| Entry points | the endpoints, jobs, event consumers, or UI actions that start it |
| Main code | the key files/classes (3–6, not everything) |
| Data | the main tables/entities it reads and writes |
| External systems | payment providers, email, queues, caches, other services |
| Tests to read first | the 1–2 test files that best describe its behavior |

## Step 2 — Entry points

| Method | URL / trigger | Auth / role | Purpose | Main handler |
|---|---|---|---|---|

Include non-HTTP triggers too: scheduled jobs, message/event consumers, webhooks, and CLI commands.

## Step 3 — Workflow

### 3a. Step-by-step walkthrough
Follow one realistic request from start to finish. Number each step, and give the file:line and what happens **in plain words**:

```
1. Request hits OrderController.applyCoupon (OrderController.java:41)
   → Spring checks the JWT and rate limit before this method runs (JwtFilter, @RateLimited)
2. Service loads the order *only if it belongs to the caller* (OrderService.java:47)
   → Why: so users can't touch other people's orders by changing the id (💭 inferred from the S2 tests)
...
```

For each step, call out **side effects** (DB writes, events published, emails, cache updates, external calls), the **transaction boundaries**, and **where it can fail** (what error, which status code).

### 3b. One diagram
Pick the single diagram that best explains the flow, and say why in one sentence:
- a **sequence diagram** for request flows across layers/services (the default),
- a **flowchart** for decision-heavy logic,
- a **state diagram** for entity lifecycles (e.g. order statuses).

Write it in Mermaid. Include the error branches.

**Check that every diagram (including any `erDiagram`) renders before you finish.** A diagram with a syntax error shows up as an error box, not a picture. After writing the report file, run `bash <this skill's dir>/scripts/check_mermaid.sh <report file>`. It renders every ```` ```mermaid ```` block with the Mermaid CLI and prints `OK`/`FAIL` with the block's line. Fix each `FAIL` and re-run until all pass. Common causes: unquoted labels with `()`, `:`, `/`, `{}` or `"` (wrap them as `A["label (x)"]`), `end` used as a node name, `alt`/`opt`/`loop` without a matching `end`, and arrows with a missing message (`A->>B: msg`). If the check cannot run (no Node/network), say so in the report instead of claiming the diagram was verified.

## Step 4 — DTOs: request and response

For every request and response DTO in the flow, give a **realistic example JSON** (realistic values, not "string"), then a field table:

| Field | Type | Required | Validation | Comes from / maps to | Meaning (why it exists) |
|---|---|---|---|---|---|

- **Comes from / maps to**: for requests, where the value goes (e.g. "used to look up `coupons.code`"). For responses, where it comes from (a column, "derived: subtotal − discount", or another service).
- **Meaning** is the most important column. Explain what the field represents for the business and why a client needs it, not a restatement of its name.
- Explain **derived fields** with the formula and a worked example ("10% of 120.00 = 12.00").
- Point out fields that are **deliberately missing** (e.g. no internal ids, no price in the request), and why. Newcomers often try to "add the missing field", so explain the reason it's absent.
- Show the **error response** shape, with a table of error codes this flow can return: code, HTTP status, when it happens.
- Note **mapping code** (mappers, assemblers) and any naming differences between the DTO and the entity.

## Step 5 — Business rules and why they exist

| Rule | Where enforced | Why (✅/💭/❓) | Proven by test |
|---|---|---|---|

Order the rules as the code checks them, and mention when that order matters (e.g. "ownership is checked first, so users never learn anything about other people's orders").

## Step 6 — Data touched

A short list of the tables/entities read and written, with the columns that matter for this flow and the relationships between them. Add an `erDiagram` only if the relationships are non-obvious. Mention anything frozen or denormalized on purpose (e.g. "the discount is stored, not recalculated, so old orders keep their price").

## Step 7 — Gotchas

These are the things most likely to trip up a newcomer. Look especially for:
- non-obvious ordering, rounding, timezones, or units,
- values computed in one place and stored in another,
- "magic" behavior from frameworks (filters, interceptors, annotations, AOP, event listeners, DB triggers, cascades),
- duplicate logic that must be changed in two places,
- feature flags or config that change the behavior,
- tests that run differently from production (mocks, in-memory DB),
- known limitations or TODOs/FIXMEs in the code.

Format each gotcha as **What surprises people → why it's like that → what to do when changing it.**

## Step 8 — Try it yourself

Help the newcomer learn by doing:
- How to run the relevant tests (the exact command), and which test to read first.
- A sample request (`curl` or HTTP file) with realistic data, and the expected response. Use placeholders for tokens and ids; never real credentials.
- A suggested breakpoint path for debugging (2–4 places to put breakpoints).

## Step 9 — Glossary, check-your-understanding, next steps

- **Glossary**: every domain term used, defined in one line.
- **Check your understanding**: 3–5 short questions with answers hidden (use `<details>` blocks), aimed at the gotchas and rules, e.g. "What happens to an order's total if the coupon is edited after it was applied?"
- **Open questions for the team**: the ❓ items, phrased so the newcomer can ask a teammate.
- **Where to go next**: related features and the next thing worth learning.

End by offering deeper dives: "Want me to go deeper into any step, explain another flow, or quiz you on this one?"

---

## Output template

The report file uses these headings:

```
# How [Feature] Works
Date: YYYY-MM-DD · Commit: <sha> · Scope: <what was explained>
## 1. At a Glance
## 2. Entry Points
## 3. Workflow
### 3.1 Step by Step
### 3.2 Diagram
## 4. DTOs (Request & Response)
## 5. Business Rules & Why
## 6. Data Touched
## 7. Gotchas
## 8. Try It Yourself
## 9. Glossary · Check Your Understanding · Next Steps
```

For a quick question about a single DTO or a single method, skip the full template: answer directly with the relevant section (e.g. only the DTO field table), and offer the full walkthrough.

Write in the same language the user writes in. Keep code identifiers, file names, and field names unchanged.
