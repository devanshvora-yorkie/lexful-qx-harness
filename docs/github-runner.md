# Plan: run the harness on a self-hosted runner after each UAT deploy

Status: plan. Parts marked **exists** are in the harness today; parts marked **to build** are not.
Nothing in the harness writes to Linear or GitHub yet.

## The flow

```text
docu-stack (GitHub)                      the QA PC (self-hosted runner)
───────────────────                      ─────────────────────────────────────────────
merge to main
  └─ "docu-app - Build & Deploy UAT"     
     or "docu-service - Build & Deploy UAT" succeeds
        └─ qa-notify workflow (seconds,  ──repository_dispatch──▶  qa-harness workflow
           ubuntu-latest): env + sha        "uat-deployed"           runs-on: [self-hosted, qa-harness]
                                                                       1. wait for the other app to settle
                                                                       2. list the tickets this deploy shipped
                                                                       3. per ticket: docker run harness
                                                                          python -m app.cli --sha … --ticket …
                                                                       4. runs/ stays on the PC
                                                                       5. post linear-report.md to the ticket
```

## 1. Trigger: `workflow_run`, not `deployment_status`

UAT deployments in `docu-stack` are created inside the "… - Build & Deploy UAT" workflows. GitHub does not
start a new workflow from an event the workflow's own `GITHUB_TOKEN` created (except `workflow_dispatch` and
`repository_dispatch`), so a `deployment_status` trigger may never fire. `workflow_run` fires when a named
workflow finishes, whoever started it.

Add one small workflow to `docu-stack` (the only change there):

```yaml
# docu-stack/.github/workflows/qa-notify.yml
name: Notify QA harness
on:
  workflow_run:
    workflows: ["docu-app - Build & Deploy UAT", "docu-service - Build & Deploy UAT"]
    types: [completed]
jobs:
  notify:
    if: github.event.workflow_run.conclusion == 'success'
    runs-on: ubuntu-latest           # a few seconds of hosted minutes
    steps:
      - name: Tell the harness repo what UAT now runs
        env:
          GH_TOKEN: ${{ secrets.QA_HARNESS_DISPATCH_TOKEN }}
        run: |
          gh api repos/Lexful-ai/qa-harness/dispatches \
            -f event_type=uat-deployed \
            -F "client_payload[sha]=${{ github.event.workflow_run.head_sha }}" \
            -F "client_payload[workflow]=${{ github.event.workflow_run.name }}" \
            -F "client_payload[run_url]=${{ github.event.workflow_run.html_url }}"
```

`QA_HARNESS_DISPATCH_TOKEN` is a fine-grained token (or a GitHub App) with **Contents: read and write** on
`Lexful-ai/qa-harness` only. That is all `docu-stack` holds.

**Why dispatch to the harness repo instead of running the QA job in `docu-stack`:** the PC is then registered to
the private harness repo only. No `docu-stack` workflow, and no pull request from a fork, can ever be scheduled on
it, and the harness secrets never leave the PC. The alternative, an org-level runner group limited to selected
`docu-stack` workflows, saves the token but puts the PC one misconfigured `runs-on:` away from untrusted jobs.

## 2. The runner on the PC

Recommended: the native runner as a service under a dedicated user, which is the simplest to register and survive
reboots. A Docker-based runner (the guide's approach) works too, with three corrections:

1. **Registration.** As far as I know, `ghcr.io/actions/actions-runner` ships the runner binary but no entrypoint
   that registers from `GH_TOKEN`/`GITHUB_REPOSITORY` (that is what community images add). Verify this first. If so,
   the container needs a start script: get a registration token with the PAT
   (`POST /repos/Lexful-ai/qa-harness/actions/runners/registration-token`), run
   `./config.sh --url … --token … --labels qa-harness --name qa-pc-01 --unattended --replace`, then `./run.sh`.
2. **Paths.** With `/var/run/docker.sock` mounted, `docker run -v <path>` in a job is resolved on the **host**.
   Mount the work directory at the same path inside and outside (`/srv/qa-runner/_work:/srv/qa-runner/_work`,
   `RUNNER_WORKDIR=/srv/qa-runner/_work`), and give `docker run` host paths for `runs/` and the env file.
3. **No fallback to `ubuntu-latest`.** The guide's Part 2 routes jobs to GitHub-hosted runners when the PC is off.
   For QA that is wrong: the run needs the PC's `runs/` volume, Stytch session cache, product clone and secrets.
   When the PC is off, the job stays queued (GitHub keeps it up to 24 hours) and starts when the runner is back.

Either way: the runner user is in the `docker` group, which is root on that PC. Use a machine or VM that does
nothing else, keep the harness env file at `/etc/qa-harness/harness.env` mode `600`, and register the runner to
`Lexful-ai/qa-harness` only.

## 3. The harness job

```yaml
# qa-harness/.github/workflows/qa-on-uat-deploy.yml
name: QA after UAT deploy
on:
  repository_dispatch:
    types: [uat-deployed]
  workflow_dispatch:                       # run by hand: a sha, optionally a ticket
    inputs:
      sha: { required: true }
      ticket: { required: false }
concurrency:                               # one harness run at a time on the PC; never cancel a running one
  group: qa-harness
  cancel-in-progress: false
jobs:
  qa:
    runs-on: [self-hosted, qa-harness]
    timeout-minutes: 300
    env:
      SHA: ${{ github.event.client_payload.sha || inputs.sha }}
    steps:
      - uses: actions/checkout@v4          # the harness at main
      - name: Build the harness image (cached layers; seconds when nothing changed)
        run: docker build -t lexful-qx-harness:ci .
      - name: Let the other component finish deploying
        run: sleep 600                     # docu-app and docu-service often deploy minutes apart
      - name: QA each ticket this deploy shipped
        run: |
          for ticket in $(docker run --rm --env-file /etc/qa-harness/harness.env lexful-qx-harness:ci \
                            node scripts/deploy-tickets.mjs --sha "$SHA"); do          # to build, see §4
            docker run --rm --init --shm-size=2g \
              --env-file /etc/qa-harness/harness.env \
              -v /srv/qa-harness/runs:/opt/lexful-qa-opencode/runs \
              -v "/srv/qa-harness/e2e test cases:/opt/lexful-qa-opencode/e2e test cases" \
              lexful-qx-harness:ci \
              server/.venv/bin/python -m app.cli --sha "$SHA" --ticket "$ticket" || true
          done
```

The exit code of each run is `0` PERFECT, `1` NEEDS_REVISION, `2` HALTED, `64` bad arguments (**exists**).
The job does not fail on `1`: the verdict goes to Linear, not to a red check.

## 4. What the harness needs before this works

| Piece | State | What it does |
|---|---|---|
| `python -m app.cli --sha <sha> [--ticket] [--pr]` | exists | one run in a container, then exit with the verdict |
| PR or deploy → ticket before the folder is made | exists | `scripts/resolve-trigger.mjs`; the run starts under `runs/tickets/<ticket>/` and never moves |
| One folder per run, never renamed | exists | result in `runs/index.json` and `manifest.json` |
| Deployment check per changed path | exists, with a gap | `workflow-service-uat` and shared `packages/typescript/ui` changes are not matched to an environment, so those PRs read as "not on UAT" |
| **Tickets in a deploy** | to build | `scripts/deploy-tickets.mjs --sha`: compare the previous successful deploy of that environment with this one (`/compare/<prev>...<sha>`), map each commit to its PR (`/commits/<sha>/pulls`) and each PR to its LEX key, keep PRs that touch that environment's paths. One deploy often carries several PRs and tickets: the last `docu-service-uat` deploy carried #2266 and #2268 and earlier merges |
| **Once per ticket and build** | to build | skip a ticket that already has a finished run on the same deployed commits (docu-app and docu-service fire separately for one merge) |
| **Linear write-back** | to build | after the run is sealed, `scripts/linear-post.mjs <run dir>` in the same container: post `linear-report.md` as a comment on the ticket (`commentCreate`), upload its screenshots (`fileUpload`) and link `linear-report.html`; record the comment id in `linear-posted.json` in the run folder, so a retry edits the comment instead of posting a second one. Behind `QA_LINEAR_WRITE=true`, off by default |
| **Bugs as tickets** | to build, after the comment works | `bugs.json` → `issueCreate` in the team, related to the ticket, ids kept in `linear-posted.json`. Only verified bugs are in `bugs.json` already |
| Retention on the PC | to build | keep the last N runs per ticket, or prune folders older than N days; `runs/source/` and `runs/cache/` stay |
| Heals of `e2e test cases/` | to decide | on the PC the suite is a host folder that heals edit in place (`changes.log`). Bringing those edits back into the repo is manual today |

## 5. Results on the PC

`/srv/qa-harness/runs` is the record:

```text
runs/
  tickets/LEX-3509/2026-11-03_1015Z_ab12/   one run: linear-report.md/.html, ux-report.html, bugs.md, e2e/, …
  pull-requests/  deploys/                  only when GitHub named no ticket
  index.json, START-HERE.txt
  cache/stytch/   source/                   shared by every run, not results
```

Open `linear-report.html` from the folder, or let the Linear comment link to it once write-back exists. If the
team needs the reports outside the PC, add an `actions/upload-artifact` step for `linear-report.*`, `bugs.md`
and `ux-report.html` only; never upload the whole folder (it holds transcripts).

## 6. Order of work

1. Register the runner on the PC (native service, or the Docker runner with the start script) and run the
   workflow by hand (`workflow_dispatch`) with a known sha and ticket. Exists today; proves paths and secrets.
2. Build `deploy-tickets.mjs` and the once-per-ticket check; test with `workflow_dispatch` and the sha only.
3. Add `qa-notify.yml` to `docu-stack` and the dispatch token. From here every UAT deploy of docu-app or
   docu-service starts QA.
4. Build the Linear comment write-back behind `QA_LINEAR_WRITE`, try it on one ticket, then turn it on.
5. Bugs as Linear issues, then retention.

## Decisions to make

- Native runner service or the Docker runner (both work; native is fewer moving parts).
- Which PC, and whether it is always on (queued jobs expire after 24 hours).
- E2E User Journey stage on every deploy (`QA_PHASE1_ON_START=true`, about an hour) or only on a schedule.
- Linear: comment only, or comment plus bug issues; which team and labels for bugs.
