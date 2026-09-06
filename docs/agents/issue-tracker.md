# Issue Tracker: GitHub Issues

Issues for IRIS are tracked in GitHub Issues at [noodisD/Iris-01](https://github.com/noodisD/Iris-01).

## How skills interact with it

- **`to-issues`** — Converts problems/findings into GitHub issues
- **`triage`** — Applies triage labels and moves issues through workflow
- **`to-prd`** — Reads issues to generate PRD documents
- **`qa`** — References issues during testing and validation

## Creating an issue

Use the `gh` CLI:

```bash
gh issue create --title "..." --body "..." --label "needs-triage"
```

Or use the GitHub web UI at https://github.com/noodisD/Iris-01/issues/new.

## Workflow

Issues flow through triage labels (see `docs/agents/triage-labels.md`):

1. New issue → `needs-triage`
2. Maintainer evaluates → `needs-info` or `ready-for-agent` or `wontfix`
3. Issue becomes `ready-for-human` when it requires human implementation
4. Issue is closed when resolved

Skills read and update labels automatically during their workflows.
