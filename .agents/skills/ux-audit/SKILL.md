---
name: ux-audit
description: "Use when auditing a live Lexful UAT journey (search, asset CRUD, document editing) for UX quality — flow, clarity, style-guide consistency, accessibility, navigation. Writes structured findings. The server renders the HTML report."
version: 0.18.0
status: "DRAFT — unsigned."
---

# UX audit

**Purpose.** Decide whether a Lexful release candidate is safe from a UX standpoint, and write findings the harness can score and show.

**Where this fits.** This is the UI/UX audit. It is its own switch, `QA_RUN_UX_AUDIT`. Set that to false to run functional QA only. It is not part of E2E User Journey TCs and it is not a step inside Feature Specific TCs. It runs on Lexful's live UAT app, logged in.

**Read in this order:**

| File | Role |
|---|---|
| `.agents/ux/checks.yaml` | Machine checks. Every finding cites one of these ids. |
| `.agents/ux/rulebook.md` | Five lenses, personas, and the severity scale. |
| `.agents/ux/pattern-library.md` | Exploratory pass. Cite `BP-*` when a pattern matches. |
| `.agents/ux/traceability.md` | QA-expected behavior is at most an Observation. |
| `.agents/skills/design-system/SKILL.md` | Written remediation: shadcn/ui component plus Fluent rationale. |

This skill is the procedure. Those files are the rules. Do not invent a second checklist.

---

## Audit inputs

1. **UAT login** — the session is already loaded. Never read credentials.
2. **The journey under this ticket** — search, asset CRUD, or document editing, limited to screens this ticket touches.
3. **Persona** — Technician by default. Say Admin or owner only when the Administration menu is visible.
4. `context-pack.json`, `FEATURE.md`, `explore/`, and `triage.json` in the run folder.

If the journey or the session is missing, say so and write a partial audit. Do not guess rules.

## Procedure

### Step 1 — Task completion
Walk the journey start to finish. Note anywhere the task cannot be completed, resets, or loses data. That alone can be an S0 or S1.

### Step 2 — Five lenses
Cite a rule id from `rulebook.md` or a check id from `checks.yaml` for every finding. A finding with neither is invalid.

| Order | Lens | What it catches |
|---|---|---|
| A | Flows and speed | Keyboard, hotkeys, focus, extra steps, unsaved work, destructive confirmation |
| B | Clarity and trust | Labels, errors, confirmations, AI transparency, sensitive-field masking |
| C | Style-guide consistency | Tokens, Storybook components, repeated patterns, icons |
| D | Accessibility | WCAG 2.1 AA contrast, focus, labels, color independence, modal focus, heading order, target size |
| E | IA and navigation | Current location, name match, back and refresh, search relevance, filter persistence |

### Step 2b — Pattern pass
Roam the same journey against `pattern-library.md`. Cite the pattern id (`BP-12`). This catches gaps the fixed checks did not name.

### Step 2c — Drift review
A healed locator means the robot adapted. It does not mean a technician would not be confused. Read `triage.json`.

| ID | Rule |
|---|---|
| H1 | Log every heal: old locator, new locator, and the screenshots the healer already captured. |
| H2 | A heal appears in the report even when the test passed. |
| H3 | Run the healed element through the five lenses. |
| H4 | A heal on search, save, or a primary CTA is at least S2. |
| H5 | The same element healing across runs is an unstable-UI watch, even with no rule break yet. |
| H6 | A heal does not close a regression. A person confirms a fix. |

### Step 3 — Severity
Use the scale below. Apply at most one adjustment, and say why.

- Workaround exists → one step down.
- High-repetition path (search, save) → one step up.
- Regression vs. the previous release → one step up.
- The auditor does not assign S0 or S1 without the evidence gate, and does not lower one.

### Step 4 — Noise control
1. Deduplicate against findings already in this run.
2. Group polish on one screen into one finding.
3. Low confidence stays in the report. Do not treat it as a blocker.
4. Skip anything `traceability.md` or the do-not-flag list calls intentional.

### Step 5 — Write the finding
Each object in `ux-findings.json` needs: `id`, `lens`, `checkId`, `title`, `severity`, `confidence`, `evidence`, `solution`, `implementationShadcn`, `fluentRationale`, `qaRefs`. Add `relatedPattern` when a `BP-*` applies.

`evidence` is what you observed, with the page and the repro. `solution` is the change in plain language. `implementationShadcn` and `fluentRationale` come from the design-system skill. Mark any prop you did not confirm in the docs.

### Step 6 — Scorecard
Write `ux-scorecard.json` with `counts` (`S0`, `S1`, `S2`, `S3`, `O`), `envNotes`, and a draft `verdict`. The harness recomputes the score and the verdict, then fills the report template.

Start at 100. Subtract S0 40, S1 25, S2 10, S3 3. Observations subtract nothing. Floor at 0.

| Sev | Meaning | Score | Verdict |
|---|---|---|---|
| S0 | Broken: journey cannot finish, data lost, or crash | -40 | BLOCKING-FAIL |
| S1 | A core task cannot be completed by any normal path | -25 | BLOCKING-FAIL |
| S2 | Task completes, but a typical technician is misled or slowed | -10 | ADVISORY-FAIL |
| S3 | Polish, or a non-essential WCAG AA miss | -3 | ADVISORY-FAIL |
| O | Works as intended. A design suggestion | 0 | no effect |

Any S0 or S1 makes the verdict `BLOCKING-FAIL`. S2 or S3 with no S0 or S1 is `ADVISORY-FAIL`. Only observations, or no findings, is `PASS`. The score is advisory. It does not change the functional QA verdict.

Calibration and the S0/S1 evidence gate are in `checks.yaml` (`meta.calibration_rules`, `meta.evidence_gate`) and rulebook section 7b. Never copy wording or ids from sample files.

## Report
`.agents/skills/lexful-ux-audit-gate/SKILL.md` is the report contract, and `audit-preview.html` beside it is the template. The harness fills that template and writes `ux-report.html`. Defects (S0–S3) and observations (O) go in separate sections. There are no mock images.

Do not write HTML, `ux-report.html`, `ux-report.md`, or a `before-after/` folder. Do not copy the template into the run folder.

## Guardrails
- Recommend only. Never edit product code or product data.
- UAT and demo data only.
- Credentials never appear in findings, notes, or screenshots.
- Do not open `.env` or session files. Load auth with `playwright-cli state-load`.

## Changelog
- **v0.18.0**: The report template lives in `lexful-ux-audit-gate`. The harness fills it. The auditor writes JSON only. Observations are a separate section from defects.
- **v0.17.0**: One naming scheme (`ux-audit`, `design-system`, `checks.yaml`, `rulebook.md`, `pattern-library.md`, `traceability.md`). Removed the before/after skill, its toggles, `visual_fix`, and the live findings log. Written remediation stays in the design-system skill.
- **v0.16.0**: QA ingestion for search, asset CRUD, and document editing. `traceability.md` is the cross-check. QA-expected behavior is at most an Observation.
