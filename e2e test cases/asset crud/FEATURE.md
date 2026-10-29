# FEATURE: Assets CRUD E2E (share pack)

**Spec:** `assets-crud.spec.ts` (AC-001–AC-034) and `inline-attachments.spec.ts` (AC-035–AC-037)

Combines `Assets-E2E` (31) and `asset-crud-e2e` (3) into one spec.

## Run

```bash
node scripts/specs.mjs --headed "e2e test cases/asset crud"
```

Page objects are in this folder. Auth is `../../auth-helper`. Paths are relative to `QA_ENV_URL`.

## Tests

- Authentication (4)
- Assets main (5)
- Create cancel (1)
- Server lifecycle create / edit / archive / tag / duplicate (2)
- Servers listing (5)
- Filters (3)
- Bulk actions (4)
- Server detail (10)

## Inventory

Type and suite are recorded here. A word in the test title does not decide them.

| TC | Title | Type | Suite |
|---|---|---|---|
| AC-001 | POST /auth/password returns HTTP 204 with both cookies | positive | Regression |
| AC-002 | cookies apply to the app domain — not redirected to login | positive | Regression |
| AC-003 | invalid credentials returns HTTP 4xx | negative | Regression |
| AC-004 | expired/missing cookie redirects to login | negative | Regression |
| AC-005 | clicking into Servers type navigates to listing | positive | Regression |
| AC-006 | clicking into Applications type navigates to listing | positive | Regression |
| AC-007 | search opens Ask Lex with matching records | positive | Regression |
| AC-008 | Ask Lex button opens AI panel | positive | Regression |
| AC-009 | user menu opens and shows options | positive | Regression |
| AC-010 | Cancel button closes the drawer without creating | edge | Regression |
| AC-011 | server happy path: create, find, edit, delete | positive | Regression |
| AC-012 | after create: add a tag, duplicate, then archive | positive | Regression |
| AC-013 | toolbar buttons are visible | positive | Regression |
| AC-014 | open row detail drawer and verify | positive | Regression |
| AC-015 | detail drawer has all 8 tabs | positive | Regression |
| AC-016 | details tab shows editable fields | positive | Regression |
| AC-017 | overview tab shows linked items | positive | Regression |
| AC-018 | search is case-insensitive | positive | Regression |
| AC-019 | bulk action buttons appear when rows selected | positive | Regression |
| AC-020 | clear selection resets selection count | edge | Regression |
| AC-021 | deselecting one row after select-all decreases count | positive | Regression |
| AC-022 | clear selection resets selection count | edge | Regression |
| AC-023 | multiple rows can be selected | positive | Regression |
| AC-024 | bulk Actions button is present when rows are selected | positive | Regression |
| AC-025 | clicking a row opens the detail drawer | positive | Regression |
| AC-026 | detail drawer has Edit Name button | positive | Regression |
| AC-027 | Overview tab shows Relationships section | positive | Regression |
| AC-028 | Details tab shows all editable fields | positive | Regression |
| AC-029 | Details tab shows additional fields | positive | Regression |
| AC-030 | drawer close button closes the drawer | positive | Regression |
| AC-031 | Escape key closes the drawer | positive | Regression |
| AC-032 | Copy link button is present | positive | Regression |
| AC-033 | Expand record button is present | positive | Regression |
| AC-034 | More actions button is present | positive | Regression |
| AC-035 | A saved inline image marks its attachment Embedded and disables Delete | positive | Smoke |
| AC-036 | Removing the image and saving re-enables Delete, which then removes it | positive | Smoke |
| AC-037 | Cancelling the confirmation keeps an ordinary attachment | negative | Smoke |
| AC-038 | Move password stays disabled until a destination is chosen and excludes the current organization | edge | Smoke |
| AC-039 | Cancel closes the Move dialog and submits no move | edge | Smoke |
| AC-040 | Ordinary PATCH rejects an organization change and leaves the record in place | negative | Smoke |
| AC-041 | password record drawer Overview shows username, URL and a masked password | positive | Smoke |
| AC-042 | Copy password requests the secure password from the API | positive | Smoke |
| AC-043 | New Passwords shows every field and keeps Create disabled until an organization is chosen | negative | Smoke |
