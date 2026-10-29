You own functional QA in this session: Explore, Author, Heal, and Promote when the server asks.

Read `.agents/skills/lexful-autonomous-agent-qa/SKILL.md` and follow it. Read `references/custom-instructions.md` at Step 0. Do not spawn subagents. Do every step yourself in this session.

**Feature Specific TCs** (default for a LEX ticket):

1. Read `preflight.json` and `context-pack.json` in the run directory. Use `appUrl`. Do not start a dev server. Read `e2e-coverage.md`. Do not call Linear, GitHub, or `/auth/password`. Do not read `.env`.
2. Explore with `playwright-cli`: append each successful step to `explore/flow.md`, write `FEATURE.md` (planned cases, gaps, API endpoints). See `references/listing-exploration-hints.md` when the walk includes a listing.
3. Author POM and specs under the run's `specs/` from the walk only. Write tests for `new` rows the walk reached. Do not write `covered` rows or gaps. Write `planned-specs.json`. Do not run the official Playwright suite.
4. When the server sends a heal prompt, follow **Feature Specific Heal** in the skill. Replay failures, write `triage.json`, patch specs or report bugs. Do not run the official suite.
5. When the server sends promote, follow **Promote** in the skill. Use `playwright/test-outcomes.json` for final pass/fail per test title (after heals). Write `promoted.json`.

**E2E User Journey TCs** (server message says so):

- Do not explore or author. Follow **E2E User Journey heal** in the skill only. Patch spec drift in `e2e test cases/`. CloudFront **403 Request blocked** on UAT is environment timing, not a product bug — class **spec** and retry navigation per custom-instructions; do not file it on `bugs`.
- Write `triage.json`. Do not run the suite; the server re-runs when files change.

Stay inside this repository. The server writes `qa-result.json`, `bugs.md`, and the verdict.
