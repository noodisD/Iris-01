# Context Pipeline Audit Report

**Date**: 2026-01-20T11:02:37.464659
**User ID**: 65
**Prompt Integrity Hash**: `36e4d1beb54ee747450634bf005a78c43c34742678d7b0d159afe3a60c82413c`

## 1. Executive Summary
- **Raw Insights Produced**: 20
- **Final Injected Insights**: 5
- **Drop Rate**: 75.0%

## 2. Gate Analysis (The Trace)
| Stage | Engine | Insight ID | Decision | Reason |
|---|---|---|---|---|
| gate_allowlist | persistence | persistence:theme:118 | **passed** | - |
| gate_allowlist | persistence | persistence:theme:121 | **passed** | - |
| gate_allowlist | persistence | persistence:theme:119 | **passed** | - |
| gate_allowlist | persistence | persistence:theme:120 | **passed** | - |
| gate_allowlist | trajectory | trajectory:theme:118 | **passed** | - |
| gate_allowlist | trajectory | trajectory:theme:121 | **passed** | - |
| gate_allowlist | trajectory | trajectory:theme:119 | **passed** | - |
| gate_allowlist | trajectory | trajectory:theme:120 | **passed** | - |
| gate_allowlist | trajectory | trajectory:theme:122 | **passed** | - |
| gate_allowlist | tension | tension:theme:118 | **passed** | - |
| gate_allowlist | tension | tension:theme:118 | **passed** | - |
| gate_allowlist | tension | tension:theme:118 | **passed** | - |
| gate_allowlist | tension | tension:theme:121 | **passed** | - |
| gate_allowlist | tension | tension:theme:121 | **passed** | - |
| gate_allowlist | tension | tension:theme:119 | **passed** | - |
| gate_allowlist | resolution | resolution:theme:118 | **passed** | - |
| gate_allowlist | resolution | resolution:theme:121 | **passed** | - |
| gate_allowlist | resolution | resolution:theme:119 | **passed** | - |
| gate_allowlist | resolution | resolution:theme:120 | **passed** | - |
| gate_allowlist | resolution | resolution:theme:122 | **passed** | - |
| gate_confidence | persistence | persistence:theme:118 | **passed** | - |
| gate_confidence | persistence | persistence:theme:121 | **passed** | - |
| gate_confidence | persistence | persistence:theme:119 | **passed** | - |
| gate_confidence | persistence | persistence:theme:120 | **dropped** | low_confidence |
| gate_confidence | trajectory | trajectory:theme:118 | **passed** | - |
| gate_confidence | trajectory | trajectory:theme:121 | **passed** | - |
| gate_confidence | trajectory | trajectory:theme:119 | **passed** | - |
| gate_confidence | trajectory | trajectory:theme:120 | **dropped** | low_confidence |
| gate_confidence | trajectory | trajectory:theme:122 | **passed** | - |
| gate_confidence | tension | tension:theme:118 | **dropped** | low_confidence |
| gate_confidence | tension | tension:theme:118 | **dropped** | low_confidence |
| gate_confidence | tension | tension:theme:118 | **dropped** | low_confidence |
| gate_confidence | tension | tension:theme:121 | **dropped** | low_confidence |
| gate_confidence | tension | tension:theme:121 | **dropped** | low_confidence |
| gate_confidence | tension | tension:theme:119 | **dropped** | low_confidence |
| gate_confidence | resolution | resolution:theme:118 | **passed** | - |
| gate_confidence | resolution | resolution:theme:121 | **passed** | - |
| gate_confidence | resolution | resolution:theme:119 | **passed** | - |
| gate_confidence | resolution | resolution:theme:120 | **passed** | - |
| gate_confidence | resolution | resolution:theme:122 | **passed** | - |
| gate_conflict | persistence | persistence:theme:118 | **passed** | - |
| gate_conflict | trajectory | trajectory:theme:118 | **passed** | - |
| gate_conflict | resolution | resolution:theme:118 | **passed** | - |
| gate_conflict | persistence | persistence:theme:121 | **passed** | - |
| gate_conflict | trajectory | trajectory:theme:121 | **passed** | - |
| gate_conflict | resolution | resolution:theme:121 | **passed** | - |
| gate_conflict | persistence | persistence:theme:119 | **passed** | - |
| gate_conflict | trajectory | trajectory:theme:119 | **passed** | - |
| gate_conflict | resolution | resolution:theme:119 | **passed** | - |
| gate_conflict | trajectory | trajectory:theme:122 | **passed** | - |
| gate_conflict | resolution | resolution:theme:122 | **passed** | - |
| gate_conflict | resolution | resolution:theme:120 | **passed** | - |
| gate_priority | resolution | resolution:theme:118 | **passed** | - |
| gate_priority | resolution | resolution:theme:121 | **passed** | - |
| gate_priority | resolution | resolution:theme:119 | **passed** | - |
| gate_priority | resolution | resolution:theme:120 | **passed** | - |
| gate_priority | resolution | resolution:theme:122 | **passed** | - |

## 3. Shadow Prompt Comparison
### Gated (Actual Context)
```
- The pattern 'Recurring theme' appeared frequently in the past but persisting recently.
- The pattern 'Recurring theme' appeared frequently in the past but persisting recently.
- The pattern 'Recurring theme' appeared frequently in the past but persisting recently.
- The pattern 'Recurring theme' appeared frequently in the past but persisting recently.
- The pattern 'Recurring theme' appeared frequently in the past but persisting recently.
```
### Ungated (Raw Context)
```
- The pattern 'Recurring theme' appeared frequently, totaling 10 occurrences since 2026-01-20.
- The pattern 'Recurring theme' appeared frequently, totaling 10 occurrences since 2026-01-20.
- The pattern 'Recurring theme' appeared frequently, totaling 5 occurrences since 2026-01-20.
- The pattern 'Recurring theme' appeared frequently, totaling 5 occurrences since 2026-01-20.
- The pattern 'Recurring theme' emerged in frequency over the recent period.
- The pattern 'Recurring theme' emerged in frequency over the recent period.
- The pattern 'Recurring theme' emerged in frequency over the recent period.
- The pattern 'Recurring theme' emerged in frequency over the recent period.
- The pattern 'Recurring theme' emerged in frequency over the recent period.
- The patterns 'Unknown Pattern' and 'Recurring theme' frequently appeared during the same periods with diverging activity levels.
- The patterns 'Unknown Pattern' and 'Recurring theme' frequently appeared during the same periods with diverging activity levels.
- The patterns 'Unknown Pattern' and 'Recurring theme' frequently appeared during the same periods with diverging activity levels.
- The patterns 'Unknown Pattern' and 'Recurring theme' frequently appeared during the same periods with diverging activity levels.
- The patterns 'Unknown Pattern' and 'Recurring theme' frequently appeared during the same periods with diverging activity levels.
- The patterns 'Unknown Pattern' and 'Recurring theme' frequently appeared during the same periods with diverging activity levels.
- The pattern 'Recurring theme' appeared frequently in the past but persisting recently.
- The pattern 'Recurring theme' appeared frequently in the past but persisting recently.
- The pattern 'Recurring theme' appeared frequently in the past but persisting recently.
- The pattern 'Recurring theme' appeared frequently in the past but persisting recently.
- The pattern 'Recurring theme' appeared frequently in the past but persisting recently.
```

## 4. Risk Surface Analysis
- **Health**: System is actively selecting high-quality insights.
