# Lexful QX Harness

OpenCode QA harness for a Lexful ticket. Preflight signs in, writes a context pack, and the server runs the coordinator. Playwright reports land in `runs/`.

## Run after clone

Docker Desktop (or another engine with Compose v2) is the only install.

```bash
git clone https://github.com/Lexful-ai/qa-harness.git
cd qa-harness
cp .env.example .env
```

Fill these in `.env`. Leave the other values as they are unless the tenant changes.

- `STYTCH_ORGANIZATION_ID`
- `STYTCH_ADMIN_EMAIL`
- `STYTCH_ADMIN_PASSWORD`
- `LINEAR_API_KEY`
- `GITHUB_TOKEN`
- `BEDROCK_API_KEY`

Then:

```bash
docker compose up --build -d
```

`make up` does the same check and start. The API is on [http://127.0.0.1:8787](http://127.0.0.1:8787). Docker publishes that port on this machine only. `.env` is passed into the container as variables and is not mounted into the working directory.

With `LOCAL_MODE=true` the API does not require `HARNESS_DEPLOY_SECRET`. Set `LOCAL_MODE=false` and a secret before exposing the port.

## Feature Specific TCs

From this directory, after the container is up:

```bash
docker compose exec harness npm run ticket -- LEX-2293
docker compose exec harness npm run ticket -- --pr 2263   # the ticket is read from the PR title, branch or body
```

That starts the run and streams the log. Preflight signs in, builds the context pack and checks that the merged PR is deployed on UAT. When `QA_PHASE1_ON_START=true` (default), the run then executes the E2E User Journey TCs against that build as its first stage and keeps the result in its own `e2e/` folder; the log shows those lines, then Feature Specific TCs. Set `QA_PHASE1_ON_START=false` to run the ticket only. Container start never runs E2E. The product repo is fetched on every run and checked out at the commits the deployment record says UAT runs (`source-info.md`). One session walks live UAT, writes a spec step only after it has done that step, and Playwright runs the suite. On a failure the same session fixes the locator, rewrites the step, creates the fixture, or removes a case it never reached. UI/UX audit runs beside Playwright when `QA_RUN_UX_AUDIT=true`; its lines appear in the same log, marked `ux-audit`, and the server checks the rendered `ux-report.html` against the UX kit's report contract (`ux-contract` lines). Set `QA_RUN_UX_AUDIT=false` to stop after functional QA. Before sign-off, the passing journeys are copied into the matching `e2e test cases` folder. The next E2E User Journey run executes those files. `docker compose down` stops the server and keeps the run volume.

Every run folder has one report, `linear-report.md`, written as the comment for the Linear issue, and `linear-report.html`, the same report for a browser with the full test list and the screenshots. It shows what triggered the run (ticket, pull request or UAT deployment), the E2E stage (ran, passed, failed, flaky, the cases updated in place and the cases added to the suite), the ticket's tests (generated, passed, failed and the pass ratio, by type and by suite), the bugs, and the UX audit's suggested changes, with links to `ux-report.html`, `bugs.md` and the screenshots. Each bug in `bugs.md` is written as a ticket: title, severity, environment, steps to reproduce, expected, actual, evidence. A bug is filed only after a fresh session followed its steps and took a screenshot; what it could not reproduce is not filed. Nothing is posted to Linear yet. On the checked-in suite, a failing case is treated as outdated: the heal updates locators, copy and seeded data in `e2e test cases/` in place and records each edit in `e2e test cases/changes.log`. A sealed run is pruned of scratch files; transcripts are kept as `.jsonl.gz`.

A GitHub runner that starts one container per UAT deployment runs the same thing without the server: `python -m app.cli --sha <deployed sha>` runs one run and exits with the verdict. See `docs/github-runner.md`.

The log ends with a `── run summary` block: each phase with its status and time, where the run stopped, the test counts, bugs, findings, hypotheses, UX result, promote result and cost. The same data is in `summary.json` in the run folder.

| Setting | Default | What it does |
|---|---|---|
| `QA_PW_WORKERS` | 3 | Playwright workers: how many browsers hit UAT at once. More workers means more CloudFront 403 blocks |
| `QA_PW_FULLY_PARALLEL` | true | Each test goes to the next free worker, so a long file such as `assets-crud.spec.ts` no longer runs alone on one worker. A file that needs its order declares `test.describe.configure({ mode: 'serial' })` or `'default'` (`search.spec.ts` does). `false` runs one file per worker |
| `QA_MAX_PARALLEL_RUNS` | 1 | Runs at the same time (each gets its own git worktree; the suite is locked) |
| `QA_UX_PARALLEL` | true | UX audit beside Playwright and heal. Its lines are in `run.log` and the terminal, marked `ux-audit` |
| `QA_PLAN_MODEL` | Haiku 5.5 | The plan is its own turn on this model, then the walk continues in the same session; empty = one single turn |
| `QA_VERIFY_FINDINGS` | true | A fresh session reproduces suspected bugs before they are filed |
| `QA_AGENT_RETRIES` | 1 | Resume a session after a dropped connection |
| `QA_AGENT_USER` | qa | OpenCode and Playwright run as this user; empty runs them as root |
| `QA_SESSION_CHECK_MINUTES` | 20 | While a run is active, the server checks every saved Stytch session against the API and signs in again from `.env` when one is dead or near expiry. 0 turns it off |
| `QA_ALLOW_UNDEPLOYED` | false | Run even when the merged PR is not on UAT yet |

Explore and Author run in one `qa` session. Heal starts a new session that reads the run files (set `QA_HEAL_FRESH_SESSION=false` to resume the Explore session). The UX audit also runs in its own session. Promote follows. Entry point: `.agents/prompts/qa.md`. Full procedure: `.agents/skills/lexful-autonomous-agent-qa/SKILL.md` (listing hints in `references/listing-exploration-hints.md`).

Before the coordinator starts, the server writes `e2e-coverage.md` into the run. That file lists the cases already in `e2e test cases` for search, asset crud, and document editing. Author does not write those baselines again. New cases cover the behavior this ticket adds or changes, including a surface that is not one of those three journeys. Each new test is tagged with one type (`@positive`, `@negative`, `@edge`) and one suite (`@bvt`, `@smoke`, `@sanity`, `@regression`). There is no fixed count.

A product bug that remains after Heal is recorded in `bugs.json` and `bugs.md` in the run folder, in the agent's words (skill §8). A skipped, deprecated, or gap test is not filed as a bug, and a failure the heal did not describe as a bug stays an open issue. A gap is a case the walk never reached.

## E2E User Journey TCs

E2E runs as the first stage of every ticket run (`QA_PHASE1_ON_START=true`), stored in that run's `e2e/` folder, or on its own when you start it (`npm run e2e` / `make e2e`). It runs the specs in `e2e test cases` against UAT. No Explore, no new specs, and no Linear call.

One worker runs one run at a time. While another run is in progress, new runs stay **queued**; `run.log` still shows queue lines, and the CLI prints `status queued` until the worker reaches your run. `docker compose logs -f harness` shows the same lines once execution starts (`echo_run`).

Only an E2E run started on its own gets a folder under `runs/phase-1/`. The folder name is the UTC start time and a short id. Start it with:

```bash
make e2e
```

`make phase1` is the same command. If an E2E User Journey run is already queued, the command follows it instead of starting a second one.

`run.log` prints each finished test. A line that says `still in the browser` means a test is running, not that the run has stopped.

A failure is classified by Heal only. Explore and Author are not called, and no new test is written.

- Spec drift is patched in the existing spec or page object: a renamed locator, a locator that matches several elements, or an existing wait that expired while that control was already on the page. The edit is written into `e2e test cases/` on this machine, which is the suite Playwright runs. The same locator is not patched again once it is listed in `e2e test cases/changes.log`. The server appends each heal to that log and, when a file changed, re-runs only the tests that did not pass, up to 3 heals. After the heals, every spec in a folder a heal edited runs once in full.
- A product bug is left in the spec and recorded in `bugs.json` and `bugs.md` in the run folder (the ticket run's `e2e/` folder for the stage). It is not sent to Linear.

Set `QA_PHASE1_ON_START=false` in `.env` to skip the E2E stage when you `npm run ticket`. `npm run e2e` always runs E2E on demand.

Feature Specific TCs still use Linear for the context pack. E2E User Journey TCs do not.

## Where a run is stored

`runs/START-HERE.txt` is the short map. One attempt is one folder, chosen when the run starts. It is never moved or renamed, so a file you have open in an editor stays where it is. A run started from a pull request or a UAT deploy reads its ticket from GitHub first (`scripts/resolve-trigger.mjs`) and starts under that ticket. Only when GitHub names no ticket does it stay under `runs/pull-requests/` or `runs/deploys/<commit>/`. The result (`11 passed, 0 failed, needs revision`) is in `runs/index.json`, `manifest.json` and `linear-report.md`, not in the folder name:

```text
runs/tickets/LEX-3642/2026-11-03_0928Z_bc40/
  linear-report.md      the one report: the Linear comment
  linear-report.html    the same report for a browser, with every test and the screenshots
  ux-report.html        UI/UX audit, interactive
  bugs.json, bugs.md    the bugs, each written as a ticket; bug-evidence/ holds their screenshots
  run.log, summary.json the timeline, ending with the run summary (phases, counts, cost)
  manifest.json         the run record, including what triggered it
  qa-result.json        functional pass/fail counts and verdict
  playwright/test-outcomes.json   every test, its tags and its final result
  FEATURE.md, feature-map.md, explore/, specs/   what was tested and how
  coverage.json, hypotheses.json, triage-N.json, verify.json   the agent's hand-off and the heal notes
  ux-findings.json, ux-scorecard.json            the UX audit's findings and score
  affected/test-outcomes.json   the checked-in cases the diff touches, and their result
  e2e/                  the E2E stage: qa-result.json, playwright/test-outcomes.json, triage, bugs
  opencode/*.jsonl.gz   transcripts of explore and author, the heals and verify

runs/phase-1/2026-11-03_1105Z_49ea/
  an E2E run started on its own: the same report, results, triage and bugs
```

A sealed run keeps only that record. Raw Playwright output, probe logs, prompts and scratch are removed once the bugs hold their screenshots (`server/app/prune.py`). A halted or failed run keeps everything so it can be resumed or debugged.

E2E User Journey TCs do not get `specs/` or `explore/`. A locator heal is written into `e2e test cases/`, not into the run folder. Feature Specific TCs stay in that attempt's `specs/` folder. The journeys copied at sign-off are listed in `promoted.json` and live under `e2e test cases/`.

Older attempts keep the counts in their folder name. `runs/regression/` and `runs/LEX-*/` are links to those folders for attempts that already existed. `runs/index.json` is the list the server uses. The default Stytch session is `runs/cache/stytch/session.json`, for the account named by `STYTCH_PERSONA` (`admin` unless that value changes). Do not commit `.env` or that file.

A case that has to run as another role signs in without changing the default:

```bash
node scripts/persona.mjs support
node scripts/persona.mjs viewer
```

Each command writes `runs/cache/stytch/<persona>.json`. A spec selects it with `injectAuthCookies(page.context(), 'support')`. A spec that omits the argument stays on the default session. The server signs in every named persona before Playwright. Inside a ticket run the same command is how Explore looks at that role before Author writes the case.

`runs/` is gitignored.

## Run specs again

The spec runner reuses the Stytch session and targets live UAT (`QA_ENV_URL`, default `https://e2e-test.uat.lexful.net`). Pass a spec file or a folder.

Watch it on this Mac. A Chrome window opens, slowed down enough to follow:

```bash
node scripts/specs.mjs --headed runs/LEX-2293/<run-id>/specs
node scripts/specs.mjs --headed runs/LEX-2293/<run-id>/specs/asset-related-items-read.spec.ts
```

Headless, inside the container:

```bash
docker compose exec harness node scripts/specs.mjs runs/LEX-2293/<run-id>/specs
```

`--headed` inside Docker uses a virtual display, so the window does not appear on the Mac. Run the command on the host when you want to see it. Results are written back into that run's `playwright/` folder when the path is already inside a run. A path that is not inside a run gets a new folder under `runs/manual/<run-id>/`.

## Checked-in e2e suites

Each folder under `e2e test cases/` is one suite: `FEATURE.md`, the spec files, and the page objects for that suite. Nothing in a suite imports a page object from outside its folder. Auth is `auth-helper.ts`. Paths such as `/docs/assets` are resolved against `QA_ENV_URL`.

With the container up:

```bash
docker compose exec harness node scripts/specs.mjs "e2e test cases/search"
docker compose exec harness node scripts/specs.mjs "e2e test cases/asset crud"
docker compose exec harness node scripts/specs.mjs "e2e test cases/document editing"
```

Watch them on this Mac. A Chrome window opens:

```bash
node scripts/specs.mjs --headed "e2e test cases/search"
node scripts/specs.mjs --headed "e2e test cases/asset crud"
node scripts/specs.mjs --headed "e2e test cases/document editing"
```

The image installs Node, Playwright Chromium, the Python server, and OpenCode. On startup the OpenRouter key from the container environment is written into the auth store. `.env` is not mounted into the working directory and is not copied into the image.

## Local process

Use this when you want the server on the host instead of in Docker.

```bash
cp .env.example .env
npm install
npx playwright install chromium
python3 -m venv server/.venv
server/.venv/bin/pip install -r server/requirements.txt
curl -fsSL https://opencode.ai/v2/install | bash -s -- --version 2.0.30 --no-modify-path
opencode auth login
npm run serve
```

`npm run ticket -- LEX-1234` starts a run and follows its log. Do not commit `.env`, `auth-state.json`, or `runs/`.
