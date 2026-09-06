# Triage Labels

IRIS uses five canonical labels for issue workflow. These are applied by the `triage` skill as issues move through evaluation.

## Labels

| Label | Meaning | Next Step |
|-------|---------|-----------|
| `needs-triage` | Maintainer must evaluate | Read issue, apply `needs-info`, `ready-for-agent`, or `wontfix` |
| `needs-info` | Waiting on reporter | Ping reporter for clarification, move to another label once info arrives |
| `ready-for-agent` | Fully specified, AFK-ready | Agent can pick up with no human context needed |
| `ready-for-human` | Needs human implementation | Human developer implements |
| `wontfix` | Will not be actioned | Close the issue |

## Workflow state machine

```
needs-triage
    ↓
    ├─→ needs-info ──→ (reporter responds) ──→ ready-for-agent or ready-for-human
    ├─→ ready-for-agent ──→ (agent implements) ──→ (closed)
    ├─→ ready-for-human ──→ (human implements) ──→ (closed)
    └─→ wontfix ──→ (closed)
```

## No custom mapping

Since you just started with GitHub Issues, these labels use their canonical names. If you later want to use different names (e.g. `bug:triage` instead of `needs-triage`), add a mapping table to this file and the skill will apply the mapped names instead.
