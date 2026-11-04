---
name: ux-audit
description: "Use when auditing a live Lexful UAT journey (search, asset CRUD, document editing) for UX quality: flow, clarity, style-guide consistency, accessibility, navigation. The auditor writes ux-findings.json and ux-scorecard.json; the server scores them and renders the interactive HTML report."
version: 0.28.0
status: "DRAFT, unsigned"
---

# Lexful UX Audit Gate

**How this runs in the harness.** The `ux-audit` phase (`.agents/prompts/ux-auditor.md`) is a session of the same `qa` agent on the same model. You audit the live journey and write `ux-findings.json` and `ux-scorecard.json` in the run directory. You do not write `ux-report.html`, run the generator or the contract check, or read `.agents/ux/audit-preview-reference.html`. The server computes the score and the verdict from your severities, renders the report with `scripts/generate_ux_report.py`, and checks it against `.agents/ux/report-contract.md`; a report that fails the check is an open issue of the run, so every finding must carry the fields in section 4.

## 1. Required source files and authority order
Consult these before classifying findings:
1. `.agents/ux/rulebook.md`: audit method, lenses, severity scale, evidence gate, pass/fail bar, finding contract.
2. `.agents/ux/pattern-library.md`: pattern identifiers and anti-pattern descriptions.
3. `.agents/ux/checks.yaml`: machine-readable check IDs, severity guidance, confidence, verification method and solution guidance. It is large: grep it for the check ids of the journey instead of reading it whole.
4. `.agents/ux/traceability.md`: known QA coverage, intended behavior, known issues and false-positive guardrails.
5. `.agents/skills/design-system/SKILL.md` and its `references/`: implementation mapping and Fluent-aligned design guidance for the shadcn/ui + Radix + Tailwind stack. Read it before you write the first `solution`.
6. Prior ticket run findings (`ux-findings.json` in the run folders `history.md` lists): when auditing a re-run, heal or regression pass on an existing ticket, review them to verify which issues stakeholders have resolved.

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
- If there are no S0/S1 findings and no S2/S3, the verdict is **PASS**. If S2 and/or S3 exist, label it **PASS WITH ADVISORIES**. Show the non-blocking findings prominently, but do not call the verdict `FAIL`, `ADVISORY-FAIL`, `BLOCKING-FAIL`, or similar.
- Only one or more validated S0/S1 findings can produce **BLOCKED**.
- A score below 100 is not itself a failure. The score communicates quality; the release verdict is determined separately by the S0/S1 gate.
- O observations never lower the score and never block.
- Keep report-generation, browser, tooling, missing-evidence, and infrastructure errors distinct from UX severity. Do not disguise an execution error as a UX finding, and do not silently claim success if the audit could not be completed.

### Evidence and calibration gates
- S0/S1 require the Rulebook evidence gate: reproduce at least twice, capture evidence that shows the problem, and attempt to disprove the claim. If evidence contradicts the claim, withdraw or downgrade it.
- **Mandatory Screenshot Evidence for Observations (O):** Every Observation (`O`) recorded during a run MUST capture and attach a concrete live evidence screenshot (`.png` artifact saved under `explore/ux/` or `ux-evidence/`). The screenshot visually proves the observed behavior, state, disabled gate, or UI pattern so human reviewers and downstream developers can inspect and check it directly in the report without re-running the test.
- S2 must state the observed reason a typical technician would be misled or slowed; do not infer impact from preference alone.
- A visible outcome counts as feedback. A missing toast is normally S3 if the outcome is plainly visible; it is S2 only when the outcome is not clear.
- Intended-by-design behavior and behavior QA verifies as expected are not defects; classify at most as O when a design suggestion is useful, and attach the supporting screenshot.
- WCAG A/AA failure is at least S3; raise to S2 only when it blocks keyboard or screen-reader use of a core task.
- Rate observed behavior, not an idealized redesign. Low confidence must be explicit.

### Ticket Re-Run Resolution Verification Protocol (Mandatory)
When auditing a ticket that has prior audit findings from an earlier run (found in `ux-findings.json` in the run folders `history.md` lists):
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
- Do not count a test execution failure as an S0 product defect without evidence that the product itself caused the failure.
- Example calibration: 2 × S3 + 1 × O = 94/100 and **PASS WITH ADVISORIES**, assuming no S0/S1.

## 4. Finding schema — every finding
Each defect or observation must contain as much of the following as the run can establish; explicitly mark unavailable evidence rather than fabricate it:
- Unique finding ID; type (`Functional`, `UX`, `Accessibility`, or `Observation`).
- Journey, screen, step, and run label.
- Concise title; severity and plain-language severity rationale.
- Expected vs. actual behavior.
- Observed impact, affected user/task, and why it matters.
- Numbered reproduction steps (`reproSteps`, an array of strings; one user action each).
- **Evidence screenshot (`screenshot`):** mandatory path to a `.png` capture saved under `explore/ux/` or `ux-evidence/` showing the observation or defect in the running UI, plus `screenshotCaption`.
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
- **UX Rulebook Check Tag (`.tag-rule`):** exact Rulebook rule IDs and/or `.agents/ux/checks.yaml` check IDs (`CRUD-*`, `A11Y-*`, `DOC-*`, `SRCH-*`, etc.). Rendered with a check/rule icon and cyan border.
- **Bad UX Pattern Tag (`.tag-pattern`):** exact pattern IDs from `.agents/ux/pattern-library.md` (`BP-*`). Rendered with an alert icon and rose/warning border.
- **UX Lens Tag (`.tag-lens`):** A — Flows & speed; B — Clarity & trust; C — Style-guide consistency; D — Accessibility; E — Information architecture & navigation.
- **QA Trace Tag (`.tag-qa`):** applicable QA test/spec IDs from `.agents/ux/traceability.md` or the relevant check's `qa_refs`.
- **Design Stack Tag (`.tag-stack`):** `shadcn/ui`, `Radix`, `Tailwind`, `Fluent-aligned`, and relevant component names only when supported by the observed stack or recommendation.
- **Confidence/Status Badges:** confidence (`High`, `Medium`, `Low`) and lifecycle status (`Reported`, `Resolved`, `Held for review`, `Withdrawn`, `Not evaluated`).
Never fabricate IDs. If a mapping is plausible but unconfirmed, mark it `Candidate mapping` and lower confidence accordingly.

## 6. What the server renders from your fields
The report follows `.agents/ux/report-contract.md`; you do not produce markup. From your JSON it renders one Acceptance Criteria & Scope Matrix row per criterion and scope statement (from `acceptanceCriteria` tags), the journey's Evaluated Checks (from `checkId`), Expected and Observed callouts on every card (from `expectedVsActual`), numbered reproduction steps (from `reproSteps`), the evidence screenshot (from `screenshot` and `screenshotCaption`), and a resolution block as What to change / Developer / Design (from `solution`). It derives one verdict from the severities. S2/S3 never block; only a validated S0/S1 gives `BLOCKED`.

Recommendations are advisory and must be concrete, feasible and proportional to severity. Keep the plain-English fix, the developer implementation (shadcn/ui + Radix + Tailwind), the Fluent design rationale and the acceptance criteria in separate fields. Do not recommend wholesale adoption of Fluent React. Respect the authority order in the design-system skill: Lexful's Storybook/style guide first, Fluent guidance second, shadcn defaults third. Before you state exact props or variants, verify them against the skill's references; web access is denied in a run, so label anything taken from memory or the reference `Not verified in this run/reference`. No visual mockups or before/after images: text guidance only.

## 7. Failure handling
- If there are no findings, write an empty `ux-findings.json` array and the scorecard; do not invent findings.
- Keep browser, tooling, missing-evidence and infrastructure errors distinct from UX severity. Do not disguise an execution error as a UX finding, and do not claim a pass for a journey you could not exercise: say what did and did not run in `ux-scorecard.json` → `envNotes`.
- Recommendations are advisory. Use UAT and synthetic/demo data only, read-only by default; credentials must never appear in findings or screenshots. A named human reviewer signs off.
