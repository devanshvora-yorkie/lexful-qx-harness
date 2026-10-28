---
name: lexful-ux-audit-gate
description: "Use when auditing a live Lexful UAT journey (search, asset CRUD, document editing) for UX quality — flow, clarity, style-guide consistency, accessibility, navigation. Produces an interactive, self-contained HTML audit report."
version: 0.20.0
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
- S2 must state the observed reason a typical technician would be misled or slowed; do not infer impact from preference alone.
- A visible outcome counts as feedback. A missing toast is normally S3 if the outcome is plainly visible; it is S2 only when the outcome is not clear.
- Intended-by-design behavior and behavior QA verifies as expected are not defects; classify at most as O when a design suggestion is useful.
- WCAG A/AA failure is at least S3; raise to S2 only when it blocks keyboard or screen-reader use of a core task.
- Rate observed behavior, not an idealized redesign. Low confidence must be explicit.

## 3. Scoring rules
- Start at **100**.
- Deduct once per unique, reportable defect: S0 −40, S1 −25, S2 −10, S3 −3, O −0.
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
- Evidence reference (screenshot, trace, DOM/accessibility details, or test ID) and evidence limitations.
- Confidence (`High`, `Medium`, `Low`).
- Applicable UX Rulebook lens and exact rule/check ID(s), where supported.
- Applicable Bad UX Pattern Library ID(s), where supported.
- Recommended resolution and acceptance/verification criteria.
- Component-level shadcn/ui implementation adaptation and separate Fluent UI design-reference adaptation, where relevant.
- Deduction points (0 for O) and whether it is release-blocking.

## 5. Tags and source traceability
Show tags on each finding as compact, filterable chips. Use tags from these sources only when there is a defensible match:
- **UX lens:** A — Flows & speed; B — Clarity & trust; C — Style-guide consistency; D — Accessibility; E — Information architecture & navigation.
- **Rule/check:** exact Rulebook rule IDs and/or `lexful-ux-checks.yaml` check IDs.
- **Bad UX pattern:** exact pattern IDs from `Lexful_Bad_UX_Pattern_Library_v0.6.md`.
- **QA trace:** applicable QA test/spec IDs from `QA_TRACEABILITY.md` or the relevant check's `qa_refs`.
- **Design stack:** `shadcn/ui`, `Radix`, `Tailwind`, `Fluent-aligned`, and relevant component names only when supported by the observed stack or recommendation.
- **Confidence/evidence:** confidence, evidence type, and `Needs verification` when appropriate.
Never fabricate IDs. If a mapping is plausible but unconfirmed, mark it `Candidate mapping` and lower confidence accordingly.

## 6. Interactive HTML report — required deliverable
Generate a **complete, valid, interactive HTML report** for every completed audit run. The report is the primary deliverable; do not replace it with a prose-only summary. Use the supplied `templates/audit-preview-reference.html` as the visual reference for structure, dark theme, gradients, typography, glass-like cards, badges, score gauge, stat cards, tab navigation, finding cards, tables, and responsive layout. Preserve its visual language and useful interactions while replacing all example content with the current run's real data.

The report must work as a local HTML file without a build step. Inline the report CSS and JavaScript. Do not require a server-side runtime. External font loading may be retained as a progressive enhancement, with sensible system-font fallbacks. Escape all dynamic strings before inserting them into HTML. Do not embed credentials, tokens, private tenant data, or unnecessary personal data.

### Required page structure
1. **Top navigation / run metadata:** kit/audit name, run ID, timestamp, target/environment, journey, audit status and QA status if available.
2. **Hero / executive summary:** concise scope and summary, release verdict, score gauge, and explanation that S2/S3 are non-blocking.
3. **Metric cards:** final score, total deductions, counts by severity, automated checks passed/failed/skipped, confidence/evidence coverage, and detected design stack where known. Never invent unavailable metrics; show `N/A` or `Not collected`.
4. **Interactive tabs or equivalent accessible navigation:**
   - **Findings:** S0–S3 defects, with severity filters and search.
   - **Observations:** a distinct section for all O items, separate from defects.
   - **Evidence:** screenshot/trace evidence, captions, and an accessible lightbox where screenshots exist. If no visual evidence exists, state that clearly; do not fabricate images.
   - **Rulebook & Bad UX Pattern Mapping:** rule/check/pattern/QA tags and traceability.
   - **Recommended Solutions:** prioritised, actionable fixes and acceptance criteria.
   - **shadcn/ui + Fluent Adaptation:** distinct implementation and design-reference guidance.
   - **Checks / QA Traceability:** automated checks, results, skipped checks and links/IDs where supplied.
   - **Scoring & Method:** severity scale, score ledger, verdict logic, evidence limitations and assumptions.
   - **Run diagnostics / Self-healing & Triage:** only if these data were actually collected; do not invent self-healing attempts.
   - **Code/schema diff:** only when supplied by the run; otherwise omit the tab or label it unavailable.
5. **Separate observation detail:** each observation must have its own title, what was observed, user/task impact (or explicitly “no demonstrated negative impact”), recommendation/resolution, optional shadcn/Fluent suggestion, and reason it remains O rather than a defect.
6. **Footer:** report generation timestamp, source/skill versions when known, and note that a human reviewer signs off.

### Finding card layout
Each defect card should visibly separate:
- ID, severity, deduction, confidence, and release-blocking status.
- Title and concise summary.
- `Observed defect & evidence`.
- `User / workflow impact`.
- `Expected vs. actual`.
- `Reproduction steps`.
- `UX rulebook + bad-pattern tags`.
- `Recommended resolution`.
- `shadcn/ui implementation` — concrete component/composition and relevant props, states, or Tailwind direction only if verified/supported. Do not invent component props.
- `Fluent UI adaptation` — the Fluent design pattern/principle to align with, not an instruction to replace Lexful's stack with Fluent React.
- `Acceptance criteria / how to verify`.
- Evidence preview and link/reference when available.

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
- Search across finding title, summary, tags and IDs.
- Expand/collapse detail panels where useful.
- Evidence lightbox only when images exist; close button, Escape-to-close and accessible labels.
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
- **v0.20.0 — 2026-10-28:** Clarified that S2/S3 are strictly non-blocking and must never fail/abort the audit or report; formalized scoring/deduplication; required traceable UX-rule and bad-pattern tags; added separate observation impact/resolution and shadcn/Fluent recommendation sections; expanded the interactive HTML report contract.
