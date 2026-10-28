You are the Author step of Feature Specific TCs in `.agents/skills/lexful-autonomous-agent-qa/SKILL.md`. Read Author and `references/custom-instructions.md` before you write files. Do not explore the app. Do not call Linear, GitHub, or `/auth/password`.

`FEATURE.md` in the run directory is the source of truth. Also read the run's `e2e-coverage.md` and `context-pack.json`.

`e2e-coverage.md` lists the cases E2E User Journey TCs already run for search, asset crud, and document editing. If a planned row is `covered`, cite that id and do not write the spec again. Write a spec only for a row marked `new`: behavior this ticket adds or changes that the coverage file does not already assert. A new surface that is not one of those three journeys has no baseline, so write the cases that surface needs.

There is no minimum and no maximum. Do not pad the run, and do not stop while a new row has no test. A missing checkbox on a new row is still a test. A test that passes by skipping the assertion does not count. Do not write a skipped or deprecated test.

Each new test has one type and one suite:

- Type: `@positive` the action succeeds, `@negative` bad input or a forbidden action is rejected, `@edge` a boundary such as discard, cancel, clear, or empty.
- Suite: `@bvt` the one path that proves the change is alive, `@smoke` that path plus the guards that would make the feature unusable, `@sanity` read-back after reload and a boundary that must hold before the full suite, `@regression` the remaining behavior this ticket changes.

One spec file is one suite. Types share that file. The id is `TC-<TICKET>-001` and does not reuse an id from `e2e-coverage.md`.

```ts
import { test, expect } from '@playwright/test'
import { injectAuthCookies } from '<auth import path>'

test.describe('LEX-3717 documents — smoke', () => {
  test('TC-LEX-3717-001: Save keeps the new expiry after reload', {
    tag: ['@positive', '@smoke'],
  }, async ({ page }) => {
    await injectAuthCookies(page.context())
    // Do the change, reload, and assert the value stuck.
  })

  test('TC-LEX-3717-002: Create is blocked while the name is empty', {
    tag: ['@negative', '@smoke'],
  }, async ({ page }) => {
    await injectAuthCookies(page.context())
    // Assert the guard. Do not skip the assertion when the control is missing.
  })
})
```

Specs use `injectAuthCookies` from the import path the task gives you. The default call signs in as admin. A case Explore recorded for another role passes that role:

```ts
await injectAuthCookies(page.context(), 'support')
await injectAuthCookies(page.context(), 'viewer')
```

Do not call `node scripts/persona.mjs` from a spec, and do not call `/auth/password`. The server signs in each named persona before Playwright. Every data load uses `page.waitForResponse` for an API recorded in `FEATURE.md`.

Write the POM and the specs only inside the run directory's `specs/` folder. Leave `FEATURE.md` in the run directory. Do not copy it into `specs/` or `tests/`.

When the files are written, write `planned-specs.json` in the run directory. Paths are relative to the repo root:

```json
{
  "plan_file": "runs/<ticket>/<run-id>/FEATURE.md",
  "test_files": ["runs/<ticket>/<run-id>/specs/<area>-<suite>.spec.ts"],
  "pom_files": ["runs/<ticket>/<run-id>/specs/<name>-pom.ts"]
}
```

Do not run the suite.
