# QA traceability: how QA's material and our UX checks fit together

**Purpose.** QA owns the functional tests for the three flows. Our checks add the UX, design and accessibility layer. This file shows what QA covers, what it leaves open, what it tells us about the real platform, and where the first real audit run (Oct 16) disagreed with it.
**Files:** `qa-specs/search/`, `qa-specs/asset-crud/`, `qa-specs/document-editing/` (Agent 007 reads them before each run).
**Rules:** (1) A QA test states **expected behavior**: use it as the "expected" when it applies and cite it in `qaRefs`. (2) Your finding must still come from what you observed this run. (3) If your observation differs from QA, say so. (4) Behavior QA tests as expected is **not a defect**: at most an Observation. (5) QA's POM files hold locators that already work: try them first, and log a healing event when you must switch.
**Reference ids:** `TC-SRCH1xx` = QA's Search test-case plan (PDF, all NOT EXECUTED on Oct 5); `SPEC-TC-nn` = `search_spec.ts`; `TC-DOC-0nn` = Document specs; `assets-crud_spec.ts:L<line>` = Asset CRUD spec.

---

## 1. Environment facts Agent 007 must respect (from QA)

| Fact | What to do |
|---|---|
| **CloudFront WAF blocks bursts.** UAT sometimes answers "403 ERROR, Request blocked". QA runs one worker and waits 45 seconds after a block. | If you see "Request blocked" or a 403 page, stop for 45 seconds and retry, at most 3 times. This is the environment, not an app defect. Keep one worker and pace actions. |
| **The Stytch JWT lives 5 minutes.** QA refreshes the session on the fly; without that, runs longer than 5 minutes bounce to `/platform/login`. | If you land on a login page mid-run, stop and ask the user to re-run the login step. Never loop. Ask QA for their `auth-helper.ts` and session refresh helper (no secrets) so runs survive past 5 minutes. |
| **Google SSO is disabled.** QA logs in by password persona through the API. | Do not plan around Google or Microsoft buttons. |
| **Only one persona has been exercised: org owner of "E2E Demo"** (sees Settings, Account, Platform). `support` and `viewer` accounts are not configured. | State your role as inferred: if Settings, Account and Platform are visible, write "Admin or owner (inferred from the Administration menu)". Never write "Support" unless the app shows it. Ask for Support and Viewer test accounts. |
| **URL patterns:** Assets `/docs/assets`; a type listing `/docs/d/all/<type>` (for example `/docs/d/all/servers`); Documents `/docs/d/all/system.document`; an open record is in the URL as `?drawer=`. | Do not guess URLs. Open types by clicking their cards or sidebar links. The first real run's search-scope ticket used `/docs/assets/computers`, which is a 404 page. |
| **Test organization:** "E2E Demo". **Search is server-side:** `GET /v1/search?term=&limit=20` with optional type and organization filters, 20 results per page. | "Why did this result match?" is decided by the server, not the UI. |

## 2. Search

**QA's plan (PDF, TC-SRCH101 to 150)** is mapped in the check list (`qa_refs`). **QA's automated suite (`search_spec.ts`, 12 cases):**

| SPEC case | What it proves | Our check |
|---|---|---|
| TC-01 header button opens palette, Escape closes it | Escape works on the search palette | SRCH-05 (expect PASS), SRCH-01 |
| TC-02 Cmd/Ctrl+K toggles open and shut | Shortcut toggles | SRCH-01 |
| TC-03 a burst of keystrokes sends one request | Typing is debounced | SRCH-10 |
| TC-04 "AD" expands to "Active Directory" before searching | Intentional term rewrite, hint shown in the results header | SRCH-02 (do not flag; check the hint is visible) |
| TC-05 exact record matches case-insensitively | Basic relevance | SRCH-02 |
| TC-06 no-results state, Reset recovers (focus returns to the box) | A next step exists | SRCH-09 (expect PASS) |
| TC-07 More results / Previous, 20 per page | Pagination | SRCH-02 |
| TC-08 / 09 / 10 type token, organization token, combined, Backspace removes the last chip | Filters work | SRCH-08 |
| TC-11 arrows move the highlight (ArrowUp wraps), Enter opens | Keyboard results | SRCH-01 |
| TC-12 documented accessibility contract of the search widget | Search is well labeled (combobox "Search assets", labelled listbox, status, shortcuts) | do not flag search-widget naming |

**Still ours alone:** match highlighting (SRCH-03), whether a visible match exists in the title (SRCH-02), how clearly the two search boxes differ (SRCH-04), the read-only organization Ask Lex case (SRCH-07).

## 3. Asset CRUD (`assets-crud_spec.ts`, 34 tests on the Servers type)

| QA group (lines) | Covers | Our checks |
|---|---|---|
| Authentication (L32-92) | Login API, cookies, redirect when expired | none (infrastructure) |
| Assets main page (L93-138) | Type cards open listings, search opens Ask Lex, user menu | SRCH-07, SRCH-08 |
| Create cancel (L139-160) | Cancel closes the create drawer without creating | CRUD-02 |
| Server lifecycle (L161-275) | Create, find, edit, delete; add a tag, duplicate, archive | CRUD-01, 03, 10, 11 |
| Servers listing (L276-339) | Toolbar, open a row, 8 tabs, editable fields, linked items | CRUD-12 |
| Filters and search (L340-375), Bulk actions (L376-417) | Case-insensitive search, selection, clear, select-all, Actions button | CRUD-09 |
| Server detail drawer (L418-510) | Edit Name, Overview, Details, close button, Escape, Copy link, Expand, More actions | A11Y-02, CRUD-12 |

**What QA states as expected:** Create stays disabled until Name, Organization and (for Servers) Role are set; edits are staged with a change counter and Save / Discard / Cancel; Escape and the Close button close the record drawer; archive asks for confirmation and is a soft delete; the record drawer has 8 tabs (Overview, Details, Relationships, Attachments, Access, History, Sources, System info).
**QA does not test:** validation messages, unsaved-change warning when navigating away, toasts (no test asserts one; the POM's toast helper looks for `.Toastify__toast`, which may not be the library the app uses), empty states, relationships, attachments, history and restore, access changes, keyboard flows, accessibility scans.
**QA's accessibility notes (from its POM comments, verify with axe):** most create-form fields have no accessible name (placeholders only); the organization picker has a combobox role with no name; grid column headers have no aria-label.

## 4. Document editing (TC-DOC-001 to 013, `FEATURE-doc-edit.md`)

| TC | Behavior | Our check |
|---|---|---|
| 001, 002, 003 | Create, rename, edit body and save, persists after reload | DOC-01, DOC-05 |
| 004 | Bold is stored as `**` (Markdown) and rendered by the read view | DOC-01 |
| 005, 013 | Set and clear expiry | DOC-08 |
| 006 | Assign a tag (skipped if no tag exists) | none |
| 007 | **Underline and Highlight exist only in HTML mode**; Markdown mode does not offer them | DOC-04, DOC-06 |
| 008 | Archive is a soft delete (`deleted_at` on the server) | CRUD-03 |
| 009 | Create is blocked until an organization is chosen | CRUD-01 (intended) |
| 010 | Empty name is rejected by native browser validation | CRUD-01 (intended) |
| 011, 012 | Discard a staged rename; Cancel the body editor: nothing is saved | DOC-07, CRUD-02 |

**QA's own coverage matrix leaves these open (best targets for our exploratory pass):** remove a tag, duplicate, print, restore a revision, Access tab (change visibility, grant a user or group), download, insert image, insert link or embed or table, bulk select and bulk actions, the Relationships / Attachments / History / Sources / System info tabs, Copy link, Expand record. Covered by DOC-09, DOC-10, CRUD-09, CRUD-12.
**Accessibility notes from QA:** the editor surface (`.tiptap`) has no role or aria-label; the formatting toolbar is a plain group labelled "Document formatting", not a toolbar. Covered by A11Y-05, A11Y-06.

## 5. QA's own open items (use as known issues)

| Item | Use |
|---|---|
| Expiry is stored as local midnight converted to UTC (for example `2026-10-30T18:30:00Z` for a tester in UTC+5:30) | Check the day shown is the same for people in other time zones (DOC-08) |
| Markdown and HTML buttons only change how the next save is stored; the round trip is not symmetric | Check the mode switch does not lose formatting (DOC-06) |
| Select-all in the list is flaky in an existing QA test (TC-A08 in `assets-list.spec.ts`) | Test select-all and deselect carefully (CRUD-09) |
| Archive `DELETE` rejects an empty JSON body (API client quirk) | Note only; not a UI finding |
| Access tab, Support and Viewer personas, tag removal are not covered | Ask for accounts; test what an owner can see |

## 6. Where the first real run (Oct 16) disagreed with QA

| Ticket | What QA material says | Recommended action |
|---|---|---|
| CRUD-02-001 S1 "no unsaved warning" | The app has staged edits with a change counter and Save / Discard / Cancel, and the run's own screenshot shows a "Discard unsaved changes?" dialog | Withdraw. Its wording also matched the old sample data |
| CRUD-01-001 "Create silently disabled" | Disabled-until-required-fields is expected (TC-DOC-009, 010, Servers needs Role too) | Not a defect. S3 or Observation: required fields are not marked or explained |
| DOC-04-001 "highlight stripped after save" | Highlight exists only in HTML mode; Markdown mode does not offer it (TC-DOC-007) | Retest in both modes. Likely expected; at most S3 |
| SRCH-04-001 "two search boxes alike" | Intentional two-tier design; evidence screenshot is a 404 page from a guessed URL | Observation, re-capture on `/docs/d/all/<type>` |
| CRUD-06-001 "no toast" | No QA test asserts a toast; the POM expects react-toastify | Keep as S3 after checking the toast library |
| Role "Support" in the header | Only the owner persona has been exercised; Administration menu was visible | Report the role as inferred |

## 7. Requests to QA and Sherwin

1. Support and Viewer test accounts (permission and read-only checks).
2. QA's `auth-helper.ts` and session refresh helper, without secrets, so runs survive past 5 minutes.
3. Which toast library the app uses, and which actions should show a toast.
4. Any QA bug list with severities (we will turn it into known issues).

## Changelog
- **2026-10-21 (1)**: Created; Search mapped from the PDF plan.
- **2026-10-22 (2)**: Added `search_spec.ts`, `assets-crud_spec.ts`, Document specs and POMs. Added environment facts, QA-stated expected behavior, QA's open items, and the Oct 16 re-check. New checks CRUD-09 to 12, DOC-06 to 10, A11Y-05 and 06 (40 checks total).
