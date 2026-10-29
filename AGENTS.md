# Lexful UAT Playwright suite

Start Feature Specific TCs from the server. Preflight, the Stytch session, and the context pack are written under `runs/tickets/<ticket>/<date>_<time>Z_<id>/` before OpenCode starts. The server also writes `e2e-coverage.md` there. Author must not rewrite a case that file already lists for search, asset crud, or document editing. Specs for the remaining behavior go in that folder's `specs/` directory. Each new test has one type tag (`@positive`, `@negative`, `@edge`) and one suite tag (`@bvt`, `@smoke`, `@sanity`, `@regression`). There is no fixed count. The checked-in suite lives in `e2e test cases/`. E2E User Journey TCs are `runs/phase-1/`. A product bug is recorded in `bugs.md`. `runs/START-HERE.txt` maps the rest.

```bash
npm run serve
npm run ticket -- LEX-3371
```

`npm run ticket` starts Feature Specific TCs and prints `run.log` until it finishes. If that ticket is already in progress, it follows that run. Add `--new` to start another one.

Use the model. One `qa` session owns functional QA: Explore, Author, Heal, and Promote on a ticket, or E2E heal-only on phase-1. Do not spawn subagents. Procedure: `.agents/skills/lexful-autonomous-agent-qa/SKILL.md` and `.agents/prompts/qa.md`. A case the walk never reached is a gap, not a product bug. A gap the ticket or its pull request requires, or leftover fixtures named in the UX audit, keeps the run in revision. The server runs Playwright and writes `qa-result.json` and `report.md` in the same run folder. UI/UX audit uses the `ux-auditor` agent when `QA_RUN_UX_AUDIT=true`. Before the run is sealed, passing journeys are copied into `e2e test cases` using `playwright/test-outcomes.json`. The default Stytch session for `STYTCH_PERSONA` is `runs/cache/stytch/session.json`. `node scripts/persona.mjs support` or `viewer` signs in as that role and writes `runs/cache/stytch/<persona>.json` without replacing the default. Set `BEDROCK_API_KEY` in `.env`. The container maps it to `AWS_BEARER_TOKEN_BEDROCK` for OpenCode.

`npm run e2e` runs E2E User Journey TCs on demand. That run does not call Linear. With `QA_PHASE1_ON_START=true` (default), `npm run ticket` queues E2E before the ticket; `false` skips E2E for tickets. Container start never auto-runs E2E.

Stay inside this directory. Do not read `~/Downloads`, `~/Desktop`, `~/Documents`, or any other checkout. Do not clone `docu-stack`.

- Linear access is the named ticket plus the parent, children, and related issues on that ticket.
- GitHub access is the pull requests that mention that ticket, and only the files in those pull requests.
- Do not commit `.env`, `auth-state.json`, or `runs/`.
