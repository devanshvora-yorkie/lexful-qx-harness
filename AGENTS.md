# Lexful UAT Playwright suite

Start Feature Specific TCs from the server. Preflight, the Stytch session, and the context pack are written under `runs/tickets/<ticket>/<date>_<time>Z_<id>/` before OpenCode starts. The server also writes `e2e-coverage.md` there. Author must not rewrite a case that file already lists for search, asset crud, or document editing. Specs for the remaining behavior go in that folder's `specs/` directory. Each new test has one type tag (`@positive`, `@negative`, `@edge`) and one suite tag (`@bvt`, `@smoke`, `@sanity`, `@regression`). There is no fixed count. The checked-in suite lives in `e2e test cases/`. E2E User Journey TCs are `runs/phase-1/`. A product bug is recorded in `bugs.md`. `runs/START-HERE.txt` maps the rest.

```bash
npm run serve
npm run ticket -- LEX-3371
```

`npm run ticket` starts Feature Specific TCs and prints `run.log` until it finishes. If that ticket is already in progress, it follows that run. Add `--new` to start another one.

Use the model. `qa` coordinates Feature Specific TCs. The steps are Explore (`qa-explorer`), Author (`qa-author`), and Heal (`qa-healer`). The server runs Playwright and writes `qa-result.json` and `report.md` in the same run folder. UI/UX audit runs after functional QA only when `QA_RUN_UX_AUDIT=true`. The default Stytch session for `STYTCH_PERSONA` is `runs/cache/stytch/session.json`. `node scripts/persona.mjs support` or `viewer` signs in as that role and writes `runs/cache/stytch/<persona>.json` without replacing the default. Set `BEDROCK_API_KEY` in `.env`. The container maps it to `AWS_BEARER_TOKEN_BEDROCK` for OpenCode.

`npm run e2e` runs E2E User Journey TCs: the checked-in specs in `e2e test cases` against UAT. That run does not call Linear. Heal patches a changed locator in `e2e test cases/` and writes a product bug into `bugs.md` in `runs/phase-1/`. With `QA_PHASE1_ON_START=true`, the same per-test lines are printed on the harness process.

Stay inside this directory. Do not read `~/Downloads`, `~/Desktop`, `~/Documents`, or any other checkout. Do not clone `docu-stack`.

- Linear access is the named ticket plus the parent, children, and related issues on that ticket.
- GitHub access is the pull requests that mention that ticket, and only the files in those pull requests.
- Do not commit `.env`, `auth-state.json`, or `runs/`.
