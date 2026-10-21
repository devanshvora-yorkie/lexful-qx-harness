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
