# FEATURE: Assets CRUD E2E (share pack)

**Spec:** `assets-crud.spec.ts` · **34 tests**

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
