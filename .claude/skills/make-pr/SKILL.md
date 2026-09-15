---
name: make-pr
description: >-
  Push the current branch and open a GitHub pull request for this repository
  — or, if the branch already has an open PR, push to it and update its
  title/description: gathering the branch's full history, drafting
  title/summary/test plan, and attribution. Use whenever the user explicitly
  asks to open/create/make/update a PR or push a pull request. Do not use for
  a plain commit (see
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

**Known `gh` failure:** `gh pr edit` (and sometimes `gh pr view` with default
fields) can fail with `GraphQL: Projects (classic) is being deprecated ...
(repository.pullRequest.projectCards)`. The edit is **not** applied. Use the
REST API instead, with the body written to a file in the scratchpad so
quoting survives:

```sh
gh api -X PATCH repos/<owner>/<repo>/pulls/<n> \
  -f title="<title>" -F body=@<scratchpad>/pr-body.md \
  --jq '"\(.title)\n\(.html_url)\n\(.body | length)"'
```

Read a PR the same way: `gh api repos/<owner>/<repo>/pulls/<n>`, or
`gh pr view <n> --json <fields>` with an explicit field list that avoids
`projectCards`.

## Workflow

1. `git fetch origin` first, so comparisons against `origin/main` and the
   remote branch aren't stale. Then run in parallel to understand everything
   that will go into the PR:
   - `git status` (untracked files — never `-uall`)
   - `git diff` (staged + unstaged changes)
   - check whether the current branch tracks a remote branch and is up to
     date with it (so you know whether a push is needed)
   - `git log` and `git diff [base-branch]...HEAD` to see the **full** commit
     history since the branch diverged from the base branch (`main` here)
   - `gh pr list --head <branch> --state all` — whether a PR from this branch
     already exists (see "If a PR already exists" below)
   - whether the branch still merges cleanly with the base:
     `git merge-tree --write-tree --name-only HEAD origin/main`
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

## If a PR already exists

`gh pr create` fails when the branch already has an open PR. Instead:

1. Note the remote branch's tip **before** pushing (e.g. from
   `git rev-parse origin/<branch>` or the push output's `old..new`). After
   the push `origin/<branch>` equals `HEAD`, so `origin/<branch>..HEAD` comes
   back empty — diff and log against that saved old tip to see what the push
   added.
2. `git push` — this alone updates the PR's commits.
3. Read the current title and body (`gh api repos/<owner>/<repo>/pulls/<n>`)
   and check whether they still describe everything in the branch. If the
   new commits add scope, update them: **keep the existing content** (it may
   hold test results or context from earlier work), add sections for the new
   commits, and adjust the title and Summary to cover the whole branch.
4. Don't claim test results you didn't produce in this session — add new
   checks as unchecked `- [ ]` items.
5. Return the PR URL.

A closed/merged PR from the same branch doesn't block a new one — create a
new PR as usual.

## Notes specific to this repo

- Do not use `Agent`/task-creation tools for this — just the `git`/`gh` Bash
  commands and read-only exploration needed to understand what shipped.
- Do not push to the remote unless the user has explicitly asked for a push/
  PR in this turn.
- Never skip hooks (`--no-verify`) or bypass signing (`--no-gpg-sign`) unless
  explicitly requested.
- Never force-push to `main`/`master`; warn the user if they ask for it.
