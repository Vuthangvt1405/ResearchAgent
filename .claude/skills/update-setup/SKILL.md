---
name: update-setup
description: Sync this project's Claude setup (CLAUDE.md, .claude/settings.json, .claude/skills/) with GitHub using one explicit mode - push, pull or status. Run only when the user invokes /update-setup with a mode or clearly asks to push, pull or check the project setup.
argument-hint: push | pull | status
disable-model-invocation: true
---

# Update Setup - Project Claude Config Sync

Keeps the Claude setup that lives **inside this project repository** version-controlled and in sync with its GitHub remote. It never touches the global `~/.claude` directory.

## Scope

Work in the repository root: `ROOT=$(git rev-parse --show-toplevel)`.

Setup files (the only paths this skill may stage):
- `CLAUDE.md`
- `.claude/settings.json`
- `.claude/skills/**`

Never stage: `.claude/settings.local.json`, `.claude/launch.json`, `.env*`, credentials, tokens, or anything outside the list above. If a setup file contains a secret (API key, token), stop and tell the user.

## Choosing the mode

The mode comes from the argument (`$ARGUMENTS`):

| Argument | Mode |
|---|---|
| `push` | **A. Push** - commit setup changes and push them |
| `pull` | **B. Pull** - bring in setup changes from the remote |
| `status` (or empty) | **C. Status** - report only, change nothing |

If the argument is empty or not one of these, run **Status** and finish by telling the user to run `/update-setup push` or `/update-setup pull`. Never pick push or pull on your own.

## A. Push

1. **Check for changes**: `git -C "$ROOT" status --short -- CLAUDE.md .claude/settings.json .claude/skills`. If nothing changed, report "setup already up to date" and stop.
2. **Validate skills**: every changed `.claude/skills/<name>/SKILL.md` must start with YAML frontmatter containing `name` (kebab-case, equal to the folder name) and `description`. Fix or report problems before going on.
3. **Pick the branch**: if the current branch is `main` or `dev`, create `chore/update-setup` (add `-<yyyymmdd>` if it already exists) and switch to it; protected branches are only updated through a PR. Otherwise stay on the current branch.
4. **Stage only setup files**: `git -C "$ROOT" add -- CLAUDE.md .claude/settings.json .claude/skills`. Run `git diff --cached --stat` and confirm nothing else is staged.
5. **Commit** with Conventional Commits, one commit per kind of change:
   - New skill: `feat(skills): add <skill-name> skill`
   - Updated skill: `feat(skills): update <skill-name> skill (<short summary>)`
   - Settings: `chore(config): update settings.json (<setting>)`
   - Rules: `docs(config): update CLAUDE.md (<short summary>)`
6. **Sync then push**: `git pull --rebase origin <branch>` (skip if the branch is not on the remote yet), then `git push -u origin <branch>`.
7. **Report**: branch, commit hashes and messages, files pushed. If the branch is not `main`/`dev`, offer to open a PR (use the `shipcode` skill conventions).

## B. Pull

1. If setup files have uncommitted changes, stop and list them; ask the user to push or discard them first. Never stash or overwrite them silently.
2. `git -C "$ROOT" fetch origin`.
3. Show what is coming: `git log --oneline HEAD..origin/<branch> -- CLAUDE.md .claude`. If nothing, report "already up to date" and stop.
4. `git -C "$ROOT" pull --ff-only origin <branch>`. If fast-forward fails, stop and explain the divergence; do not merge or rebase without the user's go-ahead.
5. **Report**: commits pulled and which setup files changed. Remind the user that changes to `settings.json` and `CLAUDE.md` apply from the next session.

## C. Status

Report, without changing anything:
- Current branch and whether it is ahead/behind `origin` (after `git fetch`).
- Modified or untracked setup files.
- Installed skills in `.claude/skills/` and whether each has valid frontmatter.
- The next command to run (`/update-setup push` or `/update-setup pull`), if any.
