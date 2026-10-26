---
name: lexful-ux-audit-gate
description: "Use when auditing a live Lexful UAT journey (search, asset CRUD, document editing) for UX quality — flow, clarity, style-guide consistency, accessibility, navigation. Adapted from the Pave Zero Design ux-audit-gate skill for a real logged-in React app, not static HTML."
version: 0.16.0
status: "DRAFT — unsigned. Rules will change after Week 1 session with John Christensen."
config:
  before_after_comparison: false
  output_mode: simple
---
## Antigravity Docker Environment Testing
- When testing these skill files on the Antigravity platform, execution must run through the designated Docker container or image environment. 
- Ensure the Docker environment is running before validating the UX skill findings.

## Capability Toggles
- **Before-After Comparison**: The visual before-after generation capability can be toggled ON or OFF as required. By default, consider this OFF unless requested.

## Output Modes (Ticket Generation)
Provide output based on the requested mode to give the user full control:
- **Simple Mode**: Provide ONLY the detailed suggested solution. Hide all other contextual details, background, and internal reasoning.
- **Advanced Mode**: Display ALL details, including the detailed suggested solution, hidden background context, technical reasoning, and the full audit breakdown.



# Lexful UX Audit Gate

**Purpose.** Decide whether a Lexful release candidate is safe from a UX standpoint, and produce findings the AI harness can file to Linear with no manual re-entry.

**Where this fits.** This skill is the UX half of Phase 1's testing harness. The functional half (Playwright scripts, bug-logger, severity→Linear mapping) already exists in the Merged POC. This skill supplies the UX judgment layer that plugs in beside it. It runs on Lexful's live UAT app, logged in — not on static screen mockups.

**Full rule detail lives in:** `Lexful_UX_Rulebook_v0.5.md` (five lenses, journey checklists, confirmed personas, **the current severity scale**), `Lexful_Bad_UX_Pattern_Library_v0.6.md` (general bad-UX patterns mapped to Lexful, for the AI exploratory pass), `lexful-ux-checks.yaml` (the same checks as a machine-readable file, the input for the automated audit), and `Lexful_Live_Findings_Log.md` (real hands-on observations as they're gathered, pre-Linear). This SKILL.md is the short, operational version for day-to-day audit runs; those documents are the long version with reasoning, examples, and the running record.

**Known change as of Sept 28 kickoff:** Sherwin confirmed major UX changes shipped the week before kickoff, and he isn't fully caught up either. Treat every past assumption about screens as provisional until re-checked against current UAT.

---

## Audit Inputs

Before running an audit, confirm you have:
1. **UAT login** — standard end-user role, test-only auth path (Stytch: Google, Microsoft, or email-link).
2. **Style guide + Storybook link** — the design authority. `[STATUS: requested, not yet received as of kickoff]`
3. **Design tokens** — from the repo, not invented.
4. **The journey being tested** — search, asset CRUD, or document content editing.
5. **Persona for this run** — Technician (primary, default) or MSP admin (secondary). `[CONFIRM roles with John]`
6. **Open Linear history for this journey** — for baseline and deduplication.

If any of 1–4 is missing, flag it and run a partial audit rather than guessing at rules.

## Audit Procedure

### Step 1 — Task completion pass (do this first, always)
Walk the journey start to finish as the technician persona. Note anywhere the task cannot be completed, resets unexpectedly, or loses data. This pass alone can produce an S1 before anything else is checked — task-blocking beats everything else.

### Step 2 — Five-lens pass
Run in this order, citing a rule ID from the rulebook for every finding. **A finding with no rule ID is invalid — discard it or convert it to a note.**

| Order | Lens | What it catches |
|---|---|---|
| A | Flows & speed | Keyboard reachability, hotkeys, focus, extra steps, unsaved-work protection, destructive-action confirmation |
| B | Clarity & trust | Labels, error messages, confirmations, AI-output transparency, AI approval gates, sensitive-field masking |
| C | Style-guide consistency | Tokens, components vs. Storybook, repeated patterns, icons |
| D | Accessibility | WCAG 2.2 AA contrast, focus indicators, labels, color-independence, modal focus trap, heading order, target size |
| E | IA & navigation | Current-location clarity, nav/heading name match, back/refresh/deep-link state, search relevance, filter persistence |

### Step 2b — AI exploratory pass (pattern matching)
Beyond the 5 cited lenses, let the AI roam the journey freely and check it against `Lexful_Bad_UX_Pattern_Library_v0.6.md` — this catches things no fixed rule ID anticipated (a confusing new modal, an odd empty state, a misleading label). A pattern-library match still needs a pattern ID cited (e.g. `BP-12`), same discipline as a rule ID. This is what makes it "exploratory" rather than purely scripted.

### Step 2c — Self-healing & drift review (run whenever a locator self-heals)
Self-healing keeps scripts alive when the UI shifts, but a script that still passes only proves the *robot* adapted — not that a *technician* wouldn't be confused. Treat every healing event as a UX signal to check, not just a script-maintenance event.

| ID | Rule |
|---|---|
| H1 | Every self-heal (old selector fails, AI finds the element a new way) is logged separately from pass/fail: old locator, new locator, before/after screenshot. |
| H2 | A healing event is never silently accepted — it always appears in the run report for human review, even if the test passed. |
| H3 | Run the healed element through the 5 lenses (Step 2) like any other change — did it move, get renamed, or become less reachable? |
| H4 | If the healed element is a high-repetition action (search, save, primary CTA) or sits on a hotkey path, auto-raise to at least S2 for human review regardless of pass/fail. |
| H5 | If the same element heals more than once across recent runs, flag "unstable UI" even with no rule violation yet — repeated silent change is itself a UX problem. |
| H6 | A healing event can close an existing regression ticket only with human confirmation. The AI cannot mark something "fixed" just because the script passes again. |

**Operating principle:** a self-healed test that still passes tells you the robot adapted. It does not tell you the technician wasn't confused. Every healing event needs a human to ask: *"would a person notice this change, and would they mind?"*

### Step 3 — Severity assignment
Use the rulebook's S1–S4 scale (mirrors the bug-logger's Critical/High/Medium/Low and Linear priority). Apply at most one adjustment step, and always state why:
- Workaround exists → one step down.
- On a high-repetition path (search, save) → one step up.
- Regression vs. previous release → one step up.
- **S1 can never be lowered by the AI pass — a human confirms it.**

### Step 4 — Noise control (before anything reaches Linear)
1. Human review (you) approves every finding until classification is trusted — first few runs, review all of them.
2. Deduplicate against open Linear tickets and prior runs.
3. Group cosmetic/S4 items into one ticket per screen per run, not one ticket each.
4. Low-confidence AI findings go into the run report only, not Linear.
5. Check the "accepted deviations" list (things Lexful said are intentional) before flagging again.

### Step 5 — Write the finding
Every finding needs: type (Functional/UX), journey + step, rule ID, severity + one-line reasoning, expected vs. actual, numbered repro steps, evidence (screenshot/trace), run label, AI confidence.

### Step 6 — Run-level verdict
Score the run against the agreed pass/fail bar. **Per the Sept 28 call, treat this as advisory/informational by default, not a hard release blocker** — Sherwin wants fast signal over gating, and the exact gating rule is still being worked out. Only escalate to "blocking" if Week 1 explicitly sets that bar. Always show the rubric in the report so Lexful can see why a run scored the way it did.

---

### Step 7: Before/After suggestions (optional, after the verdict)
For FAIL findings whose check has `visual_fix: true` in `lexful-ux-checks.yaml`, hand off to the `lexful-ui-before-after` skill (which uses `fluent-ui-design-system`). It captures a Before screenshot of the real UAT screen, builds an After concept mock using shadcn/ui components with Fluent-aligned design, and writes the solution next to both. Rules: do the quick stack check first, maximum 4 pairs per run, After images are concept mocks and never the live product, and every finding in the report gets a plain-language **Solution** line even when no visual is produced.

## Severity Reference (short form, v2: a working UI passes)

| Sev | Meaning | Score | Effect |
|---|---|---|---|
| S0 | Broken: journey cannot be completed, data lost, or crash | -40 | FAIL |
| S1 | A core task cannot be completed by any normal path | -25 | FAIL |
| S2 | Task completes, but a typical technician would be misled or slowed (observed) | -10 | none |
| S3 | Polish or minor inconsistency; non-essential WCAG AA miss | -3 | none |
| O | Observation: works as intended; a design suggestion | 0 | none |

Calibration and the S0/S1 evidence gate are in `lexful-ux-checks.yaml` (`meta.calibration_rules`, `meta.evidence_gate`) and Rulebook section 7b. Never copy wording or ids from sample files.

## Output Format

```
## UX Audit Report — [journey name] — [date] — [run label]
**Persona:** [Technician / MSP admin]
**Build/commit:** [ref]

### Task Completion
PASS / FAIL — [one line]

### Findings
| # | Lens | Rule/Pattern ID | Issue | Severity | Confidence | Evidence |
|---|------|-----------------|-------|----------|------------|----------|

### Healing Events This Run
| # | Element | Old locator | New locator | Lens check result | Verdict (Benign / Regression / Unstable-watch) |
|---|---------|-------------|-------------|--------------------|-------------------------------------------------|

### Filed to Linear
[list of ticket links, or "none this run"]

### Held for Report Only (low confidence / advisory)
[list]

### Verdict
PASS / ADVISORY-FAIL / BLOCKING-FAIL — [one line, tie back to the rubric]
```

## Guardrails
- The AI recommends only — it never edits, deletes, or fixes product data or code.
- UAT + synthetic/demo data only. No production execution (out of scope).
- No tenant data retained beyond what's needed to debug a finding.
- Credentials never appear in prompts, reports, or screenshots.
- A named human (you, initially) signs off — the AI does not self-approve.

## Open Items Blocking a v1.0 of This Skill
Pull these from the rulebook's open-questions list once answered, and bump the version:
1. Style guide / Storybook / token files access.
2. Confirmed hotkey list.
3. Confirmed pass/fail gating rule (advisory vs. blocking) — in progress per Sept 28 call.
4. Supported browsers/window sizes.
5. Accessibility bar confirmation (assuming WCAG 2.2 AA).
6. Known accepted deviations / in-flight redesigns to ignore.
7. Which agent/model actually runs this (Bedrock vs. Claude Code CLI vs. hybrid) — undecided as of kickoff, York IE to recommend. Affects how this skill gets invoked, not the rules themselves.
8. How often self-healing actually fires in practice — H5's "more than once" threshold may need tuning once real data comes in.

## Changelog
- **v0.16.0**: QA ingestion for all three flows (specs, POMs, feature notes in `qa-specs/`; `QA_TRACEABILITY.md` rewritten). Checks file v0.6: 40 checks, `qa_refs` and `qa_note` on 30 and 19 of them, environment notes (WAF, 5-minute session, URL patterns, role inference). Master prompt v2.2 adds rules 13 to 15 and tells the agent to treat QA-expected behavior as at most an Observation.
- **v0.15.0**: QA intake. Added `qa-specs/` (QA files for the three flows), `QA_TRACEABILITY.md`, `qa_refs` on checks, four new Search checks (SRCH-09 to SRCH-12, 29 checks total), and a `qaRefs` field on findings that the PDF shows. Asset CRUD and Document editing wait for QA files.
- **v0.14.0**: Severity v2. Added the Observation tier (O) so working UI passes, calibration rules, and an evidence gate for S0 and S1 (reproduce twice, check your own screenshot, try to disprove) enforced by `make-ticket-pdf.mjs`. Triggered by the first real run, where an unverified S1 was contradicted by its own screenshot and matched the sample data. Master prompt v2.1 tells the agent not to open sample files; schema-only templates added.
- **v0.13.0**: Added `AGENT_007_MASTER_PROMPT.md`, one self-contained prompt that merges all skill instructions (audit, Fluent and shadcn design direction, Before/After, next steps, PDF). The two earlier prompt files moved to `archive/`. `make-ticket-pdf.mjs` now renders Before/After pairs side by side, per-ticket next steps and a run-level next-steps page.
- **v0.12.0**: Output changed from Linear filing to a formatted PDF ticket pack: `playwright-starter/make-ticket-pdf.mjs` builds it from `findings.json` and `scorecard.json` (scores, priorities and labels computed in code, credential redaction, evidence embedded). `sample-output/sample-ticket-pack.pdf` shows the format. The Linear filing script is kept under `playwright-starter/optional-linear/`, unused by default. Agent instructions v1.2.
- **v0.11.0**: Linear filing added: `playwright-starter/linear-file.mjs` (offline dry run, read-only check, duplicate detection, YOR-only allow-list) and a fixed `tickets.json` schema. Agent instructions v1.1 add the run card and the human gate.
- **v0.10.0**: Added `AGENT_INSTRUCTIONS_playwright-audit.md` (full automated run: Playwright on Chromium across the three journeys, Linear-ready tickets with UI/UX labels, six-pillar scoring) and `playwright-starter/` (config and manual-login script).
- **v0.9.0**: Design direction set to shadcn/ui components with Fluent-aligned design. Step 7 and the two design skills updated; `lexful-ux-checks.yaml` v0.3 adds `shadcn_hint`.
- **v0.8.0**: Added Step 7 (Before/After suggestions) and linked the two new skills: `fluent-ui-design-system` and `lexful-ui-before-after`. `lexful-ux-checks.yaml` v0.2 now marks 12 checks with `visual_fix` and a `fluent_hint`.
- **v0.7.0** — Added `lexful-ux-checks.yaml`: 25 checks as structured data (the audit tool's two overlapping one-off-component checks are merged into CRUD-08) (id, rule ref, severity, how to verify, known issues) for the automated audit. Edit the YAML and the docs together so they never drift.
- **v0.5.0** — Logged real confirmed evidence for BP-11/BP-12: a 2-character search returned unexplained, non-matching results. Flagged as contradicting the earlier "no LLM" description of search — needs direct confirmation with Sherwin/John of actual matching logic and searched fields.
- **v0.4.0** — Incorporated QA's 50-case Search test document: rewrote the Search journey checklist in the rulebook, downgraded BP-101 to "confirmed intentional," added confirmed-good-patterns to avoid false positives, extended D5 to drawers/panels (backed by QA's own Escape-key uncertainty). Added Storybook/axe/Chromatic tooling context so the harness doesn't duplicate existing component-level checks.
- **v0.3.0** — Pointed at `Lexful_Live_Findings_Log.md` for real hands-on findings (separate from the general pattern library). No procedural changes — [REDACTED]'s first screenshot pass confirmed BP-20, BP-103, BP-60, and added BP-106 to BP-109 in the pattern library.
- **v0.2.0** — Added Step 2b (pattern-library exploratory pass) and Step 2c (self-healing & drift review, H1–H6). Added a "Healing Events This Run" section to the report format.
- **v0.1.0** — Initial draft from Project Brief + Runbook, adapted from Pave `ux-audit-gate`.
