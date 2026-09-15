---
name: commit-to-branch
description: >-
  Create a git commit on the current branch in this repository: staging,
  drafting the commit message, safety rules, and attribution. Use whenever the
  user explicitly asks to commit (or "commit this", "commit these changes",
  "make a commit"). Do not use to create commits the user did not ask for, and
  do not use for opening a pull request (that is a separate flow).
---

# Commit to the current branch

## When to commit

Only create a commit when the user explicitly asks for one. If it's unclear
whether they want a commit now, ask first — never commit proactively as a side
effect of another task.

## Git safety protocol

- **Never** update the git config.
- **Never** run destructive git commands (`push --force`, `reset --hard`,
  `checkout .`, `restore .`, `clean -f`, `branch -D`) unless the user
  explicitly requests them.
- **Never** skip hooks (`--no-verify`, `--no-gpg-sign`, etc.) unless the user
  explicitly requests it.
- **Always create a new commit** rather than amending, unless the user
  explicitly asks for `--amend`. If a pre-commit hook fails, the commit did
  **not** happen, so `--amend` would rewrite the *previous* commit instead —
  fix the issue, re-stage, and make a new commit.
- When staging, prefer adding specific files by name rather than `git add -A`
  or `git add .`, which can accidentally sweep in `.env`/credential files or
  large binaries.
- **Never** commit unless the user explicitly asked — even if everything looks
  ready to go.
- Before running anything that could discard uncommitted work, run
  `git status` first.

## Workflow

1. Run in parallel:
   - `git status` (see untracked files — never pass `-uall`, it can be slow/
     memory-heavy on a large repo)
   - `git diff` (staged + unstaged changes that would be committed)
   - `git log` (recent messages, to match this repo's style — see below)
2. Analyze all staged **and** newly-relevant unstaged changes, and draft a
   commit message:
   - Classify the change (new feature, enhancement, fix, refactor, test,
     docs, ...) and word the message accordingly (e.g. "add" = wholly new,
     "update" = enhancement, "fix" = bug fix).
   - Never commit a file that likely contains secrets (`.env`,
     `credentials.json`, ...); warn the user if they specifically ask to
     commit one.
   - Keep the message to 1–2 sentences focused on **why**, not a restatement
     of the diff.
   - **The commit message must be written in English**, regardless of what
     language the conversation is in — see `~/.claude/CLAUDE.md`. This
     applies to every written artifact (code, comments, docs), not only
     commit messages.
3. Run in parallel:
   - Stage the relevant untracked files.
   - Create the commit via a heredoc (so formatting/quoting survive), ending
     with the attribution line currently in effect for this session (check
     the active system reminder — it names the exact line and model, e.g.
     `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`; don't hardcode
     a stale one).
     ```sh
     git commit -m "$(cat <<'EOF'
     <summary line>

     Co-Authored-By: <current session's attribution line>
     EOF
     )"
     ```
   - Then, sequentially (it depends on the commit finishing), run `git status`
     to confirm success.
4. If the commit fails because of a pre-commit hook: fix the underlying issue,
   re-stage, and make a **new** commit — never `--amend` past a failed hook
   run.

## Notes specific to this repo

- Never use `-i`/interactive flags (`rebase -i`, `add -i`) — they need input
  this tool can't supply.
- Never pass `--no-edit` to `git rebase`.
- Don't explore code beyond what's needed to write the message — no extra
  reads, no `Agent`/task-creation tools for a plain commit.
- Don't push after committing unless the user separately asks for that.
