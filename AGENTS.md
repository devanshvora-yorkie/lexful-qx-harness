# Lexful UAT Playwright suite

Start a ticket from the server. Preflight, the Stytch session, and the context pack are written under `runs/<ticket>/<run-id>/` before OpenCode starts. Specs for that attempt go in that folder's `specs/` directory. Checked-in suites live in `e2e test cases/`.

```bash
npm run serve
npm run ticket -- LEX-3371
```

`npm run ticket` starts the run and prints `run.log` until it finishes. If that ticket is already in progress, it follows that run. Add `--new` to start another one.

The coordinator is Sonnet 5.5 (`qa`). Exploration, spec writing, and healing are Haiku 5.5 subagents (`qa-explorer`, `qa-author`, `qa-healer`). The server runs Playwright and writes `qa-result.json` and `report.md` in the same run folder. Cached Stytch cookies live in `runs/cache/stytch/`.

Stay inside this directory. Do not read `~/Downloads`, `~/Desktop`, `~/Documents`, or any other checkout. Do not clone `docu-stack`.

- Linear access is the named ticket plus the parent, children, and related issues on that ticket.
- GitHub access is the pull requests that mention that ticket, and only the files in those pull requests.
- Do not commit `.env`, `auth-state.json`, or `runs/`.
