# FEATURE.md — Lexful UAT `/docs/d/all/system.document` : **Document editing**

- **URL under test:** `https://e2e-test.uat.lexful.net/docs/d/all/system.document`
- **Environment:** `QA_ENV_URL` → `e2e-test.uat.lexful.net` (remote UAT; no local DB, no global setup)
- **API host:** `https://api.uat.lexful.net`
- **Account / primary org:** `01a0ee54-00c2-7054-ae8b-a4cb9e1b7d8b` = **E2E Demo** (`asset_management_usable: true`)
- **Run:** `node scripts/specs.mjs --headed "e2e test cases/document editing"`
- **Spec files** (this folder)
  - `doceditspec.spec.ts` — TC-DOC-001 … TC-DOC-010
  - `doceditspec-2.spec.ts` — TC-DOC-011 … TC-DOC-013
- **Page objects** (this folder): `document-pom.ts`, `assets-list-pom.ts`, `document-fixtures.ts`, `document-session.ts`
- **Auth:** `../../auth-helper`. App paths are relative to `QA_ENV_URL`. Google SSO is disabled.

---

## 1. Role-based access

| Persona | Notes |
|---|---|
| `default` | Org owner of **E2E Demo**; sees Settings / Account / Platform; full create + edit rights. **Only persona exercised.** |
| `admin` | Stytch admin persona — captured for the session, not asserted. |
| `support` / `viewer` | Credentials not configured in `playwright-tests/.env`; permission assertions deferred (see §7). |

---

## 2. Data model

`GET /v1/asset_types?name=system.document` returns:

```json
{
  "name": "system.document",
  "display_name": "Documents",
  "is_system": true,
  "content_property": "content",
  "properties": [
    { "name": "name",       "type": "string",          "required": true,  "display_name": "Name" },
    { "name": "content",    "type": "richtext_large",  "required": false, "display_name": "Content" },
    { "name": "expires_on", "type": "datetime",        "required": false, "display_name": "Expires On" }
  ],
  "references": []
}
```

| Field | Stored as | Notes |
|---|---|---|
| `name` | string | Required. Inline-edited in the record header. |
| `content` | richtext_large (TipTap) | **Markdown when authored in a new-document editor, HTML when the stored value already starts with a block tag** (`isHtml()` in `src/lib/utils/html.ts`). |
| `expires_on` | ISO instant | The selected day at **local midnight**, serialized by `serializeDateTime()` → `toISOString().slice(0,19) + 'Z'`. |
| tags | separate resource | `PUT` / `DELETE /v1/tags/{tagId}/assets`. |
| access | separate resource | `PUT /v1/assets/{type}/{id}/access_grants` when visibility = `restricted`. |

---

## 3. API endpoints captured

| Method | URL | Trigger |
|---|---|---|
| GET | `/v1/asset_types?name=system.document` | Documents grid load |
| GET | `/v1/assets/system.document?limit=100&sort=name,id&order=ASC&expand=tags&group_by=organization_id` | Grid load (grouped) |
| GET | `/v1/assets/system.document?organization_id={id}&limit=100&…&expand=tags` | Per-expanded-group load |
| GET | `/v1/assets/system.document?organization_id={id}&search={q}&limit=100&…` | In-list search (URL param is `q`, API param is `search`) |
| GET | `/v1/assets/system.document?limit=1&expand=tags&group_by=organization_id` | Count refresh after a write |
| GET | `/v1/assets/system.document/{id}?expand=references,tags&include_deleted=true` | Record drawer open |
| GET | `/v1/assets/system.document/{id}/related` | Relationships tab |
| GET | `/v1/assets/system.document/{id}/revisions?limit=50&offset=0` | History tab |
| GET | `/v1/organizations?limit=100&status=active` | Organization picker in the create drawer |
| GET | `/v1/tags?limit=1000&offset=0` | Tag tree in the "Add tag" popover |
| GET | `/v1/accounts/{id}/navigation/me`, `/v1/accounts/{id}/status` | Shell load |
| GET | `/v1/assets/counts?` | Sidebar counters + the grid summary |
| **POST** | **`/v1/assets/system.document` → 201** | **Create button** |
| **PATCH** | **`/v1/assets/system.document/{id}` → 200** | **Save changes (name / content / expires_on)** |
| **PUT** | **`/v1/tags/{tagId}/assets` → 201** | **Save changes with a staged tag** |
| **DELETE** | **`/v1/tags/{tagId}/assets` → 204** | **Save changes with a removed tag** |
| **DELETE** | **`/v1/assets/system.document/{id}` → 204** | **Archive (More actions → Archive…)** |
| PUT | `/v1/assets/system.document/{id}/access_grants` | Create with visibility = `restricted` |

### Request bodies observed

```jsonc
// POST /v1/assets/system.document  (created from the Markdown editor)
{
  "name": "Q3 Vendor Onboarding Runbook",
  "content": "**Vendor onboarding checklist for the Q3 rollout.**",
  "organization_id": "01a0ee54-00c2-7054-ae8b-a4cb9e1b7d8b",
  "visibility": "inherit"
}

// PATCH /v1/assets/system.document/{id}  — one body per save, only the changed fields
{ "name": "Amet duis QA E2E" }
{ "content": "<p>In magna esse nulla eiusmod incididunt. …</p>" }   // HTML document
{ "expires_on": "2026-10-30T18:30:00Z" }                             // local midnight → UTC

// PUT /v1/tags/{tagId}/assets
["01a0ee77-599d-74b9-b87a-f8fe5c48b56f"]
```

> **Do not** send `Content-Type: application/json` on the archive `DELETE` — the service answers
> `400 {"error_code":"FST_ERR_CTP_EMPTY_JSON_BODY"}`. Send the `X-Account-Id` header only.

---

## 4. Action coverage matrix

Legend: `[x]` covered by a scripted test · `[ ]` not covered (see §7).

| # | Action | Where | Covering TC | Status |
|---|--------|-------|-------------|--------|
| 1 | Create a document (name + org + body) | `New` drawer | TC-DOC-001 | [x] |
| 2 | Create with **no** organization | `New` drawer | TC-DOC-009 | [x] |
| 3 | Create with an **empty** name (required-field rejection) | `New` drawer | TC-DOC-010 | [x] |
| 4 | Open a document from the grid | grid cell → drawer | TC-DOC-001, TC-DOC-002 | [x] |
| 5 | **Rename** a document (inline header edit) | `Edit Name` | TC-DOC-002 | [x] |
| 6 | **Discard** a staged rename | `Discard` | TC-DOC-011 | [x] |
| 7 | **Edit the body** and save | `Edit content` → TipTap | TC-DOC-003 | [x] |
| 8 | **Cancel** the body editor | `Cancel` | TC-DOC-012 | [x] |
| 9 | **Bold** formatting | toolbar | TC-DOC-004 | [x] |
| 10 | Markdown ⇄ HTML mode switch | `Markdown` / `HTML` | TC-DOC-007 | [x] |
| 11 | **Set an expiry date** | `Document expiry` | TC-DOC-005 | [x] |
| 12 | **Clear an expiry date** | calendar `Clear` | TC-DOC-013 | [x] |
| 13 | **Assign a tag** | `Add tag` → tree | TC-DOC-006 | [x] |
| 14 | Remove a tag | tag chip `Remove tag <name>` | — | [ ] |
| 15 | **Archive** a document | `More actions` → `Archive…` | TC-DOC-008 | [x] |
| 16 | Duplicate a document | `More actions` → `Duplicate…` | — | [ ] |
| 17 | Print a document | `More actions` → `Print` | — | [ ] |
| 18 | Restore a revision | `More actions` → `Restore revision…` | — | [ ] |
| 19 | Access tab — change the visibility mode | `Access` tab | — | [ ] |
| 20 | Access tab — grant a user / group | `Access` tab | — | [ ] |
| 21 | Download the document | `Download document` | — | [ ] |
| 22 | Insert an image into the body | `Insert Image` | — | [ ] |
| 23 | Insert a link / embed / table | toolbar | — | [ ] |
| 24 | In-list search | `Search Documents...` | TC-DOC-001, TC-DOC-002 | [x] |
| 25 | Bulk select / bulk Access / bulk Tags / bulk Archive | list bulk bar | — | [ ] |
| 26 | Relationship / Attachment / History / Sources / System info tabs | record drawer tabs | — | [ ] |
| 27 | `Copy link` | record header | — | [ ] |
| 28 | `Expand record` (full width) | record header | — | [ ] |

---

## 5. Test inventory

| TC | Title | Type | Suite | Priority | File |
|----|-------|------|-------|----------|------|
| TC-DOC-001 | Create a document with a name, an organization and body content | positive | BVT | Critical | `doceditspec.ts` |
| TC-DOC-002 | Rename a document from the record drawer | positive | BVT | Critical | `doceditspec.ts` |
| TC-DOC-003 | Edit the document body and save the change | positive | Smoke | High | `doceditspec.ts` |
| TC-DOC-004 | Apply bold formatting to the document body | positive | Smoke | High | `doceditspec.ts` |
| TC-DOC-005 | Set an expiry date on a document | positive | Smoke | High | `doceditspec.ts` |
| TC-DOC-006 | Assign a tag to a document | positive | Smoke | High | `doceditspec.ts` |
| TC-DOC-007 | Switch the body editor between Markdown and HTML modes | positive | Smoke | High | `doceditspec.ts` |
| TC-DOC-008 | Archive a document from the record drawer | positive | Smoke | High | `doceditspec.ts` |
| TC-DOC-009 | Create is blocked while no organization is selected | negative | Smoke | High | `doceditspec.ts` |
| TC-DOC-010 | Creating with an empty document name is rejected | negative | Smoke | High | `doceditspec.ts` |
| TC-DOC-011 | Discard a staged rename leaves the record name unchanged | edge | Regression | Medium | `doceditspec-2.spec.ts` |
| TC-DOC-012 | Cancel the body editor keeps the stored content | edge | Regression | Medium | `doceditspec-2.spec.ts` |
| TC-DOC-013 | Clear an expiry date removes only the expiry | edge | Regression | Medium | `doceditspec-2.spec.ts` |

### Coverage checklist

- [x] Create round-trip — create → the record is in the grid and the count grows by one (TC-DOC-001)
- [x] Update round-trip — rename / body / expiry persist across a reload (TC-DOC-002, 003, 005)
- [x] Delete round-trip — archive removes the record from the active grid (TC-DOC-008)
- [x] Tag round-trip — assign a tag and see it on the record and in the grid (TC-DOC-006)
- [x] Positive path for each editable field (name, content, expires_on, tag)
- [x] Negative path — required organization
- [x] Negative path — required name
- [x] Edge path — discard a staged change
- [x] Edge path — cancel the editor
- [x] Edge path — clear a set value
- [x] Every data-loading action waits on `page.waitForResponse` (no `waitForTimeout` for data)
- [x] No credentials or real e-mail addresses in the specs
- [x] Test data is created and archived by the suite — the UAT sandbox is left as it was found

---

## 6. Selectors that matter (verified against the live app)

| Element | Locator | Notes |
|---|---|---|
| Grid | `[role="treegrid"]` | AG-style. `page.locator('table')` matches nothing. |
| Grid row | `getByRole('gridcell', { name, exact: true })` | The cell text is the document name. |
| Select-all | `getByRole('checkbox', { name: 'Select loaded rows' })` | The input is `opacity:0`; use `click({ force: true })`. |
| Row checkbox | `input[aria-label^="Press Space to toggle row selection"]` | Same opacity trick. |
| Search | `input[placeholder='Search Documents...']` | Debounced 300 ms → URL `?q=…`, API `search=…`. |
| New drawer | `getByRole('dialog')` filtered by `heading "New Documents"` | |
| Name field | `getByRole('textbox', { name: 'Name' })` | `required` — HTML5 validation blocks the submit. |
| Organization picker | `dialog.locator('button[role="combobox"]').first()` | **`role="combobox"` takes its accessible name from the author only, and the app sets none** — `getByRole('combobox', { name: 'Select organization' })` does **not** match. |
| Organization option | `getByRole('option', { name: /^E2E Demo/ })` | In a `listbox "Suggestions"`. |
| Body editor (create) | `.tiptap[contentedelta="true"]` → `.tiptap[contenteditable="true"]` | No role, no aria-label — the class is the only stable hook. |
| Toolbar | `[aria-label="Document formatting"]` | A `generic`, not a toolbar role. |
| Markdown / HTML switch | `getByRole('button', { name: 'Markdown', exact: true })` | **Must be exact** — "Underline (not supported in Markdown)" also matches. The *inactive* button carries the toggle handler. |
| Record drawer | `getByRole('dialog')` → `getByRole('heading', { level: 2 })` | The heading is the document name. |
| Name inline edit | `getByRole('form', { name: 'Edit Name' })` → `getByRole('textbox', { name: 'Name' })` | |
| Body read view | `getByRole('article', { name: 'Document content' })` | |
| Body editor (record) | `getByRole('form', { name: 'Edit Content' })` → `.tiptap[contenteditable="true"]` | |
| Markdown bold in the read view | `[data-streamdown="strong"]` | **streamdown emits a `<span>`, not a `<strong>`.** |
| Dirty counter | `[role="status"]` inside the drawer | "No changes yet" / "N change(s)". |
| Save bar | `Save changes` / `Discard` / `Cancel` | `Cancel` while the body editor is open, `Discard` otherwise. |
| Expiry | `getByRole('button', { name: 'Document expiry' })` | `title` becomes "Expires <date>". |
| Expiry calendar | a **second** dialog with `Go to the Next Month` | Day buttons are named "Thursday, October 15th, 2026". |
| Tag picker | `getByRole('tree', { name: 'Tags' })` → `getByRole('checkbox', { name: tag })` | |
| Record menu | `getByRole('button', { name: 'More actions' })` → `menuitem` | |
| Archive confirm | dialog with `heading "Archive 1 asset?"` → `button "Archive asset"` | |

---

## 7. Open issues / follow-ups

1. **UAT flake — CloudFront 403.** Under load, `e2e-test.uat.lexful.net` intermittently answers
   *"403 ERROR — Request blocked"*. `DocumentRecordDrawer.openById()` retries the navigation three
   times to absorb it. A dedicated retry budget may be worth adding at the config level.
2. **The Stytch JWT lives for 5 minutes and the session token is consumed by a run.**
   `playwright-tests/playwright.config.ts` therefore replays a **sanitised** state
   (`playwright-tests/.auth/storageState.json` — the session token without
   `stytch_session_jwt`), and `playwright-tests/utils/lexful-uat-session.ts` refreshes the
   session on the fly when the app asks for a sign-in. Without this, any run longer than
   five minutes fails with the app bouncing to `/platform/login`.
3. **Access-tab coverage is missing** (rows 19–20 of the matrix). The Access tab is only rendered
   for a signed-in owner and needs a second persona to be meaningful.
4. **Tag removal** (row 14) is not covered — the UAT account currently holds a single tag, so the
   test picks the first available one and skips when the tree is empty.
5. **Persona coverage.** `support` and `viewer` credentials are not in `playwright-tests/.env`, so
   the "read-only persona cannot see the edit affordances" assertions are deferred.
6. **`Content-Type` on the archive `DELETE`** — the service rejects an empty JSON body, so the
   cleanup helper sends `X-Account-Id` only. Worth a note in the harness API client.
7. **Markdown ⇄ HTML round-trip is not symmetric.** A document created in the Markdown editor stores
   Markdown; the same document opened in the editor is therefore in Markdown mode, and the
   `Markdown` / `HTML` buttons only change the *serialization target* for the next save. TC-DOC-007
   asserts the observable effect (Underline / Highlight become available in HTML mode) rather than
   the internal flag.
8. **Pre-existing flake outside this feature:** `tests/docs/assets-list.spec.ts` → TC-A08
   ("Select-all … tracks the selection") fails or flakes on the AG Grid header checkbox.
   Measured with the changes in this feature reverted: 3 failures out of 3 runs. Unrelated to
   the document suite, but worth a separate ticket.
