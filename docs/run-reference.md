# Run reference

How one run moves through the harness and which files it writes. `README.md` is the overview and `docs/setup.md` covers deployment; this page is the detail the agents and the server share.

## Triggers and folders

One trigger, one run: `POST /run/<ticket>`, `POST /run/pr/<n>` (or `npm run ticket -- --pr <n>`), `POST /trigger/uat-deploy` (`sha`, `pr`, `ticket`) or, without the server, `python -m app.cli --sha <sha>` for a container started per UAT deploy (docs/setup.md). The run records its trigger in `manifest.json`. A PR or deploy trigger is resolved to its ticket before the folder is made, so the run starts under `runs/tickets/<ticket>/<date>_<time>Z_<id>/`. A run folder is never moved or renamed; its result is in `index.json` and `manifest.json`. `runs/START-HERE.txt` maps the rest.

`npm run ticket -- LEX-3371` starts Feature Specific TCs and prints `run.log` until it finishes. If that ticket is already in progress it follows that run; `--new` starts another one.

`npm run e2e` (or `make e2e`) runs E2E User Journey TCs on their own, in a folder under `runs/phase-1/`. That run does not call Linear. With `QA_PHASE1_ON_START=true` (default) every ticket run starts with the E2E User Journey stage after preflight, against the same build, and keeps it in that run's `e2e/` folder; a ticket never creates a separate phase-1 run. `false` skips the stage. Container start never auto-runs E2E.

## Agent and phases

One agent (`qa` in `opencode.jsonc`) on one model (`OPENCODE_MAIN_MODEL`) runs every session. Nothing is delegated: `opencode.jsonc` denies the `task` tool, so no session can start a subagent. A session is one phase, named in the server message (`Phase: <name>`). The agent reads `.agents/prompts/qa.md` (the rules every phase shares) and the one phase file it maps to:

| Phase | Session | Phase file |
|---|---|---|
| `explore+author` | Brief, feature map, hypotheses, walk, API probes, specs | `phases/explore-author.md` |
| `heal` | New session after Playwright fails on the ticket's specs; reads the run files, not the walk | `phases/heal.md` |
| `e2e-heal` | Checked-in suite failed against UAT: patch outdated cases in place | `phases/e2e-heal.md` |
| `affected-heal` | Checked-in cases that ran beside a ticket and failed | `phases/e2e-heal.md` |
| `verify` | Fresh session reproduces each suspected bug before it is filed | `phases/verify.md` |
| `promote` | Copy at most two passing journeys into `e2e test cases/` | `phases/promote.md` |
| `ux-audit` | UX audit of the journey (`QA_RUN_UX_AUDIT=true`) | `.agents/prompts/ux-auditor.md` |

The phase files live in `.agents/skills/lexful-autonomous-agent-qa/phases/`. The E2E heal reads none of the ticket procedure. A ticket session may not change `e2e test cases/`: the server puts the suite back if one does. Only `e2e-heal`, `affected-heal` and `promote` may edit it. A dropped model connection resumes the session once (`QA_AGENT_RETRIES`). `POST /runs/cancel-all` stops the processes of a running run.

## Files in a run

Preflight, the Stytch session and the context pack are written before OpenCode starts. The server also writes `e2e-coverage.md`: the cases the checked-in suite already runs for search, asset crud and document editing. The agent must not rewrite a case that file lists. Specs for the remaining behavior go in the run's `specs/` directory. Each new test has one type tag (`@positive`, `@negative`, `@edge`) and one suite tag (`@bvt`, `@smoke`, `@sanity`, `@regression`). There is no fixed count.

- `context/` holds everything preflight read, in full, with no model involved: `ticket.md`, `connected-<KEY>.md`, `pr-<n>.md`, `links.md`, and `attachments/` with the images of the ticket and its pull requests (up to `QA_CONTEXT_MAX_IMAGES`). `context/index.json` lists them and the references found.
- `pr-brief.md` is the index of that folder: every acceptance criterion (AC1...), a short view of comments and pull requests, **Read before planning** (a criterion names it, the ticket shows it, or it was said after the merge), and pointers. It has size budgets because the model re-reads it on every tool call. `history.md` lists earlier runs of the ticket.
- `node scripts/lookup.mjs <ref>` fetches a ticket or pull request the context names but did not save. It asks the server on localhost, which holds the tokens, enforces the allow-list and the per-run caps (`QA_LOOKUP_MAX_TICKETS`, `QA_LOOKUP_MAX_PRS`), and returns the text; the agent's script saves it under `context/lookups/`. There is no second hop. `references/context.md` tells the agent what to open. `context/` is removed when the run is sealed, like `context-pack.json`.
- Every run fetches the product repo and checks out the commits the deployment record says UAT runs. The server keeps a read-only clone under `runs/source/` (PR branches fetched as `pr-<n>`, token never stored) and names it in `source-info.md`. The agent browses it with Read, Grep, Glob, and `git log|show|blame|grep|diff`, and writes `feature-map.md` before it plans tests.
- A backend ticket also uses the API lane: `node scripts/api-probe.mjs [--persona all] GET /v1/...` calls UAT with the saved sessions. Findings go in `api-findings.json` (each with an `id`); the server files them in `bugs.md` even when every test passes.
- The agent writes `feature-map.md`, `FEATURE.md`, `explore/flow.md`, `hypotheses.json` (every Risk tried), `coverage.json` (every AC mapped to test ids, a gap, or `na`), `affected-cases.json` (checked-in cases the diff touches) and `planned-specs.json`.
- Specs import `test` from `qa-fixtures.ts`, which records console errors and failed API calls into `playwright/signals.jsonl`. Playwright runs each test on the next free of `QA_PW_WORKERS` workers (`QA_PW_FULLY_PARALLEL`), so every test must pass alone; a describe that cannot declares `test.describe.configure({ mode: 'serial' })`.

## Run flow

Preflight checks the GitHub deployment record and halts when a merged PR is not on UAT (`QA_ALLOW_UNDEPLOYED=true` overrides). The E2E stage runs (and heals) the checked-in suite. `explore+author` writes the specs; the server runs them; a failure is healed in a fresh session, up to `QA_HEAL_ATTEMPTS` times. The UX audit runs beside Playwright and heal; its lines are in `run.log`, marked `ux-audit`. The server scores the findings, renders `ux-report.html` with the UX kit's generator and checks it with `scripts/check_report_contract.py` (`.agents/ux/report-contract.md`); a failing report is an open issue. After heal the server runs the affected cases. Once the UX audit has finished too (it may raise suspected functional defects in `api-findings.json`), a fresh `verify` session reproduces suspected findings (`verify.json`). A failing test whose triage reason starts with `Needs a decision:` is listed in the report for a person: the test and a deliberate product change disagree, and a heal may not change what a test expects. A heal that changes an expectation is recorded in `assertion-edits.json` and keeps the run in revision. Every run ends with a `── run summary` block in `run.log` and `summary.json`: each phase, its status and time, where it stopped, tests, bugs, cost.

A case the walk never reached is a gap, not a product bug. A gap the ticket or its pull request requires, or leftover fixtures named in the UX audit, keeps the run in revision.

## Bugs and the report

The agent writes each defect as the bug object of `references/bug-objects.md` (`triage.json` `bugs[]`, `api-findings.json`); the server does not write bug text and does not file a failure the agent did not describe. Before a bug is filed, a fresh `verify` session follows its steps, saves a screenshot to `bug-evidence/<ref>.png` and returns the steps it used; Playwright's failure screenshot of the affected test is copied there too. A bug the verifier cannot reproduce is not filed; for the checked-in suite it goes back to the next heal as outdated test work. `bugs.json` is the record and `bugs.md` renders each bug as a ticket. `linear-report.md` (and `linear-report.html`) is the one report of a run: the trigger, the E2E stage and its bugs, the ticket's tests by type and suite and its bugs, the UX audit's suggested changes, and links to `ux-report.html` and the screenshots. Nothing is sent to GitHub. With `QA_LINEAR_LOG=true` the sealed run is also logged to Linear; see [linear-logging.md](linear-logging.md).

The E2E heal keeps `e2e test cases/` true to the app: it updates locators, copy and seeded data in place, and a failing case is outdated until the product is shown to be wrong. Before the run is sealed, passing journeys are copied into `e2e test cases/` using `playwright/test-outcomes.json`. A sealed run keeps only its record: the reports, bugs and screenshots, specs, plan and walk notes, `playwright/test-outcomes.json`, the hand-off and heal notes, the E2E stage's results and bugs, and the explore, heal and verify transcripts as `.gz`. Raw Playwright output, probe logs, prompts and other scratch go once the bugs hold their screenshots; the server prunes older runs the same way at start. A halted or failed run keeps everything.

## Sessions and secrets

The default Stytch session for `STYTCH_PERSONA` is `runs/cache/stytch/session.json`. `node scripts/persona.mjs support` or `viewer` signs in as that role and writes `runs/cache/stytch/<persona>.json` without replacing the default. Set `BEDROCK_API_KEY` in `.env`; the container maps it to `AWS_BEARER_TOKEN_BEDROCK` for OpenCode. Recreate the container after changing `.env`. OpenCode and Playwright run as the `qa` user (`QA_AGENT_USER`), so they cannot read the server's secrets. What protects the secrets, and what does not, is in `docs/security.md`.

## Preflight

The server runs `node scripts/preflight.mjs` before any agent starts; an agent never runs it, never calls Linear, GitHub or `/auth/password`, and never reads the credentials. It writes `preflight.json` and `context-pack.json` in the run folder. `"ok": false` halts the run (`HALTED`) and no agent starts. If a folder already holds `preflight.json` with `"ok": true`, it is reused.

| Check | Pass |
|---|---|
| npm packages | `@playwright/test` and `@playwright/cli` are installed |
| Chromium | `npx playwright install chromium` has a browser binary |
| Playwright CLI | `playwright-cli` runs |
| FastAPI | `server/.venv` imports fastapi, uvicorn and pydantic |
| OpenCode | `opencode` is on PATH, the Bedrock key is set, and the configured model is available |
| Env file | `LINEAR_API_KEY`, `GITHUB_TOKEN`, `STYTCH_ORGANIZATION_ID`, and the email and password for `STYTCH_PERSONA` are set |
| Linear | Viewer query succeeds. With a ticket, that issue is fetched |
| GitHub | The token is accepted. Files are loaded only from the pull request diff |
| Stytch | The `STYTCH_PERSONA` session is reused when more than an hour remains and the app accepts it. Otherwise one `POST /auth/password`. The only cookie file is `runs/cache/stytch/session.json` |
| Ticket context | Pack written for that ticket, its connected issues and its PR files. Starting from `--pr` reads that pull request only, takes the LEX key from its title, branch or body, then loads that ticket and its connected issues |

The context pack is the only Linear and GitHub data an agent may use: `ticket`, `connectedTickets` (parent, children, related), `pullRequests[].fileDetails` (the diff), and `primaryPr`.
