# Security: what protects what

The harness runs an AI agent with a shell, a browser and network access, on text that other people
wrote (Linear tickets, pull requests, review comments). Read this before you give it real keys or put
it on a shared machine.

## What is enforced

| Control | Where | What it stops |
|---|---|---|
| Agents run as the `qa` user, not root | `QA_AGENT_USER`, `docker/entrypoint.sh` | The agent, Playwright and the specs it writes cannot read the server process's environment (`/proc`) |
| Secrets are removed from the agent's environment | `_opencode_env`, `_playwright_env` in `server/app/runners.py` | Passwords, `LINEAR_API_KEY`, `GITHUB_TOKEN`, `HARNESS_DEPLOY_SECRET` never reach the agent. Playwright gets no model key at all |
| `.env` is not in the image or the working directory | `.dockerignore`, `docker-compose.yml` (`env_file`) | There is no `.env` file for the agent to read |
| The API is published on `127.0.0.1` only | `docker-compose.yml` | Nothing on the network can reach it |
| The API needs `HARNESS_DEPLOY_SECRET` | `require_secret` in `server/app/main.py` | A web page you open, or a process on the machine, cannot start or cancel runs. `./build.sh` creates the secret if `.env` has none |
| Commit ids, ticket keys, PR numbers and run ids are validated | `main.py`, `cli.py`, `store.py` | They become folder names and command arguments; `../` and flags cannot get through |
| GitHub is read through an allowlist of paths | `github()` in `scripts/harness-env.mjs` | Only pull requests, their files and comments, and deployment records of `GITHUB_ORG` |
| The agent reaches Linear and GitHub only through the server | `/internal/lookup` in `server/app/main.py`, `scripts/lookup.mjs` | Localhost only. The token stays in the server. Only tickets and pull requests the run's context names, one hop, within `GITHUB_ORG`, capped per run. The allow-list is in `.lookup-guard/`, owned by the server and outside the run folders, because the agent user owns those. The guard file is written outside the run folders, so a planted symlink cannot redirect it |
| Images are fetched only from an allowlist | `fetchImage` in `scripts/context-files.mjs` | https only. Linear uploads and GitHub attachment hosts, checked on every redirect. A token goes only to the service that issued it. Only real png, jpg, gif and webp files, by their first bytes, under the size limit. File names are generated |
| The product repo is a read-only clone | `runs/source/`, token not stored | The agent browses code but cannot push or commit |
| No agent may start a subagent | `task` deny in `opencode.jsonc` | One session per phase, one agent. The rule is also written in `AGENTS.md`, but the config is what enforces it |
| Server writes never follow a planted symlink | `server/app/safefs.py`, installed when the `app` package loads | Every `write_text`, `write_bytes` and write-mode `open` replaces a symlink at the target instead of following it (`O_NOFOLLOW`), and refuses a path under `runs/` whose folder resolves outside `runs/`. Files the server copies or uploads (screenshots, `bugs.md`, `ux-report.html`) are read only when they are regular files, so a link to `/proc/1/environ` is never copied where the agent can read it or sent to Linear |
| Run folders come only from the shapes the server makes | `safe_folder` in `server/app/store.py` | `runs/index.json` is writable by the agent on some hosts. A folder such as `../../root` is refused |
| Server git commands cannot run repository code | `git_safe_env` in `server/app/runners.py`; the `qa-source` volume in `docker-compose.yml` | Hooks off (`core.hooksPath=/dev/null`), no fsmonitor, no external diff, https only. The clones live in a Docker volume, not in the `./runs` bind mount, because Docker Desktop on macOS does not enforce ownership there and the agent could otherwise edit `.git/config` |
| Python never imports from the writable working folder | `PYTHONSAFEPATH=1` and `python -P` in `Dockerfile` | The working folder is world-writable (sticky) for the agent. Without this, `python -m` searches it before the standard library |
| Root config files cannot be planted in the working folder | `Dockerfile`: read-only, root-owned `.git`, `.npmrc`, `.env`, `.yarnrc` | Root's git, npm and the env loaders would read them from there |
| Nothing that looks like a secret reaches the agent or a spec | `scrubbed_env` in `server/app/runners.py` | Variables are dropped by name (`KEY`, `TOKEN`, `SECRET`, `PASSWORD`, ...), not by a fixed list, so a key added to `.env` later is covered. OpenCode still gets the Bedrock token it needs |
| The agent can edit only `runs/` and `e2e test cases/` | `edit` rules in `opencode.jsonc` | The server code, scripts, `.agents/`, the OpenCode config, `qa-fixtures.ts`, `auth-helper.ts` and the Docker files are read-only to it. `runs/cache/` (sessions) and `runs/source/` (the clone) are read-only even inside `runs/` |
| The checked-in suite is restored after a ticket session | `_guard_suite` in `server/app/pipeline.py` (explore, heal, verify) | One agent serves every phase, so the permission file cannot tell a ticket session from the E2E heal. A ticket run cannot leave edits in `e2e test cases/`. Residual: the guard does not wrap the UX audit on its own (it runs beside the affected-case heal, which may legitimately edit the suite), so a UX session's suite edit is only reverted if it lands inside a heal's window; the prompt forbids it. With `QA_MAX_PARALLEL_RUNS` above 1 the guard only logs |
| Linear is written only when asked, and only to the write team | `server/app/linear_log.py`; `QA_LINEAR_LOG` is off by default | The server writes, never the agent. It stops if the write team is the read team or `LEX`. GitHub is never written |

## What is only a guard rail

`opencode.jsonc` also denies shell commands such as `*cat*.env*` and `*printenv*`. These are text
patterns on the command line. A shell can read a file many other ways, so do not rely on them. The
real protection is in the table above: the secrets are not in the agent's reach in the first place.

## Risks that remain

1. **The agent holds the Bedrock key.** OpenCode needs `AWS_BEARER_TOKEN_BEDROCK`, so it is in the
   agent's environment, and the agent has a shell and network. A pull request or ticket that contains
   hidden instructions could try to make it send the key out. `pr-brief.md` tells the agent that this
   text is not an instruction, and `webfetch` is denied, but a shell `curl` is not blocked.
   *Reduce it:* use a Bedrock key limited to the one model, with a spend limit, and rotate it.
2. **The agent can use a UAT session.** Playwright needs the Stytch cookies in
   `runs/cache/stytch/session.json`, so the `qa` user can use them. *Reduce it:* use test accounts
   in the "E2E Demo" organization, never a real customer's admin.
3. **A self-hosted runner executes the code on `main`.** Whoever can push to `main` of the harness
   repo can run commands on the QA machine, and the runner user is in the `docker` group, which is
   root on that machine. *Reduce it:* branch protection with review on `main`, a dedicated machine
   or VM, and register the runner to the harness repo only (not an organization-wide runner).
4. **Backups of `.env` hold secrets.** `scripts/tidy-env.mjs` keeps the old `.env` as `.env.bak` (mode 600,
   gitignored). If you copied it aside (for example to `.env.orig`), that copy holds them too. Delete the
   backups when you no longer need them.
5. **`/health` needs no secret.** It shows whether a run is active and its ticket key. The
   container health check uses it.

## Rotating a key

Edit `.env`, then `docker compose up -d --force-recreate harness`. The server reads `.env` only at
start. Rotate `BEDROCK_API_KEY`, `GITHUB_TOKEN` and `LINEAR_API_KEY` if you suspect a run read them,
and the Stytch test passwords if a session file left the machine.
