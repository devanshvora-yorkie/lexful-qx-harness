# Lexful QX Harness

OpenCode QA harness for a Lexful ticket. Preflight signs in, writes a context pack, and the server runs the coordinator. Playwright reports land in `runs/`.

## Run after clone

Docker Desktop (or another engine with Compose v2) is the only install.

```bash
git clone https://github.com/devanshvora-yorkie/lexful-qx-harness.git
cd lexful-qx-harness
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

## Start a ticket

From this directory, after the container is up:

```bash
docker compose exec harness npm run ticket -- LEX-2293
```

That starts the run and streams the log. Preflight signs in, the explorer explores live UAT, the author writes specs, Playwright runs them (with automated healing if locators drifted), and the UI/UX auditor audits the ticket's screens against Lexful's UX rulebook, 5 lenses, and Fluent/shadcn design standards. `docker compose down` stops the server and keeps the run volume.

## Phase 1 — checked-in suite

Docker queues this before any ticket. It runs the specs already in `e2e test cases` against UAT. No explorer, no new specs, and no Linear call. The path is one argument, quotes included, because the folder name contains a space.

On startup the container signs in, runs that suite, and writes the log under `runs/phase-1/`. The folder name is the UTC start time and, when the run finishes, the pass and fail counts. Follow it with:

```bash
make phase1
```

That is `docker compose exec harness npm run phase1`. If a phase 1 run is already queued, the command follows it instead of starting a second one.

`run.log` prints each finished test. A line that says `still in the browser` means a test is running, not that the run has stopped.

A failure is classified by `qa-healer` only. The explorer and the author are not called, and no new test is written.

- Spec drift is patched in the existing spec or page object: a renamed locator, a locator that matches several elements, or an existing wait that expired while that control was already on the page. The edit is written into `e2e test cases/` on this machine, which is the suite Playwright runs. The same locator is not patched again once it is listed in `e2e test cases/changes.log`. The server appends each heal to that log and re-runs the suite only when a file changed, up to 3 heals.
- A product bug is left in the spec and recorded in `report.md` and `triage-1.json` in the run folder. It is not sent to Linear.

Set `QA_PHASE1_ON_START=false` in `.env` before `docker compose up` to skip the automatic run. `npm run phase1` still starts one.

A ticket run still uses Linear for the context pack. Phase 1 does not.

## Where a run is stored

`runs/START-HERE.txt` is the short map. One attempt is one folder:

```text
runs/phase-1/2026-10-23_1147Z_f35a_57-passed_2-failed_needs-revision/
  contents.txt          what each file in this folder is
  report.md             final counts and healer notes
  run.log               full log
  qa-result.json        passed, failed, skipped, flaky
  manifest.json         status, model, heal count
  triage-N.json         healer classification for heal N
  heal-N.md             healer note for heal N
  playwright/           results.json, html report, output.log
  opencode/             agent session and healer transcript

runs/tickets/LEX-2293/2026-10-21_1021Z_1722_18-passed_0-failed_perfect/
  report.md             unified report (QA results + UX audit scorecard)
  FEATURE.md            what was observed on UAT
  specs/                spec files written for that ticket
  explore/              browser snapshots
  context-pack.json
  planned-specs.json
  qa-result.json        functional pass/fail counts and verdict
  ux-findings.json      structured UI/UX findings
  ux-scorecard.json     UX scores and advisory verdict
  ux-report.md          detailed 5-lens UI/UX audit report
  before-after/         (optional) Before UAT vs After concept mocks
```

Phase 1 does not get `specs/` or `explore/`. A locator heal is written into `e2e test cases/`, not into the run folder. Ticket specs stay in that attempt's `specs/` folder.

`runs/regression/` and `runs/LEX-*/` are links to those folders for attempts that already existed. `runs/index.json` is the list the server uses. The Stytch session is `runs/cache/stytch/session.json`, for the account named by `STYTCH_PERSONA`. Do not commit `.env` or that file.

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
