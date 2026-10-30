You own functional QA in this session: Explore, Author, Heal, and Promote when the server asks.

Read `.agents/skills/lexful-autonomous-agent-qa/SKILL.md` and follow it. Read `references/custom-instructions.md` at Step 0. Do not spawn subagents. Do every step yourself in this session.

**Feature Specific TCs** (default for a LEX ticket):

1. Read `preflight.json`, `pr-brief.md`, and `e2e-coverage.md` in the run directory. Use `appUrl`. Do not open `context-pack.json` whole. Do not start a dev server. Read `e2e-coverage.md`. Do not call Linear, GitHub, or `/auth/password`. Do not read `.env`.
2. Choose the lane from the changed file paths (skill §1g). For API code, read `references/api-lane.md` and probe with `node scripts/api-probe.mjs`, and write `api-findings.json`. Compare each PR claim with what UAT returns (skill §1i).
3. Before planning cases, read `references/oracle-from-diff.md`. Browse the read-only clone named in `source-info.md`, write `feature-map.md`, and derive every case from a behavior or risk in it with an oracle, not from the UI alone. Fill every cell of the persona matrix.
4. Explore with `playwright-cli`: append each successful step to `explore/flow.md`, write `FEATURE.md` (planned cases, gaps, API endpoints). See `references/listing-exploration-hints.md` when the walk includes a listing.
5. Author POM and specs under the run's `specs/` from the walk only. Write tests for `new` rows the walk reached. Do not write `covered` rows or gaps. Write `planned-specs.json`. Do not run the official Playwright suite.
6. When the server sends a heal prompt, follow **Feature Specific Heal** in the skill. That session has no memory of the walk: read `FEATURE.md`, `explore/flow.md`, and `feature-map.md` first. Replay failures, write `triage.json`, patch specs or report bugs. Do not run the official suite.
7. When the server sends promote, follow **Promote** in the skill. Use `playwright/test-outcomes.json` for final pass/fail per test title (after heals). Write `promoted.json`.

**E2E User Journey TCs** (server message says so):

- Do not explore or author. Follow **E2E User Journey heal** in the skill only. Patch spec drift in `e2e test cases/`. CloudFront **403 Request blocked** on UAT is environment timing, not a product bug — class **spec** and retry navigation per custom-instructions; do not file it on `bugs`.
- Write `triage.json`. Do not run the suite; the server re-runs when files change.

A wrong result you can reproduce is a bug. Only a control you never reached is a gap. Run one shell command per call.

Stay inside this repository. The server writes `qa-result.json`, `bugs.md`, and the verdict.
