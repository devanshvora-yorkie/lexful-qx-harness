---
name: 00-harness-preflight
description: Check Linear, GitHub, and Stytch and write the ticket context pack before any test generation. Use when a LEX ticket or pull request is given.
version: 1.0.0
---

# 00-harness-preflight

Deterministic setup. This skill does not call a model to reach Linear, GitHub, or Stytch. The server runs `node scripts/preflight.mjs` and writes the JSON under `runs/<run-id>/`. If that directory already contains `preflight.json` with `"ok": true`, read it and do not run the script again.

## When to run

Run this before `lexful-autonomous-agent-qa` whenever the user names a `LEX-####` ticket or a pull request. Do not explore the app and do not write specs until `preflight.json` has `"ok": true`.

## Procedure

1. If the user message already points at a run directory with `preflight.json` `"ok": true`, do not run the script. Otherwise, from the repo root:

```bash
node scripts/preflight.mjs LEX-####
```

A pull request instead of a ticket:

```bash
node scripts/preflight.mjs --pr 123
```

The script writes `runs/<run-id>/preflight.json` and `context-pack.json`. It installs Chromium, the Playwright CLI, FastAPI, and OpenCode when they are missing, and it reuses a cached Stytch session when the app still accepts it.

2. Read `runs/<run-id>/preflight.json`.
   - `"ok": false` — report the failing check's `detail` and stop. Do not log in again, do not retry `/auth/password`, and do not guess a ticket or a PR.
   - `"ok": true` — read `runs/<run-id>/context-pack.json`.

3. The context pack is the only Linear and GitHub data you may use.
   - `ticket` is that one Linear issue. `connectedTickets` are its parent, children, and related issues. Do not search the Linear team or open any other issue.
   - `pullRequests` are the PRs that mention that key. `fileDetails` is the diff of those PRs. Do not clone the repo, do not open the GitHub file tree, and do not read any file that is not in the diff.
   - `primaryPr` is the PR the specs should follow.
   - Starting from `--pr` reads that pull request only, takes the LEX key from its title, branch, or body, then loads that ticket and its connected issues.

4. Hand off to `lexful-autonomous-agent-qa` with the pack path. Tell it the spec count the user asked for. Do not shrink the pack.

## What the script checks

| Check | Pass |
|---|---|
| npm packages | `@playwright/test` and `@playwright/cli` are installed |
| Chromium | `npx playwright install chromium` has a browser binary |
| Playwright CLI | `playwright-cli` runs |
| FastAPI | `server/.venv` imports fastapi, uvicorn, and pydantic |
| OpenCode | `opencode` is on PATH, OpenRouter is logged in, and the agents are Sonnet 5.5 and Haiku 5.5 |
| Env file | `LINEAR_API_KEY`, `GITHUB_TOKEN`, `STYTCH_ORGANIZATION_ID`, `STYTCH_ADMIN_EMAIL`, and `STYTCH_ADMIN_PASSWORD` are set |
| Linear | Viewer query succeeds. With a ticket, that issue is fetched |
| GitHub | The token is accepted. Files are loaded only from the pull request diff |
| Stytch | Cached session is reused when it still probes, otherwise one `POST /auth/password`. Cookies land in `runs/cache/stytch/` and in the run directory |
| Playwright | `playwright` and `playwright-cli` report versions |
| Ticket context | Pack written for that ticket, its connected issues, and its PR files |

Work only inside this repository. Do not read `~/Downloads`, `~/Desktop`, `~/Documents`, or any other folder. `opencode.jsonc` denies `external_directory`.

Credentials stay in `.env`. Never print them and never commit `.env` or `auth-state.json`.
