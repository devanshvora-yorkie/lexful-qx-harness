# Lexful UAT Playwright suite

Start Feature Specific TCs from the server. Preflight, the Stytch session, and the context pack are written under `runs/tickets/<ticket>/<date>_<time>Z_<id>/` before OpenCode starts. Specs for that attempt go in that folder's `specs/` directory. The checked-in suite lives in `e2e test cases/`. E2E User Journey TCs are `runs/phase-1/`. `runs/START-HERE.txt` maps the rest.

```bash
npm run serve
npm run ticket -- LEX-3371
```

`npm run ticket` starts Feature Specific TCs and prints `run.log` until it finishes. If that ticket is already in progress, it follows that run. Add `--new` to start another one.

Every step uses Claude Haiku 5.5 on Amazon Bedrock in us-east-1 (`us.anthropic.claude-haiku-5-5`). `qa` coordinates Feature Specific TCs. The steps are Explore (`qa-explorer`), Author (`qa-author`), and Heal (`qa-healer`). The server runs Playwright and writes `qa-result.json` and `report.md` in the same run folder. UI/UX audit runs after functional QA only when `QA_RUN_UX_AUDIT=true`. The Stytch session for `STYTCH_PERSONA` is the single file `runs/cache/stytch/session.json`. Set `BEDROCK_API_KEY` in `.env`. The container maps it to `AWS_BEARER_TOKEN_BEDROCK` for OpenCode.

`npm run e2e` runs E2E User Journey TCs: the checked-in specs in `e2e test cases` against UAT. That run does not call Linear. Heal patches a changed locator in `e2e test cases/` and writes a product bug into `runs/phase-1/`. With `QA_PHASE1_ON_START=true`, the same per-test lines are printed on the harness process.

Stay inside this directory. Do not read `~/Downloads`, `~/Desktop`, `~/Documents`, or any other checkout. Do not clone `docu-stack`.

- Linear access is the named ticket plus the parent, children, and related issues on that ticket.
- GitHub access is the pull requests that mention that ticket, and only the files in those pull requests.
- Do not commit `.env`, `auth-state.json`, or `runs/`.
