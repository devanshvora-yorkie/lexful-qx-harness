---
name: lexful-ux-audit-gate
description: "Use when auditing a live Lexful UAT journey (search, asset CRUD, document editing) for UX quality — flow, clarity, style-guide consistency, accessibility, navigation. Produces an interactive, self-contained HTML audit report."
version: 0.22.0
status: "DRAFT — unsigned. HTML Output Mode Active."
config:
  output_mode: html_preview
---

# Lexful UX Audit Gate

## Antigravity Docker Environment Testing
- When testing these skill files on the Antigravity platform, execution must run through the designated Docker container or image environment.
- Ensure the Docker environment is running before validating UX skill findings.
- Do not claim a test or audit passed if the browser, Docker environment, required page, or evidence capture failed. Report execution/infrastructure errors separately from UX findings.

## 1. Required source files and authority order
Before classifying findings, consult the current files in the kit:
1. `Lexful_UX_Rulebook_v0.5.md` — audit method, lenses, severity scale, evidence gate, pass/fail bar, finding contract.
2. `Lexful_Bad_UX_Pattern_Library_v0.6.md` — pattern identifiers and anti-pattern descriptions.
3. `lexful-ux-checks.yaml` — machine-readable check IDs, severity guidance, confidence, verification method and solution guidance.
4. `QA_TRACEABILITY.md` — known QA coverage, intended behavior, known issues and false-positive guardrails.
5. `.agents/skills/fluent-ui-design-system/SKILL.md` and its `references/` files — implementation mapping and Fluent-aligned design guidance for the existing shadcn/ui + Radix + Tailwind stack.
6. `templates/audit-preview-reference.html` — visual/layout reference for the interactive report. It contains example run data; never carry example IDs, findings, scores, screenshots, counts or product details into a real run.
7. Prior ticket run findings (`runs/tickets/<ticket>/*/ux-findings.json`) — when auditing a re-run, heal, or regression pass on an existing ticket, review prior findings to verify which issues stakeholders have resolved.

If sources disagree, respect Lexful's product facts and QA traceability first, then the UX Rulebook and machine-readable checks for classification, and the Fluent/shadcn skill for implementation suggestions. Do not invent rule IDs or pattern IDs. If no exact mapping exists, use a clearly labelled `Unmapped / candidate` tag and explain why; do not imply a confirmed rule match.

## 2. Severity and release verdict — mandatory
Use the severity scale in the UX Rulebook:
- **S0** — journey cannot be completed, data is lost/corrupted, or page crashes. Deduction: **−40**. Blocking.
- **S1** — core task cannot be completed by any normal path and there is no workaround. Deduction: **−25**. Blocking.
- **S2** — task completes, but a typical technician is observably misled or slowed. Deduction: **−10**. Non-blocking.
- **S3** — polish/minor inconsistency or WCAG AA miss on a non-essential element. Deduction: **−3**. Non-blocking.
- **O (Observation)** — behavior works as intended and is understandable; optional design suggestion. Deduction: **0**.

### Never fail the audit/report because of S2 or S3
This rule is explicit and overrides any ambiguous wording in older templates or generated output:
- **S2 and S3 findings MUST NOT cause an audit failure, release-blocking verdict, process exception, aborted report, missing report, or skipped report sections.**
- If there are no S0/S1 findings, the release verdict is **PASS**. If S2 and/or S3 exist, label it **PASS WITH ADVISORIES** (or **PASS (Advisory)**). Show the non-blocking findings prominently, but do not call the verdict `FAIL`, `ADVISORY-FAIL`, `BLOCKING-FAIL`, or similar.
- Only one or more validated S0/S1 findings can produce **FAIL / BLOCKING FAIL**.
- A score below 100 is not itself a failure. The score communicates quality; the release verdict is determined separately by the S0/S1 gate.
- O observations never lower the score and never block.
- Keep report-generation, browser, Docker, missing-evidence, and infrastructure errors distinct from UX severity. Do not disguise an execution error as a UX finding, and do not silently claim success if the audit could not be completed.

### Evidence and calibration gates
- S0/S1 require the Rulebook evidence gate: reproduce at least twice, capture evidence that shows the problem, and attempt to disprove the claim. If evidence contradicts the claim, withdraw or downgrade it.
- **Mandatory Screenshot Evidence for Observations (O):** Every Observation (`O`) recorded during a run MUST capture and attach a concrete live evidence screenshot (`.png` artifact saved under `explore/ux/` or `ux-evidence/`). The screenshot visually proves the observed behavior, state, disabled gate, or UI pattern so human reviewers and downstream developers can inspect and check it directly in the report without re-running the test.
- S2 must state the observed reason a typical technician would be misled or slowed; do not infer impact from preference alone.
- A visible outcome counts as feedback. A missing toast is normally S3 if the outcome is plainly visible; it is S2 only when the outcome is not clear.
- Intended-by-design behavior and behavior QA verifies as expected are not defects; classify at most as O when a design suggestion is useful, and attach the supporting screenshot.
- WCAG A/AA failure is at least S3; raise to S2 only when it blocks keyboard or screen-reader use of a core task.
- Rate observed behavior, not an idealized redesign. Low confidence must be explicit.

### Ticket Re-Run Resolution Verification Protocol (Mandatory)
When auditing a ticket that has prior audit findings from an earlier run (found in `runs/tickets/<ticket>/*/ux-findings.json`):
1. **Never re-detect resolved issues as active defects:** If stakeholders or developers resolved an issue previously reported on this ticket (e.g. focus return fixed, accessible label added, loading feedback smoothed, gate explained), the auditor **must not** log or detect it as an active S0, S1, S2, or S3 defect.
2. **Live verification & evidence:** Actively inspect the control, journey step, or accessibility property on live UAT. Capture a fresh verification screenshot (`explore/ux/resolved-<id>.png` or `ux-evidence/resolved-<id>.png`) proving the fixed behavior on UAT.
3. **Lifecycle Status `Resolved`:** Set `status: "Resolved"`, `severity: "O"`, `deduction: 0`, and `releaseBlocking: false`. Provide a `resolutionNote` detailing how the fix was verified (e.g., "Verified fixed on live UAT: focus now returns correctly to the opener button after drawer close; screenshot attached").
4. **Zero score penalty:** Resolved findings carry **0 deduction points** and must never reduce the quality score or trigger an advisory or blocking fail. They are presented under the *UX Observations & Verification* tab under the `Resolved` filter pill to give stakeholders and developers visible credit for resolved issues.
5. **Persisting issues:** If a finding from a prior run is verified to still be broken on UAT, retain it as an active defect with its original finding ID and severity, noting that the issue persists across runs.

## 3. Scoring rules
- Start at **100**.
- Deduct once per unique, reportable defect: S0 −40, S1 −25, S2 −10, S3 −3, O −0.
- Resolved findings carry **0 deduction points** and do not lower the score.
- Score formula: `max(0, 100 - sum(unique finding deductions))`. Do not let the score fall below 0.
- Deduplicate the same underlying defect across checks/screens before scoring. If one issue maps to multiple rules/patterns, list all applicable tags but apply only the highest justified severity deduction once for that underlying issue. If genuinely distinct impacts require separate findings, explain the distinction.
- Display: final score `/100`, total deduction, count by S0/S1/S2/S3/O, and a transparent deduction ledger with finding ID, severity, points deducted, and resulting subtotal.
- Do not count a test execution failure as an S0 product defect without evidence that the product itself caused the failure.
- Example calibration: 2 × S3 + 1 × O = 94/100 and **PASS WITH ADVISORIES**, assuming no S0/S1.

## 4. Finding schema — every finding
Each defect or observation must contain as much of the following as the run can establish; explicitly mark unavailable evidence rather than fabricate it:
- Unique finding ID; type (`Functional`, `UX`, `Accessibility`, or `Observation`).
- Journey, screen, step, and run label.
- Concise title; severity and plain-language severity rationale.
- Expected vs. actual behavior.
- Observed impact, affected user/task, and why it matters.
- Numbered reproduction steps.
- **Evidence screenshot (`screenshot`):** mandatory path to a `.png` capture saved under `explore/ux/` or `ux-evidence/` (or embedded base64 data URI in HTML) showing the observation or defect in the running UI, plus `screenshotCaption`.
- Evidence reference (screenshot, trace, DOM/accessibility details, or test ID) and evidence limitations (if screenshot capture failed, state why explicitly).
- Confidence (`High`, `Medium`, `Low`).
- Applicable UX Rulebook lens and exact rule/check ID(s), where supported.
- Applicable Bad UX Pattern Library ID(s), where supported.
- Recommended resolution and acceptance/verification criteria.
- Component-level shadcn/ui implementation adaptation and separate Fluent UI design-reference adaptation, where relevant.
- Deduction points (0 for O and 0 for Resolved) and whether it is release-blocking (never for Resolved or O).
- Lifecycle status (`Reported`, `Resolved`, `Held for review`, `Withdrawn`, `Not evaluated`). For resolved findings, include `resolutionNote` explaining how the stakeholder fix was verified on live UAT, and `resolvedFromRun` citing the earlier run ID.

## 5. Tags and source traceability
Show tags on each finding as compact, filterable chips with distinct visual styling:
- **UX Rulebook Check Tag (`.tag-rule`):** exact Rulebook rule IDs and/or `lexful-ux-checks.yaml` check IDs (`CRUD-*`, `A11Y-*`, `DOC-*`, `SRCH-*`, etc.). Rendered with a check/rule icon and cyan border.
- **Bad UX Pattern Tag (`.tag-pattern`):** exact pattern IDs from `Lexful_Bad_UX_Pattern_Library_v0.6.md` (`BP-*`). Rendered with an alert icon and rose/warning border.
- **UX Lens Tag (`.tag-lens`):** A — Flows & speed; B — Clarity & trust; C — Style-guide consistency; D — Accessibility; E — Information architecture & navigation.
- **QA Trace Tag (`.tag-qa`):** applicable QA test/spec IDs from `QA_TRACEABILITY.md` or the relevant check's `qa_refs`.
- **Design Stack Tag (`.tag-stack`):** `shadcn/ui`, `Radix`, `Tailwind`, `Fluent-aligned`, and relevant component names only when supported by the observed stack or recommendation.
- **Confidence/Status Badges:** confidence (`High`, `Medium`, `Low`) and lifecycle status (`Reported`, `Resolved`, `Held for review`, `Withdrawn`, `Not evaluated`).
Never fabricate IDs. If a mapping is plausible but unconfirmed, mark it `Candidate mapping` and lower confidence accordingly.

## 6. Interactive HTML report — required deliverable
Generate a **complete, valid, interactive HTML report (`ux-report.html`)** for every completed audit run. The report is the primary deliverable; do not replace it with a prose-only summary. Use the supplied `templates/audit-preview-reference.html` as the visual reference for structure, dark theme, gradients, typography, glass-like cards, badges, score gauge, stat cards, tab navigation, finding cards, tables, and responsive layout. Preserve its visual language and useful interactions while replacing all example content with the current run's real data.

The report must work as a local HTML file without a build step. Inline the report CSS and JavaScript. Do not require a server-side runtime. External font loading may be retained as a progressive enhancement, with sensible system-font fallbacks. Escape all dynamic strings before inserting them into HTML. Do not embed credentials, tokens, private tenant data, or unnecessary personal data.

### Required page structure
1. **Top navigation / run metadata:** kit/audit name, run ID, timestamp, target/environment, journey, audit status and QA status if available.
2. **Hero / executive summary:** concise scope and summary, release verdict, score gauge, and explanation that S2/S3 are non-blocking.
3. **Metric cards:** final score, total deductions, counts by severity, automated checks passed/failed/skipped, confidence/evidence coverage, and detected design stack where known. Never invent unavailable metrics; show `N/A` or `Not collected`.
4. **Interactive tabs or equivalent accessible navigation:**
   - **UI/UX Defects (S0–S3):** A dedicated section strictly for S0–S3 defect findings, featuring severity filter pills (`All Defects`, `S0`, `S1`, `S2`, `S3`), deduction details, and defect finding cards. If 0 defects exist, render an explicit positive empty state.
   - **UX Observations & Verification (O):** A separate, dedicated section for all Observation (`O`) and `Resolved` items (positive verifications, intended behaviors, stakeholder resolutions, design suggestions, or items held for review). Includes an informational callout banner emphasizing that observations and resolved items carry **0 deduction points** and **zero release-blocking impact**, plus status filter pills (`All Observations`, `Reported`, `Resolved`, `Held for review`, `Not evaluated`, `Withdrawn`).
   - **Visual Evidence & Lightbox:** Screenshot and trace evidence with captions and an interactive lightbox.
   - **Evaluated Checks Matrix:** Table of evaluated and not-evaluated checks from the UX Rulebook.
   - **Scoring & Deduction Ledger:** Transparent points deduction ledger with running subtotals and non-blocking calibration rules.
5. **Finding & observation card layout:**
   Each card must visibly feature:
   - Header with ID, severity badge (`.badge-s0` to `.badge-s3`, `.badge-obs`, or `.badge-resolved`), deduction points (0 for Resolved and O), confidence, and status.
   - Prominent badge chips for **Rulebook Check** (`.tag-rule`), **Bad UX Pattern** (`.tag-pattern`), **Lens** (`.tag-lens`), **QA Trace** (`.tag-qa`), and **Design Stack** (`.tag-stack`).
   - **Inline Evidence Screenshot (`.finding-image-preview`):** An embedded visual evidence preview containing the screenshot image, relative path label, and a one-click lightbox zoom trigger so reviewers can immediately see and verify what was observed in the HTML report.
   - `Observed defect & evidence` (or `Observed behavior & details` for observations).
   - `Expected vs. actual` behavior.
   - `Reproduction steps & QA trace`.
   - `Recommended resolution` (or `Recommended design direction` for observations).
   - `shadcn/ui implementation` — concrete component/composition props and Tailwind styling.
   - `Fluent design alignment` — Fluent UX principle/pattern alignment.
6. **Footer:** Report generation timestamp, ticket ID, engine metadata, and reviewer sign-off notice.

### Recommended solutions and design-system adaptations
- Recommendations must be concrete, feasible, and proportional to severity.
- Always separate **What to fix (plain English)**, **Developer implementation**, **Design rationale**, and **Acceptance criteria**.
- Keep **shadcn/ui implementation** and **Fluent UI adaptation** in separate labelled blocks. The product implementation baseline is shadcn/ui + Radix + Tailwind, with Fluent UI used as a design-alignment reference; do not recommend wholesale adoption of Fluent React.
- Use `.agents/skills/fluent-ui-design-system/SKILL.md`, `references/shadcn-components.md`, `references/components.md`, and `references/lexful-mapping.md`. Respect the documented authority order: Lexful's Storybook/style guide first, Fluent guidance second, shadcn defaults third.
- Before recommending exact props/variants/behavior, verify them against the supplied skill reference or official component docs when browsing is available. If not verified, label the recommendation `Not verified in this run/reference`.
- Avoid visual mockups and before/after image pairs. Text-based implementation guidance is required.

## 7. HTML interactions and accessibility
Implement working, keyboard-accessible:
- Tabs with correct selected state and keyboard/focus visibility.
- Severity filters for S0, S1, S2, S3 and O, plus All.
- Status filters for Reported, Resolved, Held for review, Withdrawn, Not evaluated, plus All.
- Search across finding title, summary, tags and IDs.
- Expand/collapse detail panels where useful.
- Evidence lightbox clickable from both card inline previews and the gallery tab; close button, Escape-to-close and accessible labels.
- Responsive layout for desktop and mobile; tables horizontally scroll on narrow screens.
- Respect reduced-motion preferences and ensure status is not communicated by colour alone.
- Use semantic headings, buttons, labels, visible focus indicators, sufficient contrast, and meaningful image alt text.
- The report must remain useful when JavaScript is unavailable: core finding and observation content should still be present in the HTML; JavaScript enhances filtering/tabs.

## 8. Report completeness and failure handling
- Always generate the report for a completed run, including when S2/S3 findings exist.
- If there are no findings, render an explicit empty state and the score/verdict; do not invent findings.
- If there are only S2/S3/O findings, render all of them and mark the verdict **PASS WITH ADVISORIES** when S2/S3 exist, or **PASS** when only O/no findings exist.
- If S0/S1 exists, render the full report and mark **FAIL / BLOCKING FAIL**; never abort report generation.
- If the audit itself is incomplete due to browser/Docker/tooling failure, generate a partial diagnostic report if possible, label the run `INCOMPLETE — NOT A PASS`, show what did and did not run, and keep this separate from the product release verdict. Never present incomplete execution as a successful audit.
- Do not suppress observations, recommendations, scoring ledger, or traceability because any severity is present.
- Do not use `verdict-advisory-fail` for S2/S3. Use a positive/pass-with-advisories state. The attached reference's sample verdict and data are examples only and must be replaced.

## 9. Final output
- Save/emit the completed report as a `.html` artifact whenever the environment supports file creation. If the interface requires returning the HTML source, return valid HTML without Markdown fences.
- Include a brief run summary separately only when the surrounding workflow permits; it must not replace the HTML artifact.
- Never claim the report was generated unless the artifact/source is actually present.
- Recommendations are advisory. The AI does not modify product data. Use UAT and synthetic/demo data only; read-only by default; credentials must never appear in prompts, reports, or screenshots. A named human reviewer signs off.

## Changelog
- **v0.22.0 — 2026-10-29:** Introduced Ticket Re-Run Resolution Verification Protocol: when re-running on a ticket, check prior findings; if stakeholders resolved the defect, verify on live UAT with a screenshot, mark `status: "Resolved"`, do NOT re-detect as a defect, and apply 0 score deductions; added `Resolved` status filter and badge.
- **v0.21.0 — 2026-10-29:** Mandated live evidence screenshots (`.png`) for all UX observations (`O`); required explicit `screenshot` path and caption in finding/observation schema; required inline `.finding-image-preview` screenshot thumbnails within every observation card on `ux-report.html` with click-to-lightbox support.
- **v0.20.0 — 2026-10-28:** Clarified that S2/S3 are strictly non-blocking and must never fail/abort the audit or report; formalized scoring/deduplication; required traceable UX-rule and bad-pattern tags; added separate observation impact/resolution and shadcn/Fluent recommendation sections; expanded the interactive HTML report contract.
