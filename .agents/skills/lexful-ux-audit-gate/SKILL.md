---
name: lexful-ux-audit-gate
description: "Report contract for a Lexful UX audit. The harness fills audit-preview.html from the auditor's JSON. The auditor does not write HTML."
version: 0.18.0
status: "DRAFT — unsigned. The harness renders the HTML report."
---

# UX report template

**Who fills this.** The harness, in `server/app/ux_report.py` (`write_ux_report`). The auditor writes `ux-findings.json` and `ux-scorecard.json` only.

Do not copy this template into the run folder. Do not fill the placeholders yourself. Do not write `ux-report.html`. A model-filled copy of this file is not a valid report.

**Template.** `.agents/skills/lexful-ux-audit-gate/audit-preview.html`

**Output.** `<run folder>/ux-report.html`

The harness reads the two JSON files, recomputes the score and the verdict, then replaces every placeholder below. It does not ask the model to emit HTML.

## Score and verdict

Start at 100. S0 −40, S1 −25, S2 −10, S3 −3, O −0. Floor at 0.

| Condition | Class | Meaning |
|---|---|---|
| Any S0 or S1 | `verdict-blocking-fail` | Blocks release. |
| No S0 or S1, and any S2 or S3 | `verdict-advisory-fail` | Does not block release. S2 and S3 are warnings. |
| Score 100 | `verdict-pass` | No scored findings. |

## Placeholders

| Token | Filled with |
|---|---|
| `__DATE__` `__RUN_ID__` `__TARGET__` | Run date, run id, ticket |
| `__SCORE__` `__GAUGE__` | Score and the gauge color for the verdict |
| `__VERDICT__` `__VERDICT_CLASS__` `__KICKER__` | Verdict label, CSS class, and the one-line explanation |
| `__COUNTS__` | S0, S1, S2, S3, O counts |
| `__DEFECT_INDEX__` `__DEFECTS__` | S0–S3 only. Each defect is `<article class="finding-card severity-SX">` with a title, observed defect, and design and remediation plan |
| `__OBSERVATION_INDEX__` `__OBSERVATIONS__` | Observations only, in `<section class="observations-section">`, below the defects |
| `__NOTES__` | Environment notes from the scorecard |

## Layout rules the harness keeps

- Defects and observations are separate. An Observation is never placed in `#findings`.
- No before/after images. The template has no `finding-image-preview` block, and the harness does not add one.
- Cards use the classes already in the template. The harness does not invent a second layout.

## Changelog
- **v0.18.0**: The template stays in this skill. The harness fills it. Observations render in their own section. The auditor no longer writes the HTML.
