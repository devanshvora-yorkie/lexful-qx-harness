# Lexful UAT Playwright suite

The server starts every run and every agent session. One agent (`qa`) on one model (`OPENCODE_MAIN_MODEL`) does all the work, one phase per session; no session can start a subagent. The server message names the phase. Read `.agents/prompts/qa.md` (the rules every phase shares) and the one phase file it maps to. Do not read the other phase files.

- Run folders are `runs/tickets/<ticket>/<date>_<time>Z_<id>/`; E2E-only runs are under `runs/phase-1/`. Preflight, the Stytch session and the context pack are written there before a session starts, together with `pr-brief.md`, `e2e-coverage.md` and `source-info.md`. `runs/START-HERE.txt` maps the rest.
- The checked-in suite is `e2e test cases/` (E2E User Journey TCs). Feature Specific TCs for a ticket go in the run's `specs/`. Do not rewrite a case `e2e-coverage.md` already lists. Each new test has one type tag (`@positive`, `@negative`, `@edge`) and one suite tag (`@bvt`, `@smoke`, `@sanity`, `@regression`); there is no fixed count.
- A product bug is a wrong result you reproduced; it is written as the bug object in `.agents/skills/lexful-autonomous-agent-qa/references/bug-objects.md`. A case the walk never reached is a gap, not a bug.
- `pr-brief.md` is an index. The full ticket and pull request text and their images are in the run's `context/`; `node scripts/lookup.mjs <ref>` fetches what they name.
- The product repo is a read-only clone under `runs/source/` named in `source-info.md`. Do not clone `docu-stack` yourself.
- Stay inside this directory. Do not read `~/Downloads`, `~/Desktop`, `~/Documents` or any other checkout.
- Linear access is the named ticket plus its parent, children and related issues. GitHub access is the pull requests that mention that ticket, and only the files in those pull requests. Both are already saved in the run. `scripts/lookup.mjs` reaches one hop further, through the server, with a per-run budget.
- Do not commit `.env`, `auth-state.json` or `runs/`.

The full run flow, the files a run writes and the settings are in `docs/run-reference.md`; the secrets model is in `docs/security.md`.
