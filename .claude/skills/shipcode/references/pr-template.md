# PR body template

Use these headings exactly. Fill every part from the real diff; delete Key Changes bullets that don't apply.

```markdown
## 1. Ticket
- [<JIRA-ID>](<Jira link>) — <User Story id and title, e.g. US-6 Clear feedback on failure>

## 2. Summary of Changes
- **Objective:** <1–2 sentences: what problem this PR solves>
- **Key Changes:**
  - Added endpoint / command handler: <names, routes>
  - Database schema / migration update: <migration name, tables/columns/indexes; "announced in team chat">
  - Refactored service / logic: <what and why>

## 3. Technical Checklist
- [ ] Added or updated Unit / Integration tests (all tests pass locally).
- [ ] Verified database queries against EF Core **N+1 issues** and missing indexes.

## 4. Proof
<test runner summary in a code block>
<!-- add screenshots: Swagger / Postman / UI / test runner -->
```

## Filled example

~~~markdown
## 1. Ticket
- [PROJ-123](https://company.atlassian.net/browse/PROJ-123) — US-2 Refresh expired sessions

## 2. Summary of Changes
- **Objective:** Users were logged out every 15 minutes because access tokens couldn't be renewed. This adds a refresh-token flow so sessions last until the refresh token expires.
- **Key Changes:**
  - Added endpoint / command handler: `POST /api/v1/auth/refresh` → `RefreshTokenCommandHandler`
  - Database schema / migration update: `20261104_AddRefreshTokens` — new `RefreshTokens` table (FK `UserId`, unique index on `TokenHash`); announced in team chat
  - Refactored service / logic: token creation moved from `AuthController` into `ITokenService`

## 3. Technical Checklist
- [x] Added or updated Unit / Integration tests (all tests pass locally).
- [x] Verified database queries against EF Core **N+1 issues** and missing indexes.

## 4. Proof
```
Passed!  - Failed: 0, Passed: 112, Skipped: 0, Total: 112
```
<!-- add screenshots: Swagger / Postman / UI / test runner -->
~~~
