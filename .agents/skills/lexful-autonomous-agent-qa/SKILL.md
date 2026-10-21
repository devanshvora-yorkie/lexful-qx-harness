---
name: lexful-autonomous-agent-qa
description: Generate and verify Playwright E2E tests from a test plan.
version: 1.0.0
author: Hermes
tags: [qa, testing, e2e, playwright, test-generation, test-debugging, automation, pom-pattern]
---

# lexful-autonomous-agent-qa

Two-phase QA workflow: (1) explore UI and create a structured test plan, (2) generate, run, and debug POM-based Playwright tests. Extended via `references/custom-instructions.md` for project-specific conventions and pitfalls.

## Prerequisites

- The server has already written `runs/<run-id>/preflight.json` with `"ok": true` and a `context-pack.json` beside it
- Application URL or dev server running
- Workspace exists with target repository
- `references/custom-instructions.md` in this skill's directory (read it at Step 0; it is not auto-loaded)
- No Using Browser-use tool, or preview-pane. or chrome remote-debugging. use playwright-cli only.

## How to Run

The server is the orchestrator. It runs preflight, starts the `qa` agent, then runs Playwright. `qa` reads this skill and delegates. `qa-explorer` does Phase 1. `qa-author` does Phase 2. `qa-healer` does the debug loop. The files in `.agents/prompts/` are the role limits. They are not a second procedure.

Phase 1 always runs against `appUrl` in the context pack. Do not start a local dev server when that URL is present. If `autonomous-agent-v2` already produced a FEATURE.md for this exact commit, Phase 1 may reuse it instead of repeating the exploration.

## Quick Reference

| Step | Action |
|------|--------|
| Step 0 | Read `runs/<run-id>/preflight.json` (`ok: true`) and `context-pack.json`. Do not call Linear, GitHub, or `/auth/password` yourself |
| Step 0b | Resolve a live URL — use the supplied one if it serves, otherwise start the dev server and wait for 200 |
| Phase 1 | Explore the running app → read playwright config → write FEATURE.md → user approval gate |
| Phase 2 | Generate common POM → generate module POMs → generate specs → run → debug → verdict |
| Debug cap | 3 attempts per test, then document gap and stop |
| Handoff | The server writes `runs/<run-id>/qa-result.json` from the Playwright reporter |

**Phase 1 is not optional.** Skipping it and inferring the flow from source code is the single most common failure mode this skill exists to prevent.

## Procedure

### 0. Pre-Workflow

0. Read the run directory in the user message. If `preflight.json` is missing or `"ok"` is not true, stop. Do not run `scripts/preflight.mjs` and do not call Linear, GitHub, or `/auth/password`. On success, read `context-pack.json` and nothing else from Linear or GitHub. Acceptance criteria say what to test. `pullRequests[].fileDetails` are the only product files you may use. `connectedTickets` are the only other issues. Do not clone the product repo and do not read folders outside this one. The spec count in the user prompt (for example 15) is the number of tests to write for that ticket. Delegate exploration to `qa-explorer`, spec writing to `qa-author`, and fixes to `qa-healer`.
1. Read `references/custom-instructions.md` for project conventions and known pitfalls.
2. Read any agent instruction files in order: `AGENTS.md`, `CLAUDE.md`, `copilot-instructions.md`, `CURSOR.md`.
3. Read `playwright.config.ts` to understand:
   - **Base URL**: Is it local (`http://localhost:5173`) or remote (`https://...`)?
   - **Auth setup**: What auth files exist? What credentials are configured?
   - **Test registration**: How are test specs registered? Is there a `validatedFrontendSpecs` array that must be updated?
   - **Global setup**: Does it depend on local DB (PostgreSQL)? If so, remote testing bypasses it via `BASE_URL` env var.
   - **Workers**: How many workers are configured?

### 0b. Establish a live target (MANDATORY — do this before any exploration)

You cannot explore what is not running. Resolve a URL that actually serves the app:

1. **If the ticket, task, or user supplied a URL**, use it — but verify it first:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$URL"
   ```
   Non-2xx/3xx, or a timeout, means it is not usable. Do not explore it. Fall through to (2).

2. **If no usable URL was supplied, start the app yourself.** This is not optional and not a question for the user.
   - Read `package.json` scripts and `AGENTS.md` for the dev command. Usually `pnpm dev`, `npm run dev`, or `make dev`.
   - If the dev command needs a database, start it too (e.g. `pnpm db:up`) before the app.
   - **Start it in the background** so it survives across tool calls:
     ```bash
     nohup <dev command> > /tmp/qa-devserver.log 2>&1 &
     echo $! > /tmp/qa-devserver.pid
     ```
   - **Wait for it to actually serve.** Poll until 200, with a timeout:
     ```bash
     for i in $(seq 1 60); do
       code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$URL")
       [ "$code" = "200" ] && { echo "up"; break; }
       sleep 2
     done
     ```
   - Read the port from `playwright.config.ts` `baseURL`, the dev server log, or an already-bound listener. Do not guess.
   - If it never comes up, **read `/tmp/qa-devserver.log`, fix the startup error, and retry.** Exhausting the fix attempts is a real blocker; guessing the UI without a running app is not.

3. **Record the resolved URL** at the top of the FEATURE.md. Every snapshot and API observation in Phase 1 must come from this one target.

**Never derive the flow from source code alone.** Reading route files, components, or specs tells you what the code *claims*; it does not tell you what renders, what is gated, what the API actually returns, or what a user actually sees. Code reading is an input to exploration, never a substitute for it.

### 0c. Phase 1 gate — exploration cannot be skipped

Phase 1 is **mandatory in every run**. It may only be skipped when a `FEATURE.md` already exists for this module **and** it carries live-observation evidence: a recorded URL, dated snapshots, and captured API endpoints. A FEATURE.md written without those is a plan, not evidence — re-explore it.

- Being called from `autonomous-agent-v2` does **not** skip Phase 1. If the master orchestrator already ran it for this exact commit, reuse that FEATURE.md; otherwise run Phase 1 yourself.
- An existing FEATURE.md from a previous run does not skip Phase 1. The UI may have changed. Re-explore and update it.
- **You may not write FEATURE.md until you have actually navigated the app in this run.** If you have not loaded a page and taken a snapshot, exploration has not happened.
- Never present a flow diagram derived from reading components. Every route, control, and endpoint in FEATURE.md must trace back to something you observed.

### 1. Phase 1: UI Exploration & Test Planning

**1a. Explore the Application** — With the live target from 0b, navigate it using the Playwright CLI (`playwright-cli --help`). 
Note down each interaction, elementref, navigation paths, interactive elements, form fields, and data dependencies. and write a basic flow test side by side.
1 line at a time.
for example, if you navigated to a site, use playwright cli to navigate to url, see if that worked, if yes, add to flow-test.spec.ts file, move to next interaction.
also keep track of console errors, info msgs, network api calls being made. when you interact and it makes an api call, add page.waitforresponse in the test file before the interaction.(track api calls with `playwright-cli requests` — the `--static` flag is BOOLEAN, so `--static=false` crashes the CLI; the default already excludes static assets.

**playwright-cli mechanics that cost time (verified):**
- Element refs (`e15`) go stale after ANY re-render — never carry a ref across two actions; re-snapshot or use locators (`getByRole(...)`).
- Use `getByRole('button', { name: 'X', exact: true })` whenever a short name is a substring of another control (e.g. `Risk` vs `All risks`) — the non-exact resolution silently fails to click.
- Pipe raw values with the global `--raw` flag: `playwright-cli --raw snapshot > snap.yml`, `playwright-cli --raw eval "..."`.
- Inside `run-code --filename=script.js`, `setTimeout`/`require` are NOT in scope. Delay a route with `await page.waitForTimeout(5000)` inside the route handler.
- A `div[role=presentation]` fixed overlay means a modal is open and is intercepting ALL pointer events; "element intercepts pointer events" errors are almost always an unclosed modal.
- `--raw snapshot` of a large SPA is cheap; save it to a file and grep it instead of dumping it into context.

This is the reliable source of truth for `page.waitForResponse()` patterns in Phase 2.


**CRITICAL: Store snapshots for later reference.** When `browser_snapshot` output is large, save it to a file in the workspace (e.g., `snapshot-{module}.txt`) so elements and structure can be referenced during test generation. If the snapshot exceeds context limits, use targeted extraction via `browser_evaluate` with JS selectors to capture only the relevant DOM.

**1b. Check existing structure** — Before creating new directories or files, list the target directory with `ls` or `find` to match existing naming conventions (e.g., `advisor/` not `advisors/`). Do not assume directory names.

**1c. Map User Flows** — Document entry point, route, prerequisites, and primary user journey, edge cases.
for example, if its a listing page, check
1. table loading state, before/during the api call. 
2. data visibility after api call
3. row actions if any(select, actions menu)
4. pagination, search, filter
5. combination + complex edge cases(like on search, if i am on page 5, page should revert to page 1.)
6. cover negative flow path, toast message capture, console, network capture and assert in testcases.

Analyze the api call request and response and expand testing scenario based on that. capture all the possible scenario, elementref, and write it down in a file, then reference that to test using playwright cli. doesn't matter if it fails or succeeds, we need to capture the flow in a spec.ts file(or in plan so that phase 2 can work on it.)

**MANDATORY: Example: Every listing page must be tested at 100% action coverage.** Phase 1 must identify and plan tests for EVERY action on every listing/table page. Do not skip any action. The following checklist is exhaustive — verify each one during exploration and mark `[x]` or `[ ]` in the FEATURE.md:

- **Row selection** — Single row checkbox/select
- **Select all** — Header checkbox selects all visible rows
- **Deselect all** — Clearing selection after select-all
- **Update/Edit** — Click edit → modify fields → save → verify persistence
- **Delete** — Click delete → confirm dialog → verify row removed
- **Bulk delete** — Select multiple → bulk delete action
- **Search** — Type query → verify filtered results → clear → verify all results
- **Sort** — Click column headers (ascending/descending) → verify order
- **Filter** — Apply filters → verify results → clear filters → verify all
- **Pagination** — Next/prev/page number → verify data changes → verify row count
- **Column visibility** — Toggle columns on/off → verify shown/hidden
- **Row count display** — "Total X", "1-N of X", "Y / page"
- **Empty state** — When no data matches, verify empty state message
- **API loading** — Every data-changing action must wait for its API response before asserting (see API Endpoints section)
- **CRUD round-trip** — Create data → verify in list → update → verify change → delete → verify removal
- **Permissions** — Verify roles without access cannot see/hide actions (e.g., "Add New" button hidden for advisors without permission)

**1e. Write the FEATURE.md** — Save a `FEATURE.md` file **in the same directory as the test files** (not in a separate `plans/` folder). The FEATURE.md documents:
- URL, role-based access, data models
- **API Endpoints section** — List all captured API calls with method, URL pattern, and which action triggers it
- **Action coverage matrix** — Every action listed above with `[x]` or `[ ]` per role
- Test coverage plan with checkboxes (`[x]`/`[ ]`) tracking which tests are written and verified
- Test file paths
- Execution commands
- can reference the partial spec file that we wrote (flow/navigation one).
- Mention detailed selectors, api calls before/after for better phase 2.

This is the single source of truth for what each module tests and its current status.

**1f. Approval Gate** — When a person is driving the session, present the FEATURE.md plan and wait for approval. When the server started the run, skip the gate and hand the plan to `qa-author`. The server runs the suite after the specs exist.

### 2. Phase 2: Test Generation

**CRITICAL: Phase 2 builds on Phase 1's plan.** Phase 1 produces the FEATURE.md with API Endpoints, Action Coverage Matrix, and test scenarios. Phase 2 MUST use these as its source of truth — never generate tests from scratch or skip planned scenarios.

**2a. Create Common POM Class** — **Mandatory.** Always create a shared POM class (e.g., `common-pom.ts`) with reusable component locators and methods:
- Dropdowns: `selectOption(label, value)`, `isOpen()`
- Buttons: `clickButton(label)`, `isButtonVisible(label)`
- Tables: `getRow(index)`, `getCell(rowIndex, colIndex)`, `hasRow(text)`
- Forms: `fillField(label, value)`, `getFieldValue(label)`
- Navigation: `navigateTo(path)`, `sidebarLink(label)`
- Pagination: `goToPage(n)`, `nextPage()`, `prevPage()`
- Search: `search(text)`, `clearSearch()`
- Filters: `filterBy(field, value)`
- Dialogs/Modals: `closeDialog()`, `confirmDialog()`

This common POM is imported by all module POMs to avoid duplication.

**2b. Generate Module POMs** — Create POM classes for each page/component that extend or compose the common POM. Follow selector priority:
1. `getByTestId("id")` — most stable
2. `getByRole("button", { name: "Label" })` — semantic
3. `getByLabel("Field Name")` — form fields
4. `getByText("Text")` — fallback
5. CSS locator — last resort

**2c. Generate Test Specs** — Write spec files using POM locators. **Tests must be data-driven**, not static assertions:
- Create real data via API/UI (e.g., create a lead, then verify it appears in the list)
- Verify persistence (CRUD round-trips prove the API works end-to-end)
- Use typed interfaces for test data (not inline objects)
- Cover all relevant roles per the module's access model
- Each file covers one scenario group
- **Every listing page action must have a test** — reference the Action Coverage Matrix from Phase 1 FEATURE.md. No action is optional.
- **Every data-loading action must use `page.waitForResponse`** — reference the API Endpoints section from Phase 1. Never use `waitForTimeout` for data loading.
- **Test every checkbox from Phase 1** — if Phase 1 marked `[ ]` for an action, Phase 2 MUST write a test for it.

**2e. Hand off** — Write `planned-specs.json` in the run directory. The server runs `npx playwright test` on `test_files`. Do not run the suite yourself.

### 3. Debug Loop

The server starts this only after Playwright fails. Delegate it to `qa-healer`.

1. Read `playwright/results.json` and `playwright/output.log`.
2. Replay the failing step with `playwright-cli`.
3. Patch the spec or POM.
4. Stop. The server re-runs the suite. It allows 3 heal attempts, then records the gap.

### 4. Verdict & Handoff

The server writes `runs/<run-id>/qa-result.json` and `report.md`. It copies `plan_file`, `test_files`, and `pom_files` from `planned-specs.json` and sets `test_results` from the Playwright JSON reporter. Do not invent the pass count.

## Verification

The server treats a run as `PERFECT` only when Playwright exits 0 and the JSON reporter has zero unexpected tests.

## Customization

Project-specific conventions, pitfalls, and patterns live in `references/custom-instructions.md` in this skill's directory. When present, load and apply workspace paths, POM organization, test patterns, auth setup, generator tool configuration, and known UI framework quirks.
