# FEATURE: Assets CRUD E2E (share pack)

**Spec:** `assets-crud.spec.ts` · **34 tests**

Combines `Assets-E2E` (31) and `asset-crud-e2e` (3) into one spec.

## Run

```bash
cd lexful-qa-opencode
npx playwright test Assets-crud-E2E/assets-crud.spec.ts --headed --retries=0 --reporter=line
```

Share this folder plus `auth-helper.ts`, `playwright.config.ts`, and `.env` from the repo root.

## Tests

- Authentication (4)
- Assets main (5)
- Create cancel (1)
- Server lifecycle create / edit / archive / tag / duplicate (2)
- Servers listing (5)
- Filters (3)
- Bulk actions (4)
- Server detail (10)
