# Issue tracker: GitHub

Issues and specs for this repository live in GitHub Issues. Use the `gh` CLI for issue operations.

## Conventions

- Create: `gh issue create --title "..." --body "..."`.
- Read: `gh issue view <number>`.
- List: `gh issue list` with appropriate state and label filters.
- Comment: `gh issue comment <number> --body "..."`.
- Label: `gh issue edit <number> --add-label "..."` or `--remove-label "..."`.
- Close: explain the resolution in a comment, then run `gh issue close <number>`.

Infer the repository from `git remote -v`. Before creating an issue, confirm `gh repo view --json nameWithOwner` points to this user's repository.

## Pull requests as a request surface

**No.** Pull requests are not included in issue triage by default.
