# Phase `promote`: copy a few passing journeys into the checked-in suite

After the feature specs have run and the UX audit has finished, the server asks you to copy **a few** passing tests into `e2e test cases/`. In this phase you may edit that folder. The shared rules in `.agents/prompts/qa.md` apply. The inputs are `playwright/test-outcomes.json` (the final pass/fail of each test title after all heals; only a `passed` title can qualify), `specs/` and `e2e-coverage.md`.

The checked-in suite runs on every E2E run, so every test you add is paid for forever and can break the run. **The default is to promote nothing.**

A test qualifies only if it passes **all** of these:
1. **It is a user journey in exactly one of search, asset crud or document editing**: a person using the page, with the page as the thing under test. An API-only test (no page), a contract check of a new endpoint, or a check of internal state is not a journey.
2. **It will still be true next quarter.** Not tied to this ticket's rollout: no dependence on an account mode (legacy, shadow, enforced), a feature flag, or a build that is not yet everywhere. A snapshot of today's permissions or field lists goes stale and fails later.
3. **It is deterministic and cheap.** No AI or Lex response, no wait over about 30 seconds, no dependence on seeded names that the suite does not already use.
4. **It is new.** Read the target folder's `FEATURE.md` and grep its specs first. If a row or test already asserts the same surface, skip it. Two variants of one guard (for example Cancel and Escape) are one test; keep the more direct one.
5. **It cleans up after itself and stands alone.** Anything it creates or moves is restored in `afterEach`, and it passes when it runs alone on a fresh worker (the suite runs test by test, not file by file).

Take **at most two**, and only when each is a different behavior. When several candidates pass, prefer the one that fails loudly if the behavior regresses. Skip gaps, failures, skips, tooltip-only checks and any title already in `e2e-coverage.md`.

Put document-editor flows in `document editing` (the next `TC-DOC-` id), record drawers, attachments and Move in `asset crud` (the next free `AC-` id, with no gaps in the numbering), and search-palette flows in `search`. Import auth as `../../auth-helper`, keep the POM beside the spec and keep `afterEach` cleanup. Append one inventory row per test to that folder's `FEATURE.md`; the `test()` title must match the Title cell. Do not leave helpers in a page object that no test uses. Do not run Playwright, edit specs already in the suite, or change `playwright.config.ts`.

Write `promoted.json` in the run directory: `files`, `cases` (`id`, `title`) and `skipped` (`title`, `reason`, a few words) for every passing candidate you rejected. If nothing qualifies, write it with empty `files` and `cases` and list the candidates in `skipped`. The server loads each spec you add; one that does not load is removed and the whole promotion is reverted. Each promotion is recorded in `e2e test cases/changes.log`.
