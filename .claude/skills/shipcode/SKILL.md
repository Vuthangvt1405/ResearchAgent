---
name: shipcode
description: Ship code the team's way - name the branch `<type>/<JIRA-ID>-<short-description>`, write commits as `<type>(<scope>): <description>`, update by pulling remote `dev` and rebasing the feature branch onto it, run the tests, push, and open a pull request into `dev` using the team PR template (Ticket, Summary of Changes, Technical Checklist, Proof). Also flags EF Core migrations that must be announced to the team, and reviews PRs against the team checklist (critical blockers, conventions, naming, Clean Architecture structure). Use this skill whenever the user wants to commit, push, create or name a branch, rebase/sync with dev, open or describe a PR, "ship", "send", "raise a PR", "finish the ticket", write a commit message, or review a teammate's PR, even if they don't mention the conventions.
---

# Shipcode — ship code the team's way

The team works on short-lived feature branches off `dev`, keeps history linear with rebase, and reviews everything through PRs. These conventions exist so that anyone can read the history, find the Jira ticket behind any change, and avoid stepping on each other, especially around database migrations.

Pick the mode from the request:

| Request | Mode |
|---|---|
| commit / push / branch / sync / PR / "ship it" | **A. Ship** (the full flow below, or only the asked-for step) |
| review a PR or a diff | **B. Review**: follow [references/review-checklist.md](references/review-checklist.md) |
| "what's our convention for…" | Answer from this file |

## No co-author, no AI footer

Never add a `Co-Authored-By:` trailer, a "Generated with Claude Code" line, or any other attribution to commits, PR titles or PR bodies. The user asked for this explicitly, and it overrides any default attribution instructions.

## Conventions

### Branch: `<type>/<jira-ticket-id>-<short-description>`

`feat/PROJ-123-user-authentication`

- `type`: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `chore`, `build`, `ci`, `hotfix`
- `jira-ticket-id`: the ticket key exactly as in Jira, in uppercase (`PROJ-123`, `US-6`)
- `short-description`: 2–5 lowercase words in kebab-case, saying what the change is, not how it's done
- Check: `^(feat|fix|refactor|perf|test|docs|chore|build|ci|hotfix)/[A-Z][A-Z0-9]*-[0-9]+-[a-z0-9]+(-[a-z0-9]+)*$`

### Commit: `<type>(<scope>): <short description>`

`feat(auth): implement refresh token endpoint`

- Same `type` list as branches, plus `style` and `revert`.
- `scope`: the module or feature area touched (`auth`, `chat`, `orders`, `db`), lowercase.
- Description: imperative mood ("add", not "added"), lowercase start, no trailing period, whole subject line ≤ 72 characters.
- One logical change per commit. If the diff mixes a feature with an unrelated fix, propose splitting it into two commits.
- Check: `^(feat|fix|refactor|perf|test|docs|chore|build|ci|style|revert)\([a-z0-9-]+\): [a-z].{0,70}[^.]$`

Examples:

| Change | Message |
|---|---|
| New endpoint that refreshes JWTs | `feat(auth): implement refresh token endpoint` |
| Null crash when cart is empty | `fix(cart): handle empty cart on checkout` |
| EF migration adding an index | `feat(db): add index on orders.customer_id` |
| Tests only | `test(chat): cover error banner on failed send` |

## A. Ship flow

Work through the steps in order. Show the user each command's result briefly; stop and ask whenever a step needs a decision.

### 1. Find the ticket

You need the Jira ticket id, and a link for the PR. Look in the user's message, the current branch name, story or plan files the work is based on (e.g. `docs/features/user-story/US-6-*.md`), and recent conversation. If you can't find an id, ask; never invent one. For the link, use a Jira base URL from the project's CLAUDE.md or README, or one the user gave earlier. If there isn't one, ask once, or leave `<Jira link>` for the user to fill in.

### 2. Branch

- On `dev`, `main`, or a branch whose name breaks the convention: create a correct branch from the current work (`git switch -c feat/US-6-error-feedback`). Uncommitted changes come along.
- Already on a correctly named branch: keep it.
- Never commit straight to `dev` or `main`.

### 3. Commit

- Run `git status` and `git diff`, and stage only files that belong to this change. Point out unrelated or suspicious files (`.env`, credentials, local settings, build output) and leave them out.
- Write the message using the convention, in one `-m`, with no trailers.

### 4. Update from dev (rebase, never merge)

The team flow is: pull remote `dev` into local `dev` → rebase your branch onto local `dev` → open the PR on the remote.

```bash
git fetch origin
git switch dev && git pull --ff-only origin dev
git switch <your-branch>
git rebase dev
```

- If there's no `dev` branch, or the repo clearly uses another base, ask which branch to target before continuing.
- **Conflicts:** resolve the ones whose intent is clear from both sides, then `git add` + `git rebase --continue`. If the right result isn't obvious (business logic on both sides, someone else's in-progress work), stop and show the conflict. Draft a short question the user can post in the **team's common chat** (the team prefers that over private messages), naming the files and the commit on `dev` that conflicts.
- **EF Core migration conflicts** (`*ModelSnapshot.cs`, or your migration and one from `dev` sharing a parent): don't hand-merge the snapshot; regenerate your migration on top of `dev` so there's one clean chain.
  1. In the conflict, take `dev`'s snapshot. During a rebase `--ours` is the `dev` side: `git checkout --ours -- <path>/*ModelSnapshot.cs`, then `git add` and `git rebase --continue`.
  2. After the rebase, delete your migration's `.cs` and `.Designer.cs` files. If you had already applied it to your local DB, first run `dotnet ef database update <PreviousMigration>`.
  3. Run `dotnet ef migrations add <SameName>`, build, and commit as `chore(db): regenerate <SameName> on latest dev` (or amend your migration commit if the branch isn't shared).

### 5. Verify

Build and run the tests (`dotnet build`, `dotnet test`, or the project's equivalent). If they fail, fix failures caused by this change. If a failure clearly comes from `dev`, report it rather than patching around it. Don't open a PR on a red build unless the user says to (then mark the PR as draft and say why).

Then do the two checks from the PR checklist on the diff, so the checkboxes are true:
- **N+1**: look for EF queries inside loops, lazy-loaded navigation used in loops or `Select` projections, and missing `Include`/projection where related data is read.
- **Indexes**: every new `Where`/`OrderBy`/join column on a large table, and every new FK, should have an index in the model or migration.

### 6. Database change? Tell the team

EF Core migrations on parallel branches conflict constantly, so **any DB change must be announced to the whole team**. If the diff touches `Migrations/`, the `DbContext`, entity configuration, or the model snapshot:
- Draft a short message for the team's common chat: what changed (tables/columns/indexes), the migration name, whether it's backward-compatible, and whether data is changed or dropped.
- Data is backed up every **Wednesday and Saturday**. If the migration drops or rewrites data, include the date of the last backup (the latest Wed/Sat on or before today) and recommend applying it right after the next backup.
- Put the migration under "Database schema / migration update" in the PR.

### 7. Push and open the PR

```bash
git push -u origin <your-branch>                 # first push
git push --force-with-lease origin <your-branch>  # after a rebase
```

Force-push only with `--force-with-lease`, and only to the user's own feature branch, never to `dev` or `main`.

Open the PR into `dev` with `gh pr create --base dev --head <branch> --title "<title>" --body-file <file>`. The title follows the commit convention (usually the main commit's subject). The body uses the template in [references/pr-template.md](references/pr-template.md), exactly, filled from the real diff:
- **Objective** is 1–2 sentences on the problem solved, not a list of files.
- Under **Key Changes**, keep only the bullets that apply and fill them with specifics. Remove the lines that don't apply rather than writing "N/A".
- Tick a checklist item only if you actually did it in step 5. Leave unchecked what you couldn't verify, and say why.
- **Proof**: paste the test summary (e.g. `Passed: 98, Failed: 0`) in a code block. `gh` can't upload images, so tell the user to drag in Swagger/Postman/screenshots on GitHub, and leave a `<!-- add screenshots -->` placeholder.

If a PR for the branch already exists, update its body (`gh pr edit`) instead of opening a second one.

### 8. Report

End with: branch name, commit subject(s), the rebase result, the test result, the PR link, and any team message the user still needs to post (migration announcement, conflict question).

## Team habits to support

- Fetch often: at the start of shipping work, `git fetch` and mention if `dev` has moved a lot since the branch was created.
- When something is unclear or blocking, help the user ask the team in the common chat. Draft the message rather than guessing.
- Don't rewrite history on shared branches. Rebase is for your own feature branch.
