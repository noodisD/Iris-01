# Domain Docs Layout

IRIS uses a **single-context** layout. All domain documentation and architectural decisions are at the repo root.

## Structure

```
/
├── CONTEXT.md           ← Domain language glossary (terms, invariants, key concepts)
├── docs/adr/            ← Architectural Decision Records
│   ├── ADR-0001-*.md
│   ├── ADR-0002-*.md
│   └── ...
└── docs/agents/         ← Agent skills configuration (this file, issue-tracker.md, triage-labels.md)
```

## How skills consume this

### `improve-codebase-architecture`

Reads `CONTEXT.md` to learn the domain language. When it suggests refactors, it names modules and seams using vocabulary from `CONTEXT.md` so suggestions fit the project's mental model.

It also reads `docs/adr/` to avoid re-suggesting decisions that were already made and recorded. If a refactor contradicts an ADR, it flags it as "worth reopening" rather than assuming the ADR is stale.

### `tdd` and `diagnose`

Both read `CONTEXT.md` to use consistent vocabulary in test names and explanations. They respect ADRs as load-bearing decisions.

### `grill-with-docs`

Updates `CONTEXT.md` when new domain terms emerge or fuzzy terms get sharpened. It also proposes ADRs when a design decision would benefit the team.

## Rules for `CONTEXT.md`

- **Vocabulary only** — define terms the codebase uses, not tutorial-style explanations
- **Invariants** — what must always be true (e.g. "every theme has at least one occurrence")
- **Seams** — where behavior can be altered without editing in place
- **Key concepts** — patterns or principles unique to IRIS

Use markdown with a glossary-style structure:

```markdown
## Glossary

### Theme
A pattern identified across journal entries. Properties: id, vector, summary, created_at.
Invariant: themes.created_at ≤ all occurrences.occurred_at.

### Resolution
Answer to "is this pattern fading or strengthening?" One of: dissipated, stabilized, persisting, reappearing.
...
```

## Rules for `docs/adr/`

Each ADR is a markdown file named `ADR-####-kebab-case-title.md`. Use the template in `docs/adr/ADR-0000-TEMPLATE.md`.

When a design decision affects multiple modules or represents a long-term choice, record it as an ADR so:
- Future refactors know *why* a constraint exists
- Architectural reviews don't re-litigate settled decisions
- New contributors understand the project's philosophy

## Current state

Both inputs exist: `CONTEXT.md` at the repo root holds the domain glossary, and
`docs/adr/` holds the template plus ADR-0001 onward. Read `docs/adr/README.md`
for the index.

### Sample ADR-0000-TEMPLATE.md

```markdown
# ADR-0000: Decision Title

## Status
Proposed | Accepted | Deprecated | Superseded by ADR-XXXX

## Context
Why are we making this decision? What problem does it solve?

## Decision
What we decided to do.

## Consequences
What becomes easier? What becomes harder?
```
