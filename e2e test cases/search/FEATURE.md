# Search

Read-only search on `/docs/assets`. Twelve cases. Creates nothing.

## Run

```bash
node scripts/specs.mjs --headed "e2e test cases/search"
```

| File | Role |
|---|---|
| `search.spec.ts` | The cases |
| `search-pom.ts` | The search widget, palette shortcut, and the `/v1/search` wait |

Auth is `../../auth-helper`. The app path is `/docs/assets` on `QA_ENV_URL`.

Seeded UAT records the cases look up: organization `Esse Amet Accounting Inc`, computer `EAA-WS-003`.

## Inventory

Type and suite are recorded here. A word in the test title does not decide them.

| TC | Title | Type | Suite |
|---|---|---|---|
| TC-01 | opens the palette with the header button and closes it with Escape | positive | Regression |
| TC-02 | the ⌘K / Ctrl+K shortcut toggles the palette open and shut | positive | Regression |
| TC-03 | debounces a keystroke burst into a single keyword request | edge | Regression |
| TC-04 | expands the shorthand "AD" into "Active Directory" before searching | positive | Regression |
| TC-05 | matches an exact record case-insensitively | positive | Regression |
| TC-06 | shows the no-results state and Reset recovers from it | negative | Regression |
| TC-07 | pages results with More results / Previous and resets the page on a new query | edge | Regression |
| TC-08 | the # asset-type token narrows results and adds entity_types | positive | Regression |
| TC-09 | the @ organization token narrows results and adds organization_ids | positive | Regression |
| TC-10 | combines both filters in one request and Backspace removes the last chip | positive | Regression |
| TC-11 | arrow keys move the highlight (ArrowUp wraps) and Enter opens the record | edge | Regression |
| TC-12 | exposes the documented accessibility contract for the search widget | positive | Regression |
