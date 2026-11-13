# PR review checklist

Review in this priority order and label each finding with its level, so the author fixes blockers first. Cite `file:line` for every finding and suggest the fix.

Get the PR with `gh pr view <n>` and `gh pr diff <n>` (or `git diff dev...<branch>`). Write the review as a draft for the user. Post it (`gh pr review <n> --comment --body-file …`) only when the user asks, and never approve or request changes on their behalf without being told to.

## 1. Critical — can block everyone

These break `dev` for the whole team, so they come first:

- Build or tests fail; the PR targets the wrong base (not `dev`).
- **Migrations**: a new migration not rebased onto the latest `dev` (snapshot conflict / two migrations with the same parent); a DB change not announced to the team; a migration that drops or rewrites data without a plan (the last backup was the latest Wed/Sat).
- Breaking API contract changes (renamed/removed fields, changed status codes) without the ticket asking for it.
- Secrets, connection strings, or personal data committed; stack traces or internal errors returned to clients.
- Shared config changes (`appsettings.json`, `Program.cs` pipeline order, CI files) that affect everyone.
- Data loss or security holes: missing authorization/ownership checks, SQL built from strings.

## 2. Code convention

- Branch `<type>/<JIRA-ID>-<short-description>`, commits `<type>(<scope>): <description>`, PR body follows the template with an honest checklist.
- No merge commits from `dev` (the team rebases).
- Follows the common structure below.

## 3. Naming

- Variables, methods, classes say what they mean in the business domain (`GetActiveOrdersAsync`, not `GetData2`).
- C# conventions: PascalCase types/methods/properties, camelCase locals/parameters, `_camelCase` private fields, `Async` suffix on async methods, `I` prefix on interfaces.
- DTO suffixes are consistent (`*Request`, `*Response`, `*Dto`), as are validators (`*Validator`) and handlers (`*Handler`).
- No unclear abbreviations, and booleans read as yes/no (`isActive`, `hasItems`).

## Common code structure (what "good" looks like)

| Area | Expect |
|---|---|
| **Clean Architecture** | Domain (entities, rules) has no dependencies; Application (use cases, DTOs, validators, interfaces); Infrastructure (EF Core, external services); API (controllers/endpoints, middleware). Dependencies point inward; controllers stay thin. |
| **Middleware** | Cross-cutting concerns (logging, correlation id, auth, exception handling) live in middleware, not repeated in controllers. Pipeline order is correct. |
| **Global Exception Handling** | One global handler maps exceptions to the standard error response; controllers don't use try/catch just to shape errors; no stack traces leak to clients. |
| **API Response** | Every endpoint returns the team's standard response/envelope and error shape, with correct HTTP status codes. |
| **Pagination** | List endpoints are paged (page/pageSize, or a cursor) with a max page size, a stable `OrderBy`, and the total count where the UI needs it. No unbounded `ToListAsync()` on tables that grow. |
| **DTO** | Entities never cross the API boundary. Request DTOs hold only fields the client may set (no mass assignment of `Id`, `Role`, prices). |
| **Mapper** | Mapping is done the project's agreed way (one library or manual mappers), in one place, not inline in controllers. |
| **FluentValidation** | Each request DTO has a validator; rules match the DB constraints (lengths, required fields); no validation duplicated in controllers. |
| **DbContext** | Scoped lifetime; accessed through the Infrastructure layer; `AsNoTracking` for reads; projections instead of loading whole graphs; no N+1 (queries in loops, lazy loading in projections); indexes for new filter/join columns; async all the way with `CancellationToken`. |
| **Unit Test** | New logic has unit tests, positive and negative cases; names describe behavior; integration tests for queries and migrations where it matters; all tests pass. |

## Review output format

```markdown
**Verdict:** Blocking issues / Changes suggested / Looks good

### Critical
- `path/File.cs:42` — <problem>. Fix: <suggestion>.

### Convention
- …

### Naming
- …

### Nice to have
- …
```

Leave out empty sections. If nothing is wrong, say so in one line. Don't invent findings to fill the template.
