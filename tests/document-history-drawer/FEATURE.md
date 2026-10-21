# LEX-3408: Document Actions, Revision Previews, and Lex Handoffs

**Ticket:** Daylight — Document actions, revision previews, and Lex handoffs  
**App URL:** https://e2e-test.uat.lexful.net  
**Run Directory:** runs/LEX-3408-20261019T094453Z-de92/

## Overview

This feature polishes the document drawer without backend changes. It consolidates document actions (Duplicate, Move, Archive, Restore revision, Print) into a single "More actions" menu, introduces saved revision previews with Exit history, keeps Lex beside Download with text selection awareness, and improves AI review states and handoffs.

## Test Coverage Plan

### Smoke Tests (3)
- [x] **SMOKE-01** — Drawer opens with Document and History tabs visible
- [x] **SMOKE-02** — More actions menu shows 4 main items: Restore revision, Duplicate, Print, Archive
- [x] **SMOKE-03** — Download menu shows PDF, Markdown, and HTML format options

### Actions Menu Tests (1)
- [x] **ACTIONS-01** — Archive menu item opens a confirmation dialog and can be cancelled

### Revisions Preview Tests (4)
- [x] **REVISION-01** — Viewing a revision opens read-only preview with "Viewing revision from" banner
- [x] **REVISION-02** — Saved revisions list shows Latest badge on first item and read-only snapshot text
- [x] **REVISION-03** — Exit history button returns to document view and hides revision preview
- [x] **REVISION-04** — Restore button is hidden when viewing latest revision

### Lex Integration Tests (3)
- [x] **LEX-01** — Lex button is visible in read mode next to Download button
- [x] **LEX-02** — Entering edit mode keeps Lex visible in toolbar or header
- [x] **LEX-03** — Lex button is enabled and clickable when text is selected in editor

### Edit Mode Tests (3)
- [x] **EDIT-01** — Edit button opens ProseMirror editor and Save button is initially disabled
- [x] **EDIT-02** — Download button is disabled while in edit mode
- [x] **EDIT-03** — Cancelling edit without changes sends no PATCH request and re-enables Download

### Restore Dialog Tests (1)
- [x] **RESTORE-01** — Cancel button closes restore dialog without sending restore request to /restore endpoint

## Test Execution

### Run Tests
```bash
npx playwright test tests/document-history-drawer/
```

### Run Specific Test File
```bash
npx playwright test tests/document-history-drawer/smoke.spec.ts
npx playwright test tests/document-history-drawer/revisions.spec.ts
npx playwright test tests/document-history-drawer/lex-integration.spec.ts
```

## API Endpoints Observed

### Document Revision Endpoints
- **List revisions:** `GET /system.document/{id}/revisions?limit=50&offset=0`
- **Get single revision:** `GET /system.document/{id}/revisions/{revisionId}`
- **Restore revision:** `POST /revisions/{revisionId}/restore`

### Asset/Document Endpoints
- **List documents:** `GET /v1/assets/system.document?...` (with filters, pagination)
- **Get document:** `GET /v1/assets/system.document/{id}`
- **Update document:** `PATCH /v1/assets/system.document/{id}`
- **Delete/Archive:** `DELETE /v1/assets/system.document/{id}` or `PATCH` with archived flag

## Selectors Reference

### Drawer & Tabs
```javascript
// Drawer container
page.getByRole('dialog').first()

// Drawer heading (document name)
page.getByRole('heading', { name: <docName>, level: 2 })

// Record sections tablist
page.getByRole('tablist', { name: 'Record sections' })

// Individual tabs
page.getByRole('tab', { name: 'Document', exact: true })
page.getByRole('tab', { name: 'History', exact: true })

// Close button
page.getByRole('button', { name: 'Close', exact: true }).first()
```

### Document Content & Edit
```javascript
// Document content article
page.getByRole('article', { name: 'Document content' })

// Edit button
page.getByRole('button', { name: 'Edit content' })

// Editor
page.getByRole('tabpanel').locator('.ProseMirror').first()

// Save & Cancel
page.getByRole('button', { name: 'Save changes' })
page.getByRole('button', { name: 'Cancel', exact: true })
```

### Actions Menu
```javascript
// More actions button
page.getByRole('button', { name: 'More actions' })

// Menu items
page.getByRole('menuitem', { name: 'Restore revision…' })
page.getByRole('menuitem', { name: 'Duplicate…' })
page.getByRole('menuitem', { name: 'Print' })
page.getByRole('menuitem', { name: 'Archive…' })
```

### Download
```javascript
// Download button
page.getByRole('button', { name: /Download document|Preparing download/ })

// Download formats
page.getByRole('menuitem', { name: /^PDF/ })
page.getByRole('menuitem', { name: /^Markdown/ })
page.getByRole('menuitem', { name: /^HTML/ })
```

### History & Revisions
```javascript
// History panel
page.getByRole('tabpanel', { name: 'History' })

// History entries
page.getByRole('tabpanel', { name: 'History' }).getByRole('article')

// View revision button
page.getByRole('button', { name: 'View revision' })

// Revision preview
page.getByRole('region', { name: 'Revision preview' })

// Saved revisions sidebar
page.getByRole('complementary', { name: 'Saved revisions' })

// Exit history button
page.getByRole('button', { name: 'Exit history' })

// Restore this revision button
page.getByRole('button', { name: 'Restore this revision…' })

// Restore dialog
page.getByRole('heading', { name: 'Restore this record?' })
page.getByRole('button', { name: 'Restore record' })
```

### Lex Integration
```javascript
// Lex button (read mode)
page.getByRole('button', { name: 'Lex' }).first()

// Lex in toolbar (edit mode)
page.locator('[role="toolbar"]').first().getByRole('button', { name: 'Lex' })
```

## Key Testing Considerations

### Auth & Setup
- Auth tokens provided in `auth-state.json` from the run directory
- Do NOT call `/auth/password` — will be rate-limited
- Sessions last ~12 hours; refresh only when expired

### DOM & Rendering
- Use `domcontentloaded` + explicit waits, never `networkidle`
- Lex button appears in multiple contexts; use `.first()` or scope by context
- Download button disabled while editing
- AG Grid loads rows async; wait for real rows, not placeholder "loading" state
- Overlay blocks clicks on "Clear selection" / "Actions" — use `force: true`

### Network & Timeouts
- CloudFront 403 occurs ~1–3% of the time on shared UAT; `retries: 2` absorbs it
- Revision requests may take up to 15s; use timeout explicitly
- Always check for actual API responses before proceeding

### Test Scope & Safety
- Destructive actions (Archive, Restore) must be cancelled in tests — never persist changes
- Staged AI drafts must be retained when opening drawer via detail link
- Preserve text selection state after Lex interaction
- Re-snapshot element refs before each action (refs go stale after re-render)

## Test Fixtures & POM

### Files
- `tests/document-history-drawer/document-history-drawer-pom.ts` — Page Object Model
- `tests/document-history-drawer/fixtures.ts` — Test fixture with auth injection
- `tests/document-history-drawer/smoke.spec.ts` — Smoke tests
- `tests/document-history-drawer/actions-menu.spec.ts` — Action menu tests
- `tests/document-history-drawer/revisions.spec.ts` — Revision preview tests
- `tests/document-history-drawer/lex-integration.spec.ts` — Lex integration tests
- `tests/document-history-drawer/edit-mode.spec.ts` — Edit mode tests
- `tests/document-history-drawer/restore.spec.ts` — Restore dialog tests

### Seeded Test Document
- **ID:** `01a0ee77-599d-74b9-b87a-f8fe5c48b56f`
- **Name:** `Amet duis`
- **Organization:** `Adipiscing Aliqua Academy`

## Total Test Count

**15 tests planned and implemented** across 6 spec files covering smoke, positive, and negative scenarios for document drawer actions, revision previews, Lex integration, edit mode, and restore dialogs.
