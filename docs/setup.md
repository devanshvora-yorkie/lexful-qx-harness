# Setup: the QA machine, the trigger and what Lexful configures

This is the whole deployment: one machine that runs the harness, one GitHub workflow in the
harness repo that runs it, and one workflow in `docu-stack` that tells it when UAT has a new build.

Status of each part is marked **built** (in this repo today) or **to build**.

## 1. How it fits together

```text
docu-stack (Lexful-ai/docu-stack)                 qa-harness (Lexful-ai/qa-harness)
─────────────────────────────────                 ──────────────────────────────────
merge to main
 └─ "docu-app - Build & Deploy UAT" succeeds
    └─ qa-notify.yml  (ubuntu-latest, seconds)
       sends repository_dispatch ───────────────▶  qa-on-uat-deploy.yml
       event: uat-deployed, sha = deployed commit   runs-on: [self-hosted, qa-harness]
                                                     └─ QA machine (this repo, build.sh --runner)
                                                        docker compose run harness
                                                        python -m app.cli --sha <sha>
                                                        └─ resolves the PR and LEX ticket
                                                        └─ preflight, E2E stage, Feature
                                                           Specific TCs, UX audit, report
                                                        └─ runs/ on the machine
```

- **The trigger is `workflow_run`, not `deployment_status`.** UAT deployments are created inside the
  "… - Build & Deploy UAT" workflows. GitHub does not start a new workflow for an event made with the
  workflow's own token, so a `deployment_status` trigger may never fire. `workflow_run` fires whenever
  the named workflow finishes.
- **The event goes to the harness repo, not to a job in docu-stack.** The QA machine is registered to
  `Lexful-ai/qa-harness` only. No docu-stack workflow, and no pull request from a fork, can run on it.
  The harness secrets stay on the machine.
- **Only the commit is sent.** The harness works out the pull request and the ticket from that commit
  (`scripts/resolve-trigger.mjs`). docu-stack does not need to know about tickets.

### What starts when, and what stays running

| Piece | Lifetime | Started by |
|---|---|---|
| GitHub Actions runner (a service on the QA machine, label `qa-harness`) | always on; waits for jobs | `./build.sh --runner` (launchd on macOS, systemd on Linux) |
| Harness API container (`harness`, port 8787) | always on; optional for deploy runs | `./build.sh` |
| **Run container** (`docker compose run --rm harness python -m app.cli --sha <sha>`) | **one deploy, then it exits and is removed** | the workflow, for each deploy |

So nothing has to be started by hand after a deploy. The workflow pulls the latest harness code, rebuilds
the image if it changed, starts a fresh container with the same `.env`, `runs/` folder and settings the API
container uses, runs the one deploy to the end, and removes the container. The QA machine only needs the
runner service and Docker to be up.

To turn it off, for example while the machine is serviced, stop the runner service. Queued deploys wait
(GitHub holds a queued job for up to 24 hours) and start when it is back:

```bash
cd ~/actions-runner-qa-harness      # QA_RUNNER_DIR if you changed it
./svc.sh stop                       # Linux: sudo ./svc.sh stop
./svc.sh start
./svc.sh status
```

**Why there is no fallback to GitHub-hosted runners.** A generic runner guide often routes a job to
`ubuntu-latest` when the self-hosted runner is offline. That does not fit here: the harness needs the QA
machine's `.env` (UAT, Linear, GitHub and Bedrock keys), its Docker image and its disk. A GitHub-hosted
runner has none of them, and the keys must not be put in GitHub. When the machine is off, deploys wait.

### Which UAT deploys start QA

docu-stack has one workflow per component, named `<component> - Build & Deploy UAT`. Each runs on a push
to `main` that changes that component's paths, and deploys to the GitHub environment `<component>-uat`.
The harness reads those same environments to decide whether a merged pull request is already on UAT.

| Workflow | GitHub environment | Starts QA by default | What it ships |
|---|---|---|---|
| docu-app - Build & Deploy UAT | `docu-app-uat` | **yes** | the main web app (`apps/docu-app`) |
| docu-service - Build & Deploy UAT | `docu-service-uat` | **yes** | the API behind it (`services/docu-service`) |
| platform-app - Build & Deploy UAT | `platform-app-uat` | optional | platform web app |
| analytics-app - Build & Deploy UAT | `analytics-app-uat` | optional | analytics web app |
| workflow-service - Build & Deploy UAT | `workflow-service-uat` | optional | workflow service |
| indexer-service - Build & Deploy UAT | `indexer-service-uat` | optional | search indexing |
| audit-service - Build & Deploy UAT | `audit-service-uat` | optional | audit events |
| data-integration-service - Build & Deploy UAT | `data-integration-service-uat` | optional | data integration |
| data-query-service - Build & Deploy UAT | `data-query-service-uat` | optional | data queries |
| data-sync-service - Build & Deploy UAT | `data-sync-service-uat` | optional | data sync |
| docu-etl - Build & Deploy UAT | `docu-etl-uat` | optional | ETL jobs |
| extension-app, packages | none | no | not deployed to UAT by a deploy workflow |

The harness tests the docu-app pages (search, assets, documents), so docu-app and docu-service are the
two that matter. Add a backend only when its change can show in those pages.

The choice is made in two places, and a deploy must pass both:

1. **docu-stack** `qa-notify.yml`: the `workflows:` list decides which workflow finishes send an event.
   A ready-to-copy file is in [docu-stack/qa-notify.yml](docu-stack/qa-notify.yml).
2. **qa-harness** repository variable `QA_UAT_ENVIRONMENTS` (Settings > Secrets and variables > Actions >
   Variables), a space-separated list such as `docu-app-uat docu-service-uat platform-app-uat`. When it is
   not set the list is `docu-app-uat docu-service-uat`. The harness repo can change the list by itself,
   without a change in docu-stack. A manual run (a sha, pull request or ticket) ignores the list.

**One merge, two events, one run.** A merge that changes both `apps/docu-app` and `services/docu-service`
starts both deploy workflows, which send two events with the same commit. The harness runs a commit once:
the second event finds the first run and ends with `skipped`. To test the same commit again, run the
workflow by hand with **again** ticked (or `--again` on the command line).

## 2. What you need

On the QA machine:

| Need | Why |
|---|---|
| macOS or Linux, always on, on a network that reaches `e2e-test.uat.lexful.net`, `api.uat.lexful.net`, GitHub, Linear and AWS Bedrock | the run calls all of them |
| Docker Desktop (macOS) or Docker Engine with Compose v2 (Linux) | the harness image |
| `git`, `curl` | `build.sh` |
| GitHub CLI `gh`, logged in as an account with **admin** on `Lexful-ai/qa-harness` | registers the runner (only with `--runner`) |
| Disk: about 20 GB for the image and `runs/` | the image is large (Playwright browsers); `runs/` grows until retention is built |

In the repos:

| Where | What |
|---|---|
| `Lexful-ai/qa-harness` | this code, on `main`, with `.github/workflows/qa-on-uat-deploy.yml` |
| `Lexful-ai/docu-stack` | `qa-notify.yml` (below) and the secret `QA_HARNESS_DISPATCH_TOKEN` |

Keys and accounts (filled into `.env` on the QA machine only, never in GitHub or in chat):

| Key | From |
|---|---|
| `STYTCH_ORGANIZATION_ID`, `STYTCH_ADMIN_EMAIL`, `STYTCH_ADMIN_PASSWORD` | a UAT admin test account (Lexful) |
| `STYTCH_SUPPORT_*`, `STYTCH_VIEWER_*` | optional; support and viewer test accounts (Lexful) |
| `LINEAR_API_KEY` | a Linear API key with read access to the LEX team |
| `GITHUB_TOKEN` | a token that can read `Lexful-ai/docu-stack` pull requests and deployments |
| `BEDROCK_API_KEY` | an AWS Bedrock API key (whose AWS account pays for the model calls) |

## 3. Setting up the QA machine

From a clone of `Lexful-ai/qa-harness`:

```bash
git clone https://github.com/Lexful-ai/qa-harness.git
cd qa-harness
./build.sh          # first run: creates .env and lists the empty keys
# fill the keys in .env, then:
./build.sh          # checks the tools and keys, builds the image, starts the API on 127.0.0.1:8787
./build.sh --runner # registers this machine as the runner labelled qa-harness
```

What `build.sh` does, in order:

1. Checks docker, compose v2, git and curl. Nothing is installed for you.
2. Creates `.env` from `.env.example` on the first run, with mode 600.
3. Checks that the required keys are set. It prints only the names of empty keys.
4. Creates `HARNESS_DEPLOY_SECRET` in `.env` if it is empty. With it, a web page or a process on the
   machine cannot start or cancel runs, and the agents (which never get the secret) cannot either.
   The scripts in the container send it for you. See [security.md](security.md).
5. Builds the image (`docker compose build harness`) and restarts the API container, so new code and
   a new `.env` take effect. It refuses while a run is in progress.
6. Waits for `http://127.0.0.1:8787/health`.
7. With `--runner`: downloads the current GitHub Actions runner for this machine, registers it to
   `Lexful-ai/qa-harness` with the label `qa-harness`, writes `QA_HARNESS_DIR` into the runner's `.env`
   and installs it as a service (launchd on macOS, systemd on Linux) so it survives reboots.

Other options: `./build.sh --check` (checks only, changes nothing), `./build.sh --update` (pulls first).

To update the harness later: `./build.sh --update`. The workflow also pulls and rebuilds before each run.

**Two things `build.sh` cannot do for you:** the Docker Desktop app must start at login (macOS
Settings > General > Login Items), and the machine must not sleep (System Settings > Energy, or `caffeinate`).
A runner that is asleep leaves deploy runs queued; GitHub holds a queued job for up to 24 hours.

## 4. Triggering a run

### By hand (test first)

In GitHub: **Actions > QA a UAT deploy > Run workflow**, with a full commit sha, or a pull request
number, or a ticket. Or from a terminal:

```bash
gh workflow run qa-on-uat-deploy.yml -R Lexful-ai/qa-harness -f sha=<40-char sha>
gh workflow run qa-on-uat-deploy.yml -R Lexful-ai/qa-harness -f pr=2263
gh workflow run qa-on-uat-deploy.yml -R Lexful-ai/qa-harness -f sha=<40-char sha> -f again=true   # even if that commit was tested
```

Or on the QA machine, without GitHub: `docker compose exec harness npm run ticket -- --pr 2263`.

### After a UAT deploy (needs the docu-stack workflow)

`qa-notify.yml` in `docu-stack` (the draft is in section 5) sends a `uat-deployed` event with the
deployed commit. The harness workflow runs the QA for that commit. It needs no other input.

## 5. What to ask Lexful to configure

Send this to whoever owns `Lexful-ai/docu-stack` and the Lexful org settings.

**a. A notify workflow in docu-stack.** Add [docu-stack/qa-notify.yml](docu-stack/qa-notify.yml) from this
repo as `.github/workflows/qa-notify.yml`. It listens for the UAT deploy workflows in the table above, and
sends the deployed commit and the workflow name to `Lexful-ai/qa-harness` when one succeeds on `main`. It
starts with docu-app and docu-service; uncomment the others you want. Ask which backends matter.

**b. A dispatch token.** A fine-grained personal access token, or better a GitHub App, owned by a
Lexful admin account, with access to **only** `Lexful-ai/qa-harness` and the permission
**Contents: read and write**. Store it as the secret `QA_HARNESS_DISPATCH_TOKEN` in docu-stack
(Settings > Secrets and variables > Actions). Set an expiry and a rotation date.

**c. Confirm the deploy workflows mean "live".** The QA runs when a deploy workflow succeeds. Please
confirm that success means the new build is serving UAT, and tell us if a deploy can succeed and be
rolled back in the same run.

**d. Allow the QA machine through CloudFront.** UAT answers `403 Request blocked` in bursts from
automated traffic. Ask Lexful to allow the QA machine's public IP (or a request header we send) in
the WAF rules for `e2e-test.uat.lexful.net`. This is the biggest single fix for the blocked runs we
saw. Tell us the IP so we can give it to you.

**e. Test accounts.** A UAT admin account (and optionally support and viewer) in organization
"E2E Demo", with the Stytch credentials sent out of band, not in GitHub or chat.

**f. Repo access for the runner.** An admin of `Lexful-ai/qa-harness` runs `./build.sh --runner`
(or approves a registration token). Branch protection on `main` of `qa-harness`, so a runner-run
workflow can only run code that was reviewed.

**g. Linear.** A read-only API key for the LEX team now. Write access (comments and bug tickets)
comes later, and needs its own decision.

## 6. What is built and what is not

| Part | State |
|---|---|
| Run from a PR number, a ticket, or a deploy commit (`--pr`, `--ticket`, `--sha`) | built |
| The ticket is read from the commit's pull request before the run folder is made | built |
| `build.sh` (checks, image, container, `--runner`) | built, the runner registration is not yet tested on a real machine |
| `qa-on-uat-deploy.yml` (manual and `repository_dispatch`, with the environment list `QA_UAT_ENVIRONMENTS`) | built, not yet run on the runner |
| `qa-notify.yml` in docu-stack | [ready to copy](docu-stack/qa-notify.yml), not yet sent to Lexful |
| One run per deploy commit: no second run when docu-app and docu-service ship the same merge | built (`--sha` skips a commit already accepted; `--again` overrides) |
| A deploy that ships several tickets (one commit per PR, several PRs) | to build; one run covers the commit's first ticket for now |
| Linear: tracking ticket, comment per run, Bug tickets | built, off by default (`QA_LINEAR_LOG`); see [linear-logging.md](linear-logging.md) |
| Keeping `runs/` tidy (retention) | to build |

Known gap in the deployment check: it reads every GitHub environment ending in `-uat`, so a new
component is picked up on its own. But a change to the shared `packages/typescript/ui` names no component, so
those PRs read as "not on UAT" and their runs halt unless `QA_ALLOW_UNDEPLOYED=true`.

## 7. Order of work

1. Push this repo to `Lexful-ai/qa-harness` (done; the personal fork is kept in step).
2. Lexful: items a, b and e. Us: run `./build.sh --runner` on the QA machine, then test the workflow
   by hand with a known sha and a ticket.
3. Lexful: item d (CloudFront), so the runs are not blocked.
4. Turn on `qa-notify.yml`. Watch the first three deploys. Set `QA_UAT_ENVIRONMENTS` if more than docu-app and docu-service should start QA.
5. Switch on `QA_LINEAR_LOG` once the write team and project are agreed. Then build multi-ticket deploys and retention.
