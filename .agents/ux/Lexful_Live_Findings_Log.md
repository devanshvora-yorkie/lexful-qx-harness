# Lexful Live Findings Log

**Purpose.** This is where real, hands-on observations go as you audit the actual platform — kept separate from `Lexful_Bad_UX_Pattern_Library_v0.3.md` (which stays general/reusable) and `Lexful_UX_Rulebook_v0.2.md` (which stays rule-based). Each entry here is a candidate for an eventual Linear ticket once the AI harness is live, or for your own notes to John/Sherwin in the meantime.

**Format:** one entry per finding, using the same fields the skill file requires for a Linear ticket — so there's no rework later.

**⚠️ Severity scale superseded (Oct 6):** entries below (#1–9, #11) use the old S1–S4 UX severity scale. As of Oct 5, the project uses engineering's shared **S0–S3** scale (see `Lexful_UX_Rulebook_v0.5.md` §7 for the full mapping). Convert before filing any of these to Linear for real.

---

## How to log a new finding

```
### [#] [Short title]
**Date:** 
**Source:** [Screenshot / live walkthrough / meeting]
**Journey:** [Search / Asset CRUD / Document editing / Other]
**Pattern/Rule ID:** [BP-## or rulebook rule ID, or "ungrouped — candidate for new pattern"]
**Severity:** [S1–S4, with one-line reasoning]
**Expected:** 
**Actual:** 
**Evidence:** [image reference]
**Status:** [Open / Needs confirmation from John-Sherwin / Resolved / Not a bug — intended behavior]
```

---

## Log

### 1. Mandatory fields validated one at a time
**Date:** 2026-10-01
**Source:** Screenshot (Application asset creation)
**Journey:** Asset CRUD
**Pattern/Rule ID:** BP-20 (validate too late)
**Severity:** S3 — friction, not blocking; workaround is trial-and-error
**Expected:** All required-field errors shown together after one submit attempt
**Actual:** Entered name only, hit Create — one missing-field error shown; after fixing it, a second error appeared
**Evidence:** Asset creation form screenshots
**Status:** Open — candidate for AI harness check once auth/UAT access lands

### 2. No toast or confirmation after actions
**Date:** 2026-10-01
**Source:** Screenshots (create, save, link actions)
**Journey:** Asset CRUD, Document editing
**Pattern/Rule ID:** BP-108 (missing toast entirely) / rulebook rule B3
**Severity:** S2 — user can't confirm an action succeeded
**Expected:** Visible confirmation (toast or inline) after create/save/link
**Actual:** No toast observed in any of the reviewed screenshots
**Evidence:** Images 1, 2, 4
**Status:** Needs confirmation — check a few more actions before treating as systemic

### 3. Assets home empty state has no inline CTA
**Date:** 2026-10-01
**Source:** Screenshot comparison (Assets home vs. Documents empty state)
**Journey:** Other (navigation/onboarding)
**Pattern/Rule ID:** BP-106
**Severity:** S3 — inconsistency, not blocking
**Expected:** Same "+ Create record"-style CTA as the Documents empty state
**Actual:** Assets home shows "No assets yet" with only the top-right "+New" button
**Evidence:** Image 3 (Documents, has CTA) vs. Image 6 (Assets, no CTA)
**Status:** Open

### 4. Edit button style inconsistent with rest of UI
**Date:** 2026-10-01
**Source:** Screenshot, document edit view
**Journey:** Document editing
**Pattern/Rule ID:** BP-60 (one-off component)
**Severity:** S4 — cosmetic, but a real style-guide deviation
**Expected:** Edit button matches Storybook button styles used elsewhere
**Actual:** Visually distinct styling, unclear if intentional for emphasis
**Evidence:** Document view screenshot
**Status:** Needs confirmation from John — may be deliberate emphasis styling

### 5. Possible markdown syntax leaking into rendered document
**Date:** 2026-10-01
**Source:** Screenshot, test document content
**Journey:** Document editing
**Pattern/Rule ID:** BP-109 (unconfirmed)
**Severity:** S3 pending confirmation
**Expected:** `==text==` renders as highlighted text, not literal characters
**Actual:** Literal `==This is the test document!==` shown unstyled
**Evidence:** Image 1
**Status:** Needs confirmation — may be test content typed without expecting the syntax to render; check with John before logging as a real bug

### 6. No search guidance on empty or unclear query
**Date:** 2026-10-01
**Source:** Screenshot, asset search/filter panel
**Journey:** Search
**Pattern/Rule ID:** BP-107
**Severity:** S3
**Expected:** Placeholder examples, recent searches, or a scoped type list with its own search
**Actual:** Open-ended "Add a name or another filter..." with a 50+ item unfiltered type list and "No matches yet"
**Evidence:** Image 5
**Status:** Open

### 8. Escape-key support on search popup uncertain (flagged by QA itself)
**Date:** 2026-10-05
**Source:** QA test case document (TC-SRCH143, Search_testcases.pdf)
**Journey:** Search
**Pattern/Rule ID:** Rulebook rule D5 (extended to drawers/panels)
**Severity:** S2 pending confirmation — keyboard-only flow is a core technician requirement (rule A2)
**Expected:** Pressing Escape closes the search popup, per D5
**Actual:** QA's own test case notes uncertainty: "If Escape is not supported... note that as a gap" — not yet executed
**Evidence:** Search_testcases.pdf, TC-SRCH143
**Status:** Needs execution — run this specific test case once UAT access lands, high priority given it's self-flagged by QA

### 9. Search-scope distinction confirmed intentional (not a defect — closing an earlier open item)
**Date:** 2026-10-05
**Source:** QA test case document (TC-SRCH149)
**Journey:** Search
**Pattern/Rule ID:** BP-101 (downgraded)
**Severity:** N/A — not a bug, discoverability only
**Expected:** N/A
**Actual:** Global header search (cross-type) and in-page table search (scoped) are confirmed as deliberately separate by QA's own test design
**Evidence:** Search_testcases.pdf, TC-SRCH149
**Status:** Resolved — closes the open question from the Sept 29 walkthrough; only remaining check is whether the UI visually distinguishes the two

### 11. Search returns results with no visible match to the query
**Date:** 2026-10-05
**Source:** Screenshot, live search for "To"
**Journey:** Search
**Pattern/Rule ID:** BP-11 (irrelevant ranking) + BP-12 (no match highlighting) — first real evidence for both
**Severity:** S2 — undermines trust in the primary journey; workaround exists (longer/more specific queries), so not S1
**Expected:** Results should visibly contain the query term, or the UI should show *why* a result matched (e.g. highlighted field)
**Actual:** Searching "To" in Commodo Ipsum Dental LLC returned "CID Excepteur Application Admin," "CID Ipsum Registrar," and "CID Laboris Acce" — none contain "to" as consecutive letters in the visible name. Matching likely comes from a hidden field (description, tags, username) or fuzzy/typo-tolerant logic, but nothing in the UI explains it.
**Evidence:** Screenshot, Oct 5
**Status:** Open — also raises a question against the Sept 29 description of search as plain "keyword + semantic, no LLM"; needs direct confirmation of actual matching logic and which fields are searched
**Follow-up:** Short queries (1–3 characters) deserve extra scrutiny in future runs — likely where fuzzy matching produces the most noise

### 12. Severity scale reconciled with engineering (Oct 5 meeting)
**Date:** 2026-10-05
**Source:** Weekly sync + harness demo transcript
**Journey:** N/A — process/methodology
**Pattern/Rule ID:** N/A
**Severity:** N/A
**Status:** Resolved — rulebook §7 rewritten to adopt engineering's S0–S3 scale as the single shared standard. Old S1–S4 labels throughout this kit still need individual re-review; use the mapping table in the meantime.
**Other notes from this meeting:**
- Confirmed: the 6-agent harness pipeline currently has **no UX/visual checking step** — Devansh named this directly as the gap "[REDACTED] is already exploring." This is the designer's slot to define, not yet built.
- Confirmed: each run is scoped to a ticket/PR's context, not the whole platform. Full multi-journey regression only runs at the production-readiness gate. This likely means our UX checks should also run in a "scoped to what changed" mode, not a full audit every time — worth deciding before proposing where UX plugs into the pipeline.
- QA trigger mechanism (ticket-based vs. continuous per-build) still unresolved — Sherwin pushed back on ticket-based triggering given trunk-based dev with no per-ticket branches.
- Screenshots and screen-recording video are already supported as evidence by the harness — aligns with rulebook §9 evidence requirements.
- Team is using Gemini (not Claude/Bedrock) for test-case generation in the current prototype — model/infra decision still open.
- Next sync moved to Tuesday Oct 13 (Oct 12 is a Canadian holiday).

### 10. (Open design question, not logged as a defect) Floating bulk-action bar vs. sticky column
**Date:** 2026-10-01
**Source:** Your own design observation across multiple screenshots
**Journey:** Asset CRUD (table views)
**Pattern/Rule ID:** Not codified — see pattern library Section M note
**Severity:** N/A — design preference, not a confirmed usability failure
**Status:** Raise as a question to John rather than a bug; floating action bars may be an intentional style-guide choice

### 12. First real audit run (Oct 16): re-checked against QA material
**Date:** 2026-10-22
**Source:** ticket-pack.pdf (run 20261016-1519) compared with QA specs
**Result:** CRUD-02-001 (S1 no unsaved warning) withdrawn: the app has staged edits with Save / Discard / Cancel and the run's own screenshot shows a "Discard unsaved changes?" dialog. CRUD-01-001 (Create disabled) is expected per QA, so S3 or Observation (missing required markers). DOC-04-001 (highlight) likely expected: Highlight exists only in HTML mode (TC-DOC-007); retest in both modes. SRCH-04-001 is an Observation and its screenshot was a 404 page from a guessed URL. CRUD-06-001 stays S3 pending the toast library. SRCH-02-001 and A11Y-01-001 stand. Role "Support" was not verified (Administration menu visible).
**Status:** Recorded. See QA_TRACEABILITY.md section 6.
