# Lexful QA Harness

An AI agent that tests a Lexful change on UAT. Given a ticket or a pull request, it reads the
ticket and the code, walks the feature in the live app, writes Playwright specs, runs them, heals
the specs when the UI has drifted, files the bugs it can reproduce, and writes one report per run.

The harness reads Linear and GitHub. It writes to Linear only when `QA_LINEAR_LOG=true`: a tracking ticket, a comment per run and a Bug ticket per bug, in a separate write team and project ([docs/linear-logging.md](docs/linear-logging.md)). It never writes to GitHub.

## Set up

You need Docker with Compose v2 and the keys in `.env`.

```bash
git clone https://github.com/Lexful-ai/qa-harness.git
cd qa-harness
./build.sh          # creates .env on the first run; fill in the keys it lists, then run again
```

`./build.sh` checks the tools and the keys, builds the image and starts the API on
`http://127.0.0.1:8787`. The keys it requires are `STYTCH_ORGANIZATION_ID`, `STYTCH_ADMIN_EMAIL`,
`STYTCH_ADMIN_PASSWORD`, `LINEAR_API_KEY`, `GITHUB_TOKEN` and `BEDROCK_API_KEY`. `./build.sh --check`
only checks. `./build.sh --update` pulls first. It also creates `HARNESS_DEPLOY_SECRET` in `.env` when it is
empty, and restarts the container so new code and settings take effect. It refuses to restart while a run
is in progress. What protects the keys, and what does not, is in [docs/security.md](docs/security.md).

An older `.env` can be reordered to match `.env.example` with `node scripts/tidy-env.mjs`. It keeps every value, drops keys the harness no longer reads, and leaves the old file as `.env.bak`.

To run the harness from a UAT deploy on a dedicated machine, see [docs/setup.md](docs/setup.md).

## Start, stop and rebuild

All from this folder. `./build.sh` is the normal way in; the rest are the `docker compose` commands it wraps.

| To | Command |
|---|---|
| Build the image and start (or restart) the container | `./build.sh` |
| Pull the latest code first, then build and start | `./build.sh --update` |
| Check the tools and `.env` without changing anything | `./build.sh --check` |
| Start a stopped container | `docker compose up -d harness` |
| Stop it, keeping the container | `docker compose stop harness` |
| Restart it (reloads the Python server code in `server/app/`) | `docker compose restart harness` |
| Recreate it so `.env` changes apply | `docker compose up -d --force-recreate harness` |
| Rebuild the image after `Dockerfile` or `package.json` changes | `docker compose build harness` then the recreate command above (`--no-cache` for a clean build) |
| Stop and remove the container | `docker compose down` |
| Also remove the image | `docker compose down --rmi local` |
| See the status and health | `docker compose ps`, `curl http://127.0.0.1:8787/health` |
| Follow the server log | `docker compose logs -f harness` |
| Open a shell inside | `docker compose exec harness bash` |
| Stop every run now | `docker compose exec harness npm run cancel-runs` |

`scripts/`, `server/app/`, `.agents/`, `opencode.jsonc` and the Playwright config are mounted into the container. Prompt, skill and script edits apply to the next session without a rebuild; Python changes need a restart. `./build.sh` refuses to restart while a run is in progress. The `runs/` and `e2e test cases/` folders live on your disk, so removing the container or the image keeps every run.

## Run a ticket or a pull request

Once the container is up, from this folder:

```bash
docker compose exec harness npm run ticket -- LEX-3642        # a ticket
docker compose exec harness npm run ticket -- --pr 2245       # a pull request; the ticket is read from its title, branch or body
docker compose exec harness npm run ticket -- LEX-3642 --new  # start another run even if one is in progress
docker compose exec harness npm run ticket -- LEX-3642 --resume   # continue a failed run from Playwright
```

The command starts the run and follows its log until it ends. A second run waits in the queue, one
run at a time. The agents work one session at a time and cannot start subagents. To stop everything running now: `docker compose exec harness npm run cancel-runs`.

E2E User Journey TCs (the checked-in regression suite) run on their own with `make e2e`. A ticket run
also starts with them unless `QA_PHASE1_ON_START=false`.

Watch the Chrome window of a spec on your Mac, not in the container:

```bash
node scripts/specs.mjs --headed "e2e test cases/search"
```

## How a run works

1. **Preflight.** Signs in to UAT with the saved Stytch session, saves the full ticket, its comments,
   images and pull requests under the run's `context/` with `pr-brief.md` as the index, and checks that the merged pull request is deployed on UAT. A run stops here if it
   is not (`QA_ALLOW_UNDEPLOYED=true` overrides this). The product repo is fetched read-only at the
   commit UAT runs.
2. **E2E stage** (`QA_PHASE1_ON_START=true`). The checked-in suite runs against that build. Failing
   cases are healed in place in `e2e test cases/`, and every edit is logged in `changes.log`. Product
   bugs are filed in the run's `e2e/` folder.
3. **Explore and author.** One agent session maps the change (`feature-map.md`), walks the feature in
   the live app, and writes specs for each behavior that is new. Each spec step is written only after
   the agent has done that step in the app.
4. **Run and heal.** Playwright runs the new specs. A failure is healed in a fresh session, up to three
   times. Each heal reruns only the tests that have not passed yet, and one final pass runs every spec
   in a folder a heal edited.
5. **UX audit.** The same agent, in its own session, audits the journey beside Playwright and heal and
   writes `ux-report.html`. The server checks that report against the UX kit's contract
   (`.agents/ux/report-contract.md`). The audit may raise a suspected functional defect for verify.
6. **Verify and file bugs.** After the UX audit, a fresh session follows the steps of each suspected
   bug. Only a bug it reproduces is written to `bugs.md`, with its screenshot. Then at most two passing
   journeys may be promoted into `e2e test cases/`; the default is none.
7. **Seal.** The reports are written, the run is recorded in `runs/index.json`, and scratch files are
   pruned. A run is never moved or renamed after it starts.

A verdict is `PERFECT`, `NEEDS_REVISION` or `HALTED`. A case the walk never reached is a gap, not a
bug. A failure the heal did not describe as a bug stays an open issue.

## Where the results are

Each run is one folder under `runs/`, chosen when the run starts:

```text
runs/tickets/LEX-3642/2026-11-03_0928Z_bc40/
  linear-report.md / .html    the one report: trigger, E2E stage, tests, bugs, UX suggestions
  ux-report.html              the UX audit, interactive
  bugs.md, bugs.json          each bug written as a ticket; bug-evidence/ holds the screenshots
  run.log, summary.json       the timeline and the run summary (phases, counts, cost)
  manifest.json, index.json   what triggered the run and its result
  playwright/test-outcomes.json   every test, its tags and its final result
  specs/, FEATURE.md, feature-map.md, explore/   what was tested and how
  e2e/                        the E2E stage, with its own results and bugs
  opencode/*.jsonl.gz         the agent transcripts
```

`runs/START-HERE.txt` is the map. `runs/` is gitignored, and so are `.env` and
`runs/cache/stytch/session.json`. Do not commit them.

A sealed run keeps only that record. A halted or failed run keeps everything, so it can be resumed
or debugged.

## Settings that matter

Set them in `.env`, then restart the container with `docker compose up -d --force-recreate harness`.

| Setting | Default | Effect |
|---|---|---|
| `QA_PW_WORKERS` | 3 | Browsers that hit UAT at the same time. More workers means more CloudFront 403 blocks |
| `QA_PW_FULLY_PARALLEL` | true | Each test goes to the next free worker. `false` runs one file per worker |
| `QA_PHASE1_ON_START` | true | Every ticket run starts with the E2E stage |
| `QA_RUN_UX_AUDIT` | true | Run the UX audit. `false` stops after functional QA |
| `QA_VERIFY_FINDINGS` | true | A fresh session reproduces each bug before it is filed |
| `QA_LINEAR_LOG` | false | Log each finished run to Linear: tracking ticket, run comment, Bug tickets. Needs `LINEAR_WRITE_TEAM_ID` and `LINEAR_WRITE_PROJECT_ID` |
| `QA_REPORT_BASE_URL` | empty | Where run folders are hosted. Empty uploads `ux-report.html` to Linear, which downloads it |
| `QA_ALLOW_UNDEPLOYED` | false | Run a PR that is not on UAT yet |
| `QA_CONTEXT_MAX_IMAGES` | 12 | Images saved from the ticket and its pull requests. Each costs tokens only if the agent opens it |
| `QA_LOOKUP_MAX_TICKETS`, `QA_LOOKUP_MAX_PRS` | 8, 5 | Extra tickets and pull requests the agent may fetch per run with `scripts/lookup.mjs` |
| `QA_MAX_PARALLEL_RUNS` | 1 | Runs at the same time. Each run gets its own git worktree. Keep it at 1 unless you must: with one agent for every phase, the server can only log, not undo, a ticket session's edit to `e2e test cases/` when runs overlap |
| `QA_SESSION_CHECK_MINUTES` | 20 | How often the saved Stytch sessions are checked during a run. 0 turns it off |
| `OPENCODE_MAIN_MODEL` | Haiku 5.5 on Bedrock | The one model every session of the one `qa` agent runs on: explore, author, heal, verify, promote and the UX audit. The top-level `model` in `opencode.jsonc` must name the same id |

## Repository layout

- `server/` the API and the run pipeline (FastAPI, Python)
- `scripts/` helpers the agents and the server call (Node): preflight, ticket, specs, sessions
- `e2e test cases/` the checked-in suite, one folder per area, with `FEATURE.md` and `changes.log`
- `.agents/` the agent prompt, the QA skill (one file per phase), the UX audit skill, and the UX kit
- `docs/run-reference.md` the run flow, the phases and the files a run writes
- `docs/setup.md` deployment: the QA machine, the trigger and what to configure in the product repo
- `docs/linear-logging.md` how a run is written to Linear: the tickets, the comment, E2E bugs, counters and the UX report link
- `docs/security.md` what protects the secrets, what does not, and the risks that remain
- `docs/process-diagram-full-run.html` the architecture and the run flow as a diagram (open it in a browser)
- `docs/deployment_overview.html` the deploy trigger and what Lexful sets up (open it in a browser)
- `docs/architecture-roadmap.md` what the harness is, how it is built, what it does, and where it goes next
- `build.sh`, `Makefile`, `docker-compose.yml`, `Dockerfile` setup and build

## Troubleshooting

- **`UAT blocked … (HTTP 403)` or `Request blocked`.** CloudFront is rate-limiting automated traffic.
  The run retries the navigation. Lower `QA_PW_WORKERS` if it keeps happening.
- **Preflight says the PR is not on UAT.** The deployment record does not show the merge commit on
  any UAT environment yet. Wait for the deploy, or set `QA_ALLOW_UNDEPLOYED=true` for that run.
- **The run is queued.** Another run is in progress. `docker compose logs -f harness` shows the queue.
- **A signed-in session is rejected.** The server signs in again from `.env` while a run is active.
  Check the Stytch keys in `.env` if it keeps failing.
- **The container will not start.** `docker compose logs harness`. The API needs `.env` to exist and
  the required keys to be set.
