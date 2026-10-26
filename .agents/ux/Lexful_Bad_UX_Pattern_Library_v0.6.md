# Lexful Bad UX Pattern Library: DRAFT v0.6

**Purpose.** A catalog of well-known bad-UX patterns, each translated into what it would look like *specifically inside Lexful*. This is what the AI checks against during the free-roaming exploratory pass (Step 2b in the skill file), on top of the 5 cited lenses in the main rulebook.

**How this differs from the rulebook:** the rulebook (`Lexful_UX_Rulebook_v0.1.md`) has specific rules (A1, B4, D2...) written for Lexful's 3 named journeys. This library is broader — general UX failure patterns that could show up **anywhere** in the product, used so the AI isn't limited to only what we already thought to write a rule for.

**How to use a pattern in a finding:** cite it as `BP-##`, same discipline as a rule ID — no uncited findings. If a real issue doesn't match any pattern here, write it up anyway and flag it as "ungrouped" so we can add a pattern next revision.

**Marks:** `[ASSUMED]` = guessed from public info/brief, needs confirmation. `[CONFIRM]` = direct question for John/Sherwin.

**⚠️ Severity scale superseded (Oct 6):** every "S1–S4" severity below uses the **old** UX-only scale. As of Oct 5, the project uses engineering's shared **S0–S3** scale instead (see `Lexful_UX_Rulebook_v0.5.md`, Section 7, which has the full old→new mapping table). Short version: old S1→new S0 or S1, old S2→new S1 or S2, old S3→new S2, old S4→new S3. Entries below have not yet been individually re-labeled — convert via the table before citing a severity from this document in a real finding.

---

## A. Navigation & orientation

| ID | Pattern | Generic problem | What it looks like in Lexful |
|---|---|---|---|
| BP-01 | **Lost in the app** | User can't tell where they are | No active state in the sidebar/nav; page title doesn't match the section |
| BP-02 | **Dead-end screen** | No way forward or back except the browser button | A detail view (asset, document) with no visible way back to the list |
| BP-03 | **Breadcrumb mismatch** | Breadcrumb or nav label doesn't match the actual page heading | E.g. sidebar says "Assets," page heading says "Devices" |
| BP-04 | **Inconsistent back behavior** | Back sometimes returns to the list, sometimes to the dashboard, unpredictably | Especially after opening an asset from search results vs. from the asset list |
| BP-05 | **Buried critical action** | An action technicians need often is nested 3+ clicks deep | E.g. "reset tenant view" or a commonly used filter hidden in a menu |

## B. Search-specific (Lexful's #1 named journey)

| ID | Pattern | Generic problem | Lexful manifestation |
|---|---|---|---|
| BP-10 | **Silent zero results** | "No results" with no next step | Search returns nothing, no suggestion to check spelling, filters, or tenant scope |
| BP-11 | **Irrelevant ranking** | Top results don't match obvious intent | Exact asset-name match buried below partial matches. **Confirmed real (Oct 5):** searching "To" returned 3 results, none containing "to" as consecutive letters in the visible name — likely matching a hidden field or over-eager fuzzy logic. Especially risky on short (1–3 char) queries. |
| BP-12 | **No match highlighting** | User can't see why a result matched | Search term not visibly highlighted in the result list. **Confirmed alongside BP-11 (Oct 5):** same "To" search gave no indication of which field matched, leaving the user unable to judge if a result is relevant or noise. |
| BP-13 | **Lost search state on return** | Going back from a result clears the search | Technician re-types the same query after opening then returning from a result |
| BP-14 | **Cross-tenant leakage or ambiguity** | Results don't make tenant scope obvious | Given multi-tenant architecture, a result doesn't show which client/tenant it belongs to `[CONFIRM this is even architecturally possible — likely prevented at the data layer, but the UI should still be unambiguous]` |
| BP-15 | **Slow perceived search** | No feedback while searching, feels frozen | No loading indicator between keystroke and results appearing |

## C. Forms & data entry (Asset CRUD)

| ID | Pattern | Generic problem | Lexful manifestation |
|---|---|---|---|
| BP-20 | **Validate too late** | Errors only appear after full-form submit | Required asset fields not flagged until Save is clicked. **Confirmed real (Oct 1):** creating an Application asset with only the name filled showed one missing-field error, then another only after fixing the first — errors surface one at a time instead of all at once. |
| BP-21 | **Vague validation message** | "Invalid input" with no specifics | Doesn't say which field or what format is expected |
| BP-22 | **Silent data loss** | Navigating away loses unsaved edits with no warning | Editing an asset, clicking a nav link, losing changes |
| BP-23 | **No optimistic feedback** | Save button gives no indication anything happened | Button click with no loading/success/failure state |
| BP-24 | **Duplicate creation allowed silently** | Same asset can be created twice with no warning | No duplicate-name check on create |
| BP-25 | **Destructive action too easy** | Delete fires on a single click, no confirmation | Deleting an asset or document with no "are you sure," or confirmation doesn't say what's actually being deleted |
| BP-26 | **Form state lost on error** | A failed submit wipes the fields the user filled in | Server-side validation error clears the form instead of preserving input |

## D. Document editing

| ID | Pattern | Generic problem | Lexful manifestation |
|---|---|---|---|
| BP-30 | **Ambiguous save state** | User can't tell if their edit is saved | No autosave indicator, or indicator is easy to miss |
| BP-31 | **Editor lag** | Typing feels delayed under normal use | Noticeable input lag in the document editor |
| BP-32 | **Formatting toolbar keyboard-inaccessible** | Can't format without a mouse | Bold/italic/list controls have no keyboard shortcut or are unreachable by Tab |
| BP-33 | **Conflicting edits unclear** | Two people editing, no indication of conflict | No warning if another tech is editing/edited the same doc `[CONFIRM if multi-editor is even in scope]` |
| BP-34 | **AI-generated content unlabeled** | Can't tell what's AI-written vs. human-written | If Lexful's AI drafts or suggests document content `[ASSUMED feature]`, it's not visually distinguished |

## E. AI feature trust (Bedrock-powered features)

| ID | Pattern | Generic problem | Lexful manifestation |
|---|---|---|---|
| BP-40 | **Unlabeled AI guess** | AI answer presented as fact with no confidence/sourcing | "Ask Lex" or similar answers a question without showing where the info came from |
| BP-41 | **Silent AI action** | AI changes something without explicit approval | An AI suggestion applies to a document or asset without a clear approve/reject step |
| BP-42 | **No fallback on AI failure** | AI feature fails with no graceful message | Timeout or error from Bedrock shows a raw error or blank state instead of a plain-language message |
| BP-43 | **Overconfident hallucination risk** | AI states something with no way to verify | No link back to the source document/asset the AI's answer is based on |

## F. Feedback & system status

| ID | Pattern | Generic problem | Lexful manifestation |
|---|---|---|---|
| BP-50 | **Missing loading state** | Blank screen while something loads, no spinner | Any journey step with a network call and no visible loading indicator |
| BP-51 | **Missing empty state** | Blank list with no explanation | New tenant or filtered view shows nothing with no "no assets yet, add one" message |
| BP-52 | **Generic error page** | Any failure shows the same unhelpful message | 404/500-style catch-all instead of a contextual message |
| BP-53 | **Toast/notification disappears too fast** | Important confirmation flashes and is gone | Save-success message vanishes before a fast-moving technician reads it |
| BP-54 | **No indication of background process** | Long operations (import, bulk edit) give no progress | Bulk asset update or import with no progress bar or completion signal |

## G. Consistency & style-guide drift

| ID | Pattern | Generic problem | Lexful manifestation |
|---|---|---|---|
| BP-60 | **One-off component** | A screen invents its own button/input style instead of using the design system | Any control that doesn't match Storybook |
| BP-61 | **Inconsistent terminology** | Same concept called different names in different places | "Asset" vs. "Device" vs. "Item" used interchangeably `[CONFIRM canonical term]` |
| BP-62 | **Icon meaning drift** | Same icon used for different actions in different places | E.g. a pencil icon meaning "edit" in one place and "view details" in another |
| BP-63 | **Inconsistent list/table behavior** | Sorting, filtering, pagination behave differently screen to screen | Asset list sorts differently than document list |

## H. Accessibility (WCAG 2.1 AA — confirmed from Lexful's own internal doc)

| ID | Pattern | Generic problem | Lexful manifestation |
|---|---|---|---|
| BP-70 | **Color-only status** | Status shown only by color (red/green dot) | No text/icon label alongside a colored status indicator |
| BP-71 | **Keyboard trap** | Focus gets stuck in a modal or widget | Can't Tab or Escape out of a dialog |
| BP-72 | **Missing focus indicator** | No visible outline when tabbing through | Custom-styled buttons/inputs with focus outline removed and not replaced |
| BP-73 | **Unlabeled icon-only control** | Screen-reader users can't tell what a button does | Icon-only buttons (delete, edit, more-options) with no accessible name |
| BP-74 | **Low contrast text** | Text fails WCAG AA contrast | Especially secondary/muted text on light backgrounds |

## I. Performance perception (matters more for 10-hour/day users)

| ID | Pattern | Generic problem | Lexful manifestation |
|---|---|---|---|
| BP-80 | **Janky scroll/render** | Visible stutter in lists or tables | Long asset lists or search results rendering roughly |
| BP-81 | **Blocking UI during background work** | Whole screen locks for a non-critical operation | UI freezes during autosave or background sync |
| BP-82 | **Repeated unnecessary reloads** | Full page reload where a partial update would do | Navigating within the same section triggers a full reload |

## J. Trust, safety & data handling

| ID | Pattern | Generic problem | Lexful manifestation |
|---|---|---|---|
| BP-90 | **Sensitive data exposed by default** | Passwords/credentials visible without deliberate action | Credential fields shown in plaintext rather than masked-by-default |
| BP-91 | **Sensitive data in URL or title** | Leaks into browser history, page title, or logs | A password or token appearing in a URL query param or tab title |
| BP-92 | **No audit trail for destructive actions** | Can't tell who deleted/changed something | No visible "last edited by / deleted by" trail on assets or docs `[CONFIRM if this exists already]` |

---

## K. Confirmed from Lexful walkthrough (Sept 29) — real, not hypothetical

These are not general heuristics guessed at — they were observed live on the call or named directly by Sherwin/John. Treat them as higher-confidence than the rest of this library.

| ID | Pattern | What happened | Why it's bad | Severity guidance |
|---|---|---|---|---|
| BP-100 | **AI acts before checking access** | Asking Ask Lex a question about a **read-only** organization let it make tool calls first, then fail — instead of checking permission and declining immediately. Sherwin named this himself as a needed UX fix. | Wastes the user's time and the AI call itself; makes the failure feel random rather than expected | S2 default — check access/capability *before* invoking the agent harness, not after |
| BP-101 | **Search-scope distinction needs to be discoverable** (downgraded Oct 5) | **Confirmed intentional, not a bug:** QA's own test document (TC-SRCH149) confirms the global header search and the in-page table search are *by design* two separate mechanisms — global is cross-type, in-page is scoped to that one table. The remaining question is only whether a technician can tell them apart at a glance. | A user who doesn't realize two search boxes behave differently may trust the narrower one as if it were global | S3 — not "fix the scope," just verify some visual/textual cue distinguishes the two (e.g. placeholder text, icon, or position) so the difference isn't a hidden surprise |
| BP-102 | **Irreversible setting with no warning** | Marking a custom field as the asset's "name" field (the record-name designation) **cannot be unset** — confirmed by John live, and even Sherwin was confused by his own product's behavior in the moment. | A one-way door with no confirmation dialog or warning before commit | S2 — flag any irreversible action that doesn't warn the user first |
| BP-103 | **Control relocated without a trace** | The "include archived" toggle recently moved under Filters; John had to point this out mid-call because even the team wasn't sure where it currently lived. **Confirmed a second time (Oct 1):** this is the same failure mode Sherwin hit live when a recent design change confused his own navigation — not a one-off, a recurring gap. | If the product team loses track of a moved control, technicians relying on muscle memory definitely will | S3 — when a control's location changes release over release, treat it as a UX regression even if the feature itself still works. **Recommend to Lexful:** a lightweight in-app "what changed" note on design updates, so technicians aren't the ones discovering moved controls mid-task. |
| BP-104 | **Formatting drift on save (editor)** | Saving nested-list content in the TipTap document editor visibly shifted indentation, demonstrated live by Sherwin. Both Sherwin and Cailin flagged the editor as the highest-regression-risk control of the three journeys. | What-you-see is not what-you-get after save — breaks trust in the editor for structured content | S2, raise to S1 if content meaning changes (not just visual spacing) |
| BP-105 (watch, not yet confirmed fixed) | **Tag hierarchy instability** | John confirmed past complaints about the tree-based parent-child tag structure; unclear if resolved by recent UI changes. | Don't assume fixed just because the UI looks new | Treat any tag-related finding as a named regression-risk area, test explicitly rather than incidentally |

## L. Confirmed product facts (context, not bugs — use to avoid false positives)

- **Archive = soft delete.** Archived assets stay in the DB and are restorable. Do **not** flag "data appears gone" as a bug if it's just archived and filterable back in — check the archive filter before reporting data loss.
- **Read-only organizations** (licensing-churned clients) intentionally block create/edit and Ask Lex, but still allow search. A blocked create/edit action on a read-only org is expected behavior, not a bug — unless the UI fails to explain why (see BP-100/BP-101 pattern of unclear messaging).
- **Core asset types** (Document, Password, Contact, Location) have locked system-defined fields by design — this is intentional, not a bug, though custom fields can still be added.
- **No asset-type templates exist yet** (confirmed absent when asked) — this is a known gap, not a defect to report.
- **Personas confirmed:** Admin (full control), Support (default technician — search/create/update only), Viewer (read-only client/customer). Default your test runs to Support unless testing an admin-only screen.
- **Search is confirmed well-behaved in several ways** (from QA's 50-case test document, Oct): closing the search popup or Ask Lex drawer (X or Escape) discards only the search state and never navigates away or loses page context (TC-SRCH103, TC-SRCH112, TC-SRCH128); switching asset-type/org filters correctly clears the previous filter's stale results (TC-SRCH135); matching is case-insensitive and trims leading/trailing whitespace (TC-SRCH138, TC-SRCH139); records the logged-in user can't access are correctly excluded from results (TC-SRCH133). **Don't flag any of these as issues** if your own run confirms the same behavior — they're intended and already well-tested.

## M. Observed directly in platform screenshots (Oct 1 — [REDACTED]'s own audit)

These come from your first hands-on pass creating an asset, a document, and linking them. Higher confidence than general heuristics since they're seen in the live UI.

| ID | Pattern | What was observed | Why it's bad | Severity guidance |
|---|---|---|---|---|
| BP-106 | **Inconsistent empty-state engagement** | The Documents empty state shows "No documents yet" with a clear **"+ Create record"** button (image 3). The global Assets empty state shows "No assets yet" with **no equivalent inline call-to-action** — only the top-right "+New" button, easy to miss on first login (image 6). | A first-time or lost user lands on a blank screen with no obvious next step, inconsistent with how Documents already solves this | S3 — give every empty state the same inline CTA pattern, not just some |
| BP-107 | **No guidance on what to search** | Typing into search or opening the asset-type filter (image 5) shows no example queries, no recent searches, and a 50+ item type list with no search-within-search hint. Result: "No matches yet" with no suggestion of what would match. | New or infrequent users don't know the system's vocabulary (asset type names, searchable fields) and give up rather than refine | S3 — add placeholder examples ("Try: VPN password, client contact...") or a short list of recently viewed/common types |
| BP-108 | **Missing toast/confirmation entirely** | No toast or inline confirmation appears after actions (create, save, link) in the screenshots reviewed so far. This is stronger than BP-53 (toast disappears too fast) — here there's no toast at all. | User can't be sure an action succeeded, especially on slower connections or quick successive actions | S2 — upgrade from BP-53's S3 when confirmation is fully absent, not just brief. Check against rulebook rule B3 directly. |
| BP-109 | **Markdown syntax leaking into rendered output** | A document showed literal `==This is the test document!==` instead of rendered/styled text (image 1) — the `==...==` highlight syntax wasn't parsed. `[UNCONFIRMED — may be test content, not a real bug; verify with John]` | If real, breaks trust in the editor's WYSIWYG promise — same family as BP-104 (formatting drift on save) | S3 pending confirmation, raise to S2 if it affects real (non-test) content |

**Noted but not codified — needs a design discussion, not a bug ticket:** you suggested replacing the floating bottom bulk-action bar with a sticky action column. This is a legitimate alternative pattern, but floating action bars (seen consistently across images 2, 3, 4) may be an intentional, already-reviewed style-guide choice. Recommend raising it as a design question to John rather than logging it as a defect — codifying your personal layout preference as a "bad UX pattern" risks flagging Lexful's deliberate design as a bug.

---

## N. Existing engineering tooling context (from Storybook config, Oct)

Not bad-UX patterns — this is context on what Lexful's engineering side already checks, so the AI harness doesn't duplicate it or assume a gap that isn't there.

- **Axe-core accessibility checks already run** via `@storybook/addon-a11y`, wired into both Storybook and their Vitest suite (`vitest.setup.ts`). **But `a11y.test` is set to `"todo"`** in `preview.ts` — violations are shown, not enforced. CI does not fail on them today.
- **Chromatic visual regression** (`@chromatic-com/storybook`) screenshots **isolated component stories only** — it has no visibility into the live running app, multi-step flows, or anything that only appears after real user interaction (e.g. the document-editor indentation drift, BP-104). This is exactly the gap our end-to-end journey testing fills — not redundant with their existing tooling, a different layer entirely.
- **Implication for us:** ask John/Sherwin whether we should adopt their existing axe ruleset as the accessibility baseline (Lens D) rather than defining our own from scratch, and whether any historical axe/Chromatic reports already exist worth reviewing before we start from zero.
- **Still waiting on:** actual component stories, design tokens, and button/color/spacing values — these 3 files are config only, not the style guide content itself.

---

## Notes for AI exploratory use

- **Don't force-fit.** If nothing matches, write the finding plainly and mark it "ungrouped" rather than stretching a pattern ID to cover it.
- **One finding, one pattern.** If an issue matches two patterns (e.g. BP-20 validate-too-late *and* BP-21 vague-message), cite both rather than picking one.
- **Severity still comes from the main rulebook's S1–S4 scale**, not from this library. This library only helps *find* issues; the rulebook decides how serious they are.
- **This list will grow.** Every real finding that doesn't fit an existing pattern is a candidate for a new BP-## entry — treat week 2 onward as calibration, not just execution.

## Open items
1. `[CONFIRM]` Canonical terminology (Asset vs Device vs Item) — affects BP-61. Note: real terms confirmed for asset types are Document/Password/Contact/Location (core) + custom — "Asset" itself is the correct umbrella term.
2. `[CONFIRM]` Whether multi-editor conflict handling is in scope — affects BP-33.
3. `[CONFIRMED]` "Ask Lex" is real — an agentic AI harness with tool access over the knowledge graph, distinct from keyword/semantic search. BP-40/41/42/43 should be tested against the real feature now, not treated as assumptions.
4. `[CONFIRM]` Whether audit trails exist for destructive actions — BP-92. Note: revision history with restore is confirmed to exist for asset edits; unclear if archive/delete specifically logs a "who" trail.
5. `[CONFIRM]` Whether white-label branding checks are in scope for Phase 1's 3 journeys, per Lexful's own "Brand Guidelines Enforcement" doc reference.

## Changelog
- v0.6 — Added a top-of-document note flagging that all severities below use the superseded old S1–S4 scale; points to the rulebook's new S0–S3 scale (confirmed Oct 5 with engineering) and its mapping table. No individual BP entries relabeled yet.
- v0.5 — Strengthened BP-11 and BP-12 with real confirmed evidence: a 2-character search ("To") returned results with no visible match to the query. Logged as Live Findings Log #11. Flagged as contradicting the earlier "no LLM" description of search — needs direct confirmation of matching logic.
- v0.4 — Downgraded BP-101 from "likely bug" to "confirmed intentional, verify discoverability only" per QA's search test document. Added a confirmed-good-patterns note to Section L (search close/filter/case behaviors already well-tested). Added Section N: existing engineering tooling context (axe via Storybook, non-blocking; Chromatic is component-level only).
- v0.3 — Added Section M (BP-106 to BP-109) from [REDACTED]'s own hands-on screenshots: empty-state inconsistency, missing search guidance, absent toast confirmations, possible markdown-rendering bug. Strengthened BP-20 and BP-103 with real confirmed evidence. Logged the floating-action-bar suggestion as an open design question rather than a codified pattern.
- v0.2 — Added Section K (5 confirmed real issues from Sept 29 live walkthrough: BP-100 to BP-105) and Section L (confirmed product facts to prevent false positives: archive behavior, read-only org rules, locked core fields, no templates, real persona names). Corrected accessibility references to WCAG 2.1 AA per Lexful's own internal doc.
- v0.1 — Initial draft, built from general UX heuristics (Nielsen-style) mapped onto Lexful's 3 journeys and AI features. Unsigned.
