---
name: lexful-autonomous-agent-qa
description: Functional QA for one Lexful ticket or pull request on UAT. Explores the live app and the API, writes and heals Playwright specs, reproduces bugs, and keeps the checked-in E2E suite true to the app. One agent, one model, one phase file per server turn.
version: 2.0.0
tags: [qa, testing, e2e, playwright, test-generation, test-debugging, automation, pom-pattern]
---

# lexful-autonomous-agent-qa

Two kinds of tests, one agent:
- **Feature Specific TCs**: tests written for one ticket, under `runs/tickets/<ticket>/<run>/specs/`.
- **E2E User Journey TCs**: the checked-in suite in `e2e test cases/` (search, asset crud, document editing). The server runs it on its own and calls the same agent for heal-only work. It does not need the rest of this skill.

The server is the orchestrator: preflight, then one OpenCode session per phase, then Playwright and the verdict. The `qa` agent (`opencode.jsonc`) runs every session on the one model `OPENCODE_MAIN_MODEL`. The run files are the memory between sessions.

**Do not read this whole skill.** The server message names the phase; `.agents/prompts/qa.md` holds the rules every phase shares and maps the phase to its file:

| Phase | Session | File |
|---|---|---|
| `explore+author` | First turn of a ticket run: brief, source map, hypotheses, walk, probes, specs | `phases/explore-author.md` |
| `heal` | New session after Playwright fails on the ticket's specs; at most 3 attempts per test | `phases/heal.md` |
| `e2e-heal` | Checked-in suite failed against UAT: patch outdated cases in place | `phases/e2e-heal.md` |
| `affected-heal` | Checked-in cases that ran beside a ticket and failed | `phases/e2e-heal.md` |
| `verify` | Fresh session reproduces every suspected bug before it is filed | `phases/verify.md` |
| `promote` | Copy at most two passing journeys into `e2e test cases/` | `phases/promote.md` |
| `ux-audit` | UX audit of the journey (only when `QA_RUN_UX_AUDIT=true`) | `.agents/prompts/ux-auditor.md` |

References, read by the phase file that names them:
- `references/test-design.md`: what a test must prove, how to exercise real behavior safely, what counts as a gap
- `references/context.md`: reading the ticket's full context under `context/` and looking up what it names
- `references/oracle-from-diff.md`: build `feature-map.md` from the diff and the code around it
- `references/api-lane.md`: probing a backend change with `scripts/api-probe.mjs`
- `references/listing-exploration-hints.md`: scan list for grids and listings
- `references/bug-objects.md`: the bug object every defect is written as
- `references/custom-instructions.md`: project caveats, loaded for every session by `opencode.jsonc`

Use the harness tools only: `playwright-cli` for the browser, `scripts/api-probe.mjs` for the API, `scripts/persona.mjs` for other roles. No browser-use tool, preview pane or Chrome remote debugging.
