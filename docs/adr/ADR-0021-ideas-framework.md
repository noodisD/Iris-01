# ADR-0021: Ideas are confirmed propositions, not measured themes

## Status

Accepted — 2026-09-24

## Context

IRIS finds psychological patterns in what the owner logged, under a
non-interpretive contract: it reports observations and the evidence behind
them, and it does not assume causality or offer unsolicited advice. The owner
also wants a place for philosophical, political, ethical and economic
positions. Those are arguments, not occurrences. Counting them as themes would
treat a stated principle as a personality measurement, and running them through
the causal-word firewall would drop the claims the feature exists to keep.

## Decision

- Ideas are a separate store from themes. Nothing in this store is a selectable
  psychological engine, and nothing here passes through admission, narrative
  templates, or `FORBIDDEN_REGEX`.
- One verified passage is enough. Repetition establishes neither validity nor
  endorsement.
- The owner confirms both the evidence and their present position. Old writing
  never sets current belief by itself. A statement is immutable once proposed;
  a changed proposition is another node.
- Iris may propose links and, only on request, critique an argument. Critiques
  are labelled Iris output. They are never reread as the owner's writing, never
  used as extraction input, and never written into the graph automatically.
- Editing or deleting a reflection removes quotations derived from it. A date
  supplied later is read from the live reflection. An idea with no remaining
  valid quotation stays as a decision, marked as needing evidence, and leaves
  the graph until it is re-anchored.

## Consequences

The Ideas screen can hold arguments, open tensions, and an on-request
challenge without weakening the psychological contract. Chat, Insights, and
the Android app do not read this store.

A future feature that feeds a critique, a link rationale, or an idea statement
back into evidence, chat context, or theme measurement reopens this ADR.
