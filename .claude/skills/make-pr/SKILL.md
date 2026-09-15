---
name: make-pr
description: >-
  Push the current branch and open a GitHub pull request for this repository:
  gathering the branch's full history, drafting title/summary/test plan, and
  attribution. Use whenever the user explicitly asks to open/create/make a PR
  or push a pull request. Do not use for a plain commit (see
  commit-to-branch), and do not push or open the PR unless the user asked for
  it.
---

# Open a pull request

## When to run this

Only push and open a PR when the user explicitly asks. Pushing code and
opening a PR are both visible to others / affect shared state — never do
either as a side effect of another task, and never push with `--force` to
`main`/`master` without calling it out to the user first.

## Tooling

Use the `gh` CLI via Bash for all GitHub-related work (issues, PRs, checks,
releases). If given a GitHub URL, use `gh` to pull the needed info from it
rather than guessing.

## Workflow

1. Run in parallel to understand everything that will go into the PR:
   - `git status` (untracked files — never `-uall`)
   - `git diff` (staged + unstaged changes)
   - check whether the current branch tracks a remote branch and is up to
     date with it (so you know whether a push is needed)
   - `git log` and `git diff [base-branch]...HEAD` to see the **full** commit
     history since the branch diverged from the base branch (`main` here)
2. Analyze **every** commit that will be included — not just the latest one —
   and draft:
   - a PR **title** under 70 characters
   - a **body** with the details/rationale (not the title) — keep it to the
     structure below
   - **Everything written must be in English**, regardless of the
     conversation's language: title, body, and any inline comments — see
     `~/.claude/CLAUDE.md`.
3. Run in parallel:
   - create the branch remotely if needed
   - `git push -u` if the branch isn't already pushed / is behind
   - `gh pr create` with the title and a heredoc body:
     ```sh
     gh pr create --title "the pr title" --body "$(cat <<'EOF'
     ## Summary
     <1-3 bullet points>

     ## Test plan
     - [ ] <bulleted checklist of TODOs for testing the PR>

     🤖 Generated with [Claude Code](https://claude.com/claude-code)
     EOF
     )"
     ```
4. Return the PR URL to the user.

## Notes specific to this repo

- Do not use `Agent`/task-creation tools for this — just the `git`/`gh` Bash
  commands and read-only exploration needed to understand what shipped.
- Do not push to the remote unless the user has explicitly asked for a push/
  PR in this turn.
- Never skip hooks (`--no-verify`) or bypass signing (`--no-gpg-sign`) unless
  explicitly requested.
- Never force-push to `main`/`master`; warn the user if they ask for it.
