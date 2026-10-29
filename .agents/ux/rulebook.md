# Lexful UX Rulebook: DRAFT v0.5

**Status:** Draft for Week 1 review. Not signed. Per the AI SDLC Runbook (P4), the QA charter is human-signed and never AI-generated. This draft is the starting point; Sherwin Chu and John Christensen decide what stays.
**Scope:** Lexful UAT only. Journeys: **Search, Asset CRUD, Document content editing**.
**Owner:** Product Experience Designer, York IE. **Lexful counterpart:** John Christensen.
**Marks:** `[CONFIRM]` = needs an answer from Lexful. `[ASSUMED]` = my guess from the brief or public site, not verified.

---

## 1. The bar, in one sentence

> A technician who lives in Lexful up to 10 hours a day, working by hotkeys and muscle memory, should never be slowed down, blocked, or misled by a release.

UX regressions count as much as functional bugs (Project Brief). Speed, keyboard flow and trust in what the screen says come first. Visual polish comes second.

## 2. Who we test as (persona standard) — CONFIRMED Sept 29, replaces earlier guesses

Sherwin confirmed 3 real roles. Update: the walkthrough was demoed as **Admin**, but the primary technician persona is **Support**, not Admin.

| Persona | Real role name | Who | What they can do | Test priority |
|---|---|---|---|---|
| **Technician** (primary) | **Support** | MSP tech, in the tool all day | Search, create, update assets. **No** account admin, no asset-type/user management | Default persona for all 3 journeys |
| **MSP admin** (secondary) | **Admin** | Owner/lead running the MSP | Everything Support can do, plus asset types, users, roles, org setup | Only test admin-only screens (settings, asset-type builder) under this persona |
| **Client / customer** (new — not in v0.1) | **Viewer** | The MSP's own end client, given self-serve access | Read-only: search, browse, and Ask Lex only. No create/edit | `[CONFIRM]` if Client Portal is in Phase 1 scope — likely a future-phase concern, but keep it in mind since it appeared in Lexful's own persona-agent doc |

**Also confirmed:** a technician's normal working view is usually **one specific organization**, not "All Organizations" — Admins are more likely to work at the all-org level. Default your test runs to a single-org view unless the journey specifically needs cross-org (e.g. cross-org relationships, which are supported but less common).

**Org access nuance:** access can be restricted per user or per group, down to specific organizations and even specific asset types blocked. Test at least one restricted-access scenario, not just the wildcard "all organizations" case.

## 3. Sources of truth (Runbook P2-01, P2-04, P2-06) — updated with Sept 29 findings

1. **Lexful's style guide + Storybook** are the design authority — John to share the Storybook link directly. `[STATUS: promised, not yet received]`
2. **Design tokens** (color, type, spacing, radius) are read from the repo, not invented.
3. **HTML/live UAT is the thing tested.** Figma is not the reference. `[CONFIRMED]`
4. **Accessibility standard: WCAG 2.1 AA** (corrected from 2.2 — Lexful's own internal "Design System Consistency Agent" doc names 2.1 AA explicitly, so match their own bar rather than the newer standard).
5. **NEW: Microsoft Fluent UI is the design-system reference**, per Lexful's own internal agent doc ("Microsoft Fluent UI Alignment: Maintains design consistency with M365"). Check components against Fluent UI conventions where Storybook doesn't cover something. **Direction (Oct 13):** Lexful's UI is treated as shadcn/ui components (Radix + Tailwind) with Fluent UI as the design-alignment reference (Storybook shows `data-slot`, `asChild` and Tailwind classes). Authority order: Lexful Storybook and style guide, then Fluent, then shadcn defaults. To confirm with John; see `.agents/skills/design-system/SKILL.md` section 2.
6. **NEW: white-labeling exists as a product concern** ("Brand Guidelines Enforcement... white-label capability preservation" per their own docs). `[CONFIRM]` whether Phase 1's 3 journeys need to check white-label branding, or if that's out of scope for us.
7. **NEW (confirmed from Storybook config files, Oct):** Lexful already runs **axe-core accessibility checks** via `@storybook/addon-a11y`, wired into both Storybook and their Vitest suite. **Important:** `a11y.test` is set to `"todo"`, meaning violations are **surfaced but don't fail CI** — not yet enforced. `[CONFIRM]` with John whether to treat their axe ruleset as our accessibility baseline rather than defining checks from scratch, and whether any historical a11y scan results already exist to reuse.
8. **NEW (confirmed from Storybook config):** Lexful also runs **Chromatic** for visual regression, but this only screenshots **isolated Storybook stories**, not the live running app — it would not catch something like the document-editor indentation bug (section 6, Document editing). This is why journey-level UX/accessibility testing (our job) is not redundant with their existing component-level tooling — it's a different layer.
9. **Methodology note:** screenshots alone can confirm layout and visual hierarchy, but **cannot** confirm real WCAG compliance — semantic HTML, accessible names on icon-only buttons, keyboard focus order, and actual contrast ratios all need live-browser inspection once UAT access lands. Treat screenshot-based accessibility impressions as provisional, not sign-off-ready.

## 4. How the AI audits (order matters)

Run in this order on every journey step: **(1) Can the technician complete the task? (2) Can they do it fast, by keyboard? (3) Is it clear and trustworthy? (4) Is it accessible? (5) Is it consistent with the style guide?** Stop rating cosmetic issues higher than task-blocking ones.

Every finding must cite a rule ID below or a style-guide/Storybook reference. **Uncited findings are invalid** (Runbook P4 rule).

## 5. The rules (five lenses)

Default severity is S1 to S4 (see section 7). Verification: **[S]** scripted Playwright check, **[AI]** AI exploratory judgment, **[H]** human review needed.

### Lens A: Flows & speed (technician-first)

| ID | Rule | Verify | Default sev |
|---|---|---|---|
| A1 | Every journey can be completed start to finish without dead ends or unexplained resets | S | S1 |
| A2 | Core actions (search, save, create, edit) are reachable by keyboard only | S+AI | S2 |
| A3 | Hotkeys that exist keep working after a release (no silent breakage or new conflicts) `[CONFIRM list of hotkeys]` | S | S2 |
| A4 | Focus lands somewhere sensible after every action (opening a modal, saving, closing, search) and is never lost | S+AI | S2 |
| A5 | Common tasks don't gain extra clicks or steps versus the previous release | AI+H | S3 |
| A6 | Loading, empty, error and success states exist for each journey step; none leaves the user guessing | S+AI | S2 |
| A7 | Unsaved work is protected: warning before leaving, or autosave, with a clear signal | S | S1 (data loss) |
| A8 | Destructive actions (delete, overwrite) confirm and say exactly what will happen; undo or rollback where the product promises it | S+AI | S1 or S2 |

### Lens B: Clarity & trust (content and feedback)

| ID | Rule | Verify | Default sev |
|---|---|---|---|
| B1 | Labels and buttons say what they do; same word for the same thing everywhere | AI | S3 |
| B2 | Error messages say what went wrong and what to do next, in plain language | AI | S2 |
| B3 | After any change the user gets clear confirmation that it worked | S+AI | S3 |
| B4 | Anything AI-generated (Ask Lex) shows its sources, and says so when data is missing instead of guessing `[ASSUMED]` from public site claims | AI+H | S2 |
| B5 | AI-proposed changes require explicit user approval before they land `[ASSUMED]` | S+H | S1 |
| B6 | Sensitive fields (passwords, credentials) are masked by default, revealed deliberately, never leaked into URLs, page titles or search results | S+H | S1 |

### Lens C: Consistency with the style guide

| ID | Rule | Verify | Default sev |
|---|---|---|---|
| C1 | Colors, type, spacing and radius come from tokens; no arbitrary values | S | S4 |
| C2 | Components match Storybook (buttons, inputs, tables, modals); no one-off variants | S+AI | S3 |
| C3 | Same pattern for the same job across screens (e.g. every list has the same sort/filter behavior) | AI | S3 |
| C4 | Icons follow one style and size set | AI | S4 |
| C5 | Layout does not break at supported window sizes; no horizontal scroll, clipped or overlapping content `[CONFIRM supported sizes]` | S | S2 |

### Lens D: Accessibility

| ID | Rule | Verify | Default sev |
|---|---|---|---|
| D1 | Text contrast meets WCAG AA (4.5:1 normal, 3:1 large) | S | S3 |
| D2 | Visible focus indicator on every interactive element | S | S2 |
| D3 | Every input has a label; every icon-only button has an accessible name | S | S3 |
| D4 | Nothing relies on color alone (status, errors) | AI | S3 |
| D5 | Modals **and side drawers/panels** (e.g. the asset detail drawer, Ask Lex drawer) trap focus and return it on close; Escape closes | S | S2 |
| D6 | Headings and landmarks are in a sensible order; page titles are meaningful | S | S4 |
| D7 | Target sizes are usable (44px goal; dense desktop tables may be smaller if deliberate) `[CONFIRM]` | S | S4 |

### Lens E: Information architecture & navigation

| ID | Rule | Verify | Default sev |
|---|---|---|---|
| E1 | User always knows where they are (active nav state, breadcrumbs, page title) | S+AI | S3 |
| E2 | Same place, same name: nav labels match page headings | AI | S4 |
| E3 | Back button, refresh and deep links land on the same place, with state preserved | S | S2 |
| E4 | Search: results are relevant and ordered sensibly, matching text is easy to see, and "no results" gives a next step | AI+H | S2 |
| E5 | Filters, tags and sorting persist while the user works, and can be cleared in one action | S+AI | S3 |

## 6. Journey checklists (start here for the first run) — updated with Sept 29 walkthrough detail

**Search.** Updated from QA's 50-case test document (TC-SRCH101–150, Oct). Two distinct mechanisms by design, not a bug — test both, and check that the distinction is discoverable:
- **Global search (header "Search..." / ⌘K):** opens as a **non-destructive overlay popup** on top of the current page — no route change, background stays visible. Empty state shows filter chips (`@Organization`, `#Asset type`, `Passwords`, `Documents`, `/Shortcuts`), an "Ask Lex anything" row, and **GO TO** / **CREATE** shortcut sections. Typing shows live cross-type "MATCHING RECORDS" plus a dynamic "Ask Lex '[query]'" row. Filters combine with AND logic (text + org + asset type together). Confirmed to correctly exclude records the logged-in user can't access (TC-SRCH133) — a good sign for permission-safety, verify this holds under your own test runs too.
- **In-page table search** (e.g. "Search Documents..."): scoped to that one table only, by design (TC-SRCH149). **Rule E4 update:** check this distinction is *discoverable* — a technician glancing at either box should have some cue they're not equivalent, not that the narrower one is a hidden limitation (see BP-101, downgraded from "likely bug" to "confirmed intentional, verify discoverability").
- **Ask Lex (AI):** opens as a right-side drawer, not full-page — carries the typed query in as the first chat message, supports `@` mentions and `/` skills. **Confirmed live bug (Sept 29):** asking about a **read-only organization** let it make tool calls first and fail afterward, instead of checking access and declining immediately (BP-100).
- **Known open item from QA's own test design:** TC-SRCH143 tests Escape-to-close on the search popup and explicitly flags uncertainty about whether Escape is supported at all — direct supporting evidence for rule D5 (drawers/panels needing Escape support). Confirm this specifically once you have UAT access.
- **New open item (Oct 5, real evidence):** a 2-character search ("To") returned 3 results with no visible match to the query text, contradicting the Sept 29 description of search as plain "keyword + semantic, no LLM." `[CONFIRM]` the actual matching logic and which fields are searched beyond the visible name — see BP-11/BP-12 and Live Findings Log #11.
- **Good patterns already confirmed, don't misflag these:** popup/drawer close (X or Escape) discards only the search state, never navigates away or loses page context (TC-SRCH103, TC-SRCH112, TC-SRCH128); switching asset-type/org filters correctly clears stale results from the previous filter (TC-SRCH135); results are case-insensitive and trim whitespace (TC-SRCH138, TC-SRCH139).

Rules: A2, A4, A6, B6, D5, E3, E4, plus BP-100/BP-101.

**Asset CRUD.** Confirmed structure: 4 system asset types (Document, Password, Contact, Location) are locked/uneditable at the field level but extensible with custom fields; custom asset types are fully user-defined. Confirmed capabilities to test: relationships (including cross-organization links), file attachments, visibility restriction (default: org-wide, can restrict to users/groups), **revision history with restore**, **archive as soft-delete** (recently moved into the filter panel — watch for control-relocation confusion), bulk archive/duplicate, tags (tree-based parent-child — **John confirmed past complaints here**, unclear if fully resolved by the new UI, treat as a regression-risk area not a solved one). Rules: A1, A7, A8, B2, B3, C2, E5, plus new BP-102, BP-103.

**Document content editing.** Confirmed: TipTap WYSIWYG editor, supports images (stored as attachments, not embedded base64), embeddable iframe URLs, HTML/Markdown mode switching, nested lists. **Confirmed live bug, demonstrated by Sherwin himself:** saving content shifted nested-list indentation visibly. Both Sherwin and Cailin independently flagged this control as the highest regression risk of the three journeys, specifically because of open-ended formatting and copy-paste/drag-drop variability. Rules: A2, A7, B5, D2, D5, plus new BP-30 (already existed) reinforced, and BP-104.

## 7. Severity scale — SUPERSEDED Oct 5, now matches engineering's QA bar

**This replaces the old S1–S4 scale below.** On Oct 5, Abhijit proposed a QA pass/fail bar to Sherwin, who agreed in principle. This is now the **single shared severity scale** across functional and UX findings — using our own separate scale would mean the same word ("S1") means different things to different people on the same project, which defeats the point of a shared QA gate.

| Severity | Engineering's definition | What it means for a UX finding | Result |
|---|---|---|---|
| **S0** | Feature completely broken, no result possible at all | A crash, a blank/dead screen, or a journey step that cannot be completed by any path | **Fail / no-go** |
| **S1** | Feature is accessible, but the user's actual goal can't be fulfilled | Technician can open the screen/feature but cannot complete their real task — no workaround exists | **Fail / no-go** |
| **S2** | UX or cosmetic degradation; doesn't stop the journey | Friction, confusion, inconsistency, or a broken-looking element — but the technician can still finish the task, possibly with a workaround | **Pass** (logged, not blocking) |
| **S3** | Minor shifts, small visual changes | Cosmetic-only, barely noticeable | **Pass** (logged, not blocking) |

**Adjustment rules (one step max, always explained in the finding):**
- A workaround exists → consider dropping from S1 to S2.
- Problem sits on a high-repetition step (search, save) → consider raising one level.
- Regression from the previous release → consider raising one level.
- **S0 and S1 can never be downgraded by the AI alone. A human confirms both.**

**Migration note — mapping from the old S1–S4 UX scale** (used in earlier entries throughout this rulebook, the pattern library, and the findings log — not yet individually rewritten):

| Old UX severity | Maps to | Notes |
|---|---|---|
| Old S1 (blocked/data loss, no workaround) | **New S0** if a total block/crash, otherwise **New S1** | Most old S1 findings become new S1 unless genuinely nothing works at all |
| Old S2 (slowed a lot, or key path broken with workaround) | **New S1** if no real workaround, otherwise **New S2** | Check whether a workaround actually exists |
| Old S3 (noticeable friction, task still smooth) | **New S2** | |
| Old S4 (cosmetic/minor polish) | **New S3** | |

The pattern library entries that name a severity now use this S0–S3 scale. Read any remaining "S1–S4" label elsewhere in this kit through the table above.

`[RESOLVED Oct 5]` "Severity-1" in the SOW maps to the new **S0 or S1** depending on whether it's a total block or a goal-blocking issue with the feature still reachable.

## 7b. Severity v2 (Oct 16): a working UI passes

Based on the first real run, where a design-opinion-heavy rating and one unverified S1 turned a mostly healthy platform into a FAIL.

| Level | Meaning | Score | Verdict effect |
|---|---|---|---|
| **S0** | Broken: the journey cannot be completed, data is lost or corrupted, or the page crashes | -40 | FAIL |
| **S1** | A core task cannot be completed by any normal path (no workaround) | -25 | FAIL |
| **S2** | The task completes, but a typical technician would be misled or slowed (observed, not assumed) | -10 | none |
| **S3** | Polish or a minor inconsistency, or a WCAG AA miss on a non-essential element | -3 | none |
| **O** | Observation: works as intended and is understandable; a design suggestion | 0 | none |

**Calibration rules.** (1) If it works, is understandable and meets WCAG 2.1 AA, it passes: no ticket, or an Observation. (2) Rate what you observed, not what the UI should ideally do. (3) A visible outcome counts as feedback: a missing toast is S3 when the result is plainly visible, S2 only when it is not. (4) Intended-by-design behavior is not a finding. (5) A WCAG A or AA failure is at least S3, and S2 only if it blocks keyboard or screen-reader use of a core task. (6) S2 needs a written reason a typical technician would be misled or slowed.

**Evidence gate for S0 and S1.** Reproduced at least twice; your own screenshot shows the problem and not the opposite; you tried to disprove it. If your evidence contradicts your claim, withdraw or downgrade the finding. The PDF generator refuses an S0 or S1 without this record. Never copy wording or ids from any sample file.

## 8. Pass/fail bar (confirmed Oct 5, in principle — pending Sherwin's full review)

- **Bar:** no **S0** or **S1** findings → **pass**. Any S0 or S1 → **fail/no-go**. S2 and S3 are logged but don't block.
- This replaces the earlier "no severity-1 findings" wording from the SOW with the more precise S0/S1 split agreed on the call.
- **Trigger mechanism is still unresolved as of Oct 5** — Sherwin pushed back on ticket-based triggering (Lexful uses trunk-based dev with no per-ticket branches) and leans toward testing *every build* that reaches UAT rather than waiting for a ticket-status change. Don't assume the ticket-triggered model is final.
- The run report must still show the score and why (which rules fired, how severity was set), so Lexful can see how the verdict was reached — this part is unchanged.

## 9. What every finding must contain

Type (**Functional** or **UX**), journey and step, rule ID, severity with reasoning, expected vs actual, numbered reproduction steps, evidence (screenshot or trace), run label, and AI confidence (high/medium/low).

## 10. Keeping the noise down

Noisy Linear tickets in the first weeks cost credibility (Brief). So:
1. **Human review first.** York IE's QA/UX reviewer approves every finding until classification is trusted.
2. **Group cosmetic S4 issues** into one ticket per run and screen.
3. **Deduplicate** against open Linear issues and earlier runs before filing.
4. **Low-confidence findings** go to the report only, not to Linear.
5. **Accepted-deviation list:** anything Lexful says "this is intended" is recorded and not flagged again.
6. **Baseline first:** the first full run sets the baseline from Linear history. Only *new* or *worse* items are called regressions.

## 11. Guardrails (from the Runbook and Brief)

- The AI **recommends only.** It does not fix, delete or change product data.
- UAT only, synthetic/demo data only. No tenant data kept beyond what a finding needs.
- Read-only by default; write access only where agreed (file to Linear).
- Credentials never appear in prompts, reports or screenshots.
- A named human signs off. The AI does not.

## 12. Open questions for John and Sherwin (batch into one message)

1. Which hotkeys exist today, and which are most used? (A3)
2. Can we get the style guide, token files and the Storybook link? (Section 3)
3. Is WCAG 2.2 AA the right accessibility bar? (P2-03)
4. Should UX S2 findings ever block a release, or only S1? (P2-05)
5. Supported browsers and window sizes? (C5)
6. Are there known accepted deviations or ongoing redesigns we should ignore? (Section 10)
7. Which roles/personas should each journey run as? (Section 2)
8. Which past Linear bugs (from design partners) best show what "bad UX" looks like for you? (calibration)

## 13. Change log

| Version | Date | Change |
|---|---|---|
| v0.1 | 2026-09-28 | First draft from Runbook, Project Brief, and public site. Unsigned. |
| v0.2 | 2026-09-29 | Updated from live product walkthrough (Sherwin) and Lexful's own internal UX-agent doc: real personas (Admin/Support/Viewer), corrected accessibility bar (WCAG 2.1 AA), added Fluent UI + white-label as design-system inputs, confirmed journey-specific behavior (search scoping, Ask Lex, archive-as-soft-delete, tags risk area, editor indentation bug). Still unsigned.
| v0.3 | 2026-10-05 | Rewrote the Search journey checklist using QA's 50-case test document (confirmed popup/drawer behavior, GO TO/CREATE shortcuts, filter combinations, good patterns to avoid misflagging). Downgraded BP-101 from likely-bug to confirmed-intentional (verify discoverability only). Extended D5 to cover drawers/panels, backed by QA's own flagged uncertainty about Escape support. Added Storybook/Chromatic/axe tooling context (items 7–9 in Section 3) and a methodology note on screenshot vs. live-inspection limits. Still unsigned.
| v0.4 | 2026-10-05 | Added a real confirmed-bug open item to the Search checklist: a 2-character query returned results with no visible match to the query text, contradicting the earlier "keyword + semantic, no LLM" description. Flagged for direct confirmation with Sherwin/John. Still unsigned.
| v0.5 | 2026-10-06 | **Superseded the UX severity scale.** Adopted engineering's S0–S3 QA bar (confirmed on the Oct 5 call, Sherwin agreed in principle) as the single shared scale, replacing the old independent S1–S4 scale. Added an old→new mapping table since earlier entries across all files still use the old labels. Pass/fail bar updated to "no S0 or S1 = pass." Noted the QA trigger mechanism (ticket-based vs. per-build) is still unresolved as of Oct 5.
| v0.6 | 2026-10-16 | Added Severity v2 (section 7b): Observation tier (O), calibration rules so working UI passes, and the evidence gate for S0 and S1. Triggered by the first real run (one S1 contradicted by its own screenshot). |
| v0.7 | 2026-10-22 | QA ingestion: QA's specs and findings for Search, Asset CRUD and Document editing added under `qa-specs/` and summarized in `.agents/ux/traceability.md`. Behavior QA tests as expected is at most an Observation. 40 checks. |
