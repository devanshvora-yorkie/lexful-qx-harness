---
name: lexful-autonomous-agent-qa
description: Generate and verify Playwright E2E tests from a test plan.
version: 1.0.0
author: Hermes
tags: [qa, testing, e2e, playwright, test-generation, test-debugging, automation, pom-pattern]
---

# lexful-autonomous-agent-qa

This skill is **Feature Specific TCs**: tests written for one ticket. It is not **E2E User Journey TCs**, the checked-in suite in `e2e test cases`. The server runs that suite on its own and only calls `qa-healer`.

Feature Specific TCs has three steps: Explore, Author, and Heal.

| Step | Agent | Result |
|------|--------|--------|
| Explore | `qa-explorer` | `FEATURE.md` in the run directory. No specs |
| Author | `qa-author` | POM and specs in the run's `specs/` directory |
| Heal | `qa-healer` | `triage.json` and locator patches. The server re-runs |

UI/UX audit is not a step in this skill. The server runs it after functional QA only when `QA_RUN_UX_AUDIT` is true. Set that to false to run QA only.

Project conventions live in `references/custom-instructions.md`.

## Prerequisites

- The server has already written `runs/<run-id>/preflight.json` with `"ok": true` and a `context-pack.json` beside it
- `appUrl` in the context pack is the live target
- Workspace exists with target repository
- `references/custom-instructions.md` in this skill's directory (read it at Step 0; it is not auto-loaded)
- No Using Browser-use tool, or preview-pane. or chrome remote-debugging. use playwright-cli only.

## How to Run

The server is the orchestrator. It runs preflight, starts the `qa` agent, then runs Playwright. `qa` reads this skill and delegates. `qa-explorer` does Explore. `qa-author` does Author. `qa-healer` does Heal. The files in `.agents/prompts/` are the role limits. They are not a second procedure.

A Feature Specific TCs run always explores the live `appUrl` before any spec is written. Do not start a local dev server. Do not reuse an existing `FEATURE.md`. Every step uses Haiku 5.5.

An E2E User Journey TCs run is not a ticket. The server message says `E2E User Journey TCs`. The server already executed `e2e test cases` against UAT and did not call Linear. Do not explore and do not write new specs. Delegate to `qa-healer`. Patch spec drift: a renamed locator, a locator that matches several elements, or an existing wait that expired while that control was already on the page. Do not add `waitForTimeout`. Report a product bug in `triage.json` and leave that spec alone. The result stays in the run folder.

## Quick Reference

| Step | Action |
|------|--------|
| Step 0 | Read `runs/<run-id>/preflight.json` (`ok: true`) and `context-pack.json`. Do not call Linear, GitHub, or `/auth/password` yourself |
| Step 0b | Use `appUrl` from the context pack. Do not start a dev server. A 403 does not change the target |
| Explore | Walk the live app → write `FEATURE.md` in the run directory. Do not write specs |
| Author | Generate common POM → generate module POMs → generate specs → write `planned-specs.json` |
| Heal | 3 heals of the whole suite. Each heal patches once and stops. The server re-runs |
| Handoff | The server writes `runs/<run-id>/qa-result.json` from the Playwright reporter |

**Explore is not optional.** Skipping it and inferring the flow from source code is the single most common failure mode this skill exists to prevent.

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

The live target is `appUrl` in the context pack. Do not start a local dev server. Do not run `pnpm dev`, `npm run dev`, or `make dev`.

Use that URL even when a probe returns 403. CloudFront 403 on UAT is a known response and is not a reason to change targets.

Record that URL at the top of `FEATURE.md` in the run directory. Every snapshot and API observation in Explore must come from it.

**Never derive the flow from source code alone.** Reading route files, components, or specs tells you what the code *claims*; it does not tell you what renders, what is gated, what the API actually returns, or what a user actually sees. Code reading is an input to exploration, never a substitute for it.

### 0c. Explore gate — exploration cannot be skipped

Explore runs on every ticket. Do not reuse a `FEATURE.md` from a previous run or from another agent.

You may not write `FEATURE.md` until you have navigated the app in this run and saved a snapshot. Every route, control, and endpoint in it must trace back to something you observed.

### 1. Explore: UI Exploration & Test Planning

**1a. Explore the Application** — Preflight already installed the tools. Call `node_modules/.bin/playwright-cli`. Chromium is already at `PLAYWRIGHT_BROWSERS_PATH` (`/ms-playwright` in the container). Do not run `--help` or `--version`. Do not run `playwright install`, `install-browser`, or look for `/opt/google/chrome`. Load `runs/cache/stytch/session.json` with `state-load`, then open `appUrl`. Do not write spec files. Record each interaction, navigation path, interactive element, form field, and data dependency for `FEATURE.md`.

Track console errors, info messages, and network API calls. When an interaction triggers an API call, record the method, URL pattern, and the action in the API Endpoints section of `FEATURE.md`. Author uses that list for `page.waitForResponse`. Track API calls with `playwright-cli requests`. The `--static` flag is boolean, so `--static=false` crashes the CLI; the default already excludes static assets.

**playwright-cli mechanics that cost time (verified):**
- Element refs (`e15`) go stale after ANY re-render — never carry a ref across two actions; re-snapshot or use locators (`getByRole(...)`).
- Use `getByRole('button', { name: 'X', exact: true })` whenever a short name is a substring of another control (e.g. `Risk` vs `All risks`) — the non-exact resolution silently fails to click.
- Pipe raw values with the global `--raw` flag: `playwright-cli --raw snapshot > snap.yml`, `playwright-cli --raw eval "..."`.
- Inside `run-code --filename=script.js`, `setTimeout`/`require` are NOT in scope. Delay a route with `await page.waitForTimeout(5000)` inside the route handler.
- A `div[role=presentation]` fixed overlay means a modal is open and is intercepting ALL pointer events; "element intercepts pointer events" errors are almost always an unclosed modal.
- `--raw snapshot` of a large SPA is cheap; save it to a file and grep it instead of dumping it into context.

This is the reliable source of truth for `page.waitForResponse()` patterns in Author.


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

Analyze the API request and response and expand the scenarios from that. Write every scenario, selector, and API call into `FEATURE.md`. Do not write a spec file in Explore.

**MANDATORY: Example: Every listing page must be tested at 100% action coverage.** Explore must identify and plan tests for EVERY action on every listing/table page. Do not skip any action. The following checklist is exhaustive — verify each one during exploration and mark `[x]` or `[ ]` in the FEATURE.md:

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

**1e. Write the FEATURE.md** — Save `FEATURE.md` in the run directory (`runs/<ticket>/<run-id>/FEATURE.md`). Do not put it under `specs/` or `tests/`. The coordinator reads that file. It documents:
- URL, role-based access, data models
- **API Endpoints section** — List all captured API calls with method, URL pattern, and which action triggers it. Include the call before and after each action so Author can wait on it
- **Action coverage matrix** — Every action listed above with `[x]` or `[ ]` per role
- Test coverage plan with checkboxes (`[x]`/`[ ]`) tracking which tests are written and verified
- Detailed selectors from a fresh snapshot
- Execution commands

This is the single source of truth for what each module tests and its current status.

**1f. Approval Gate** — When a person is driving the session, present the FEATURE.md plan and wait for approval. When the server started the run, skip the gate and hand the plan to `qa-author`. The server runs the suite after the specs exist.

### 2. Author: Test Generation

**CRITICAL: Author builds on Explore's plan.** Explore produces the FEATURE.md with API Endpoints, Action Coverage Matrix, and test scenarios. Author MUST use these as its source of truth — never generate tests from scratch or skip planned scenarios.

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
- **Every listing page action must have a test** — reference the Action Coverage Matrix from Explore FEATURE.md. No action is optional.
- **Every data-loading action must use `page.waitForResponse`** — reference the API Endpoints section from Explore. Never use `waitForTimeout` for data loading.
- **Test every checkbox from Explore** — if Explore marked `[ ]` for an action, Author MUST write a test for it.

**2e. Hand off** — Write `planned-specs.json` in the run directory. `plan_file` is `runs/<ticket>/<run-id>/FEATURE.md`. Do not copy that file into `specs/`. The server runs `npx playwright test` on `test_files`. Do not run the suite yourself.

### 3. Heal

The server starts this only after Playwright fails. Delegate it to `qa-healer`.

1. Read `playwright/results.json` and `playwright/output.log`.
2. Replay the failing step with `playwright-cli`. Load `runs/cache/stytch/session.json` with `playwright-cli state-load`. Do not read that file and do not log in.
3. Classify every failure and write `triage.json` in the run directory as `{"failures":[...]}`.
   - `spec`: the test is wrong and the product behavior is unchanged. Patch every spec failure in this one return. This includes a renamed role, name, or test id; a locator that matches several elements, which you narrow without changing the expected outcome; and an existing `waitForResponse` or `expect` timeout that expired while the snapshot already shows that control, which you raise without adding `waitForTimeout` and without editing `playwright.config.ts`. `action` is `patched`.
   - `bug`: the product did the wrong thing. A loaded value is wrong, a request was sent that must be blocked, or the page is an error response and the control is absent because of it. Do not edit the spec. `action` is `reported`. The server keeps this in the run folder and does not call Linear.
4. If you are unsure, class it as `bug` and do not edit. Do not add a test. Do not run the suite. The server re-runs it only when a spec file changed during this heal. The cap is 3 heals of the whole suite, not 3 attempts per test.

### 4. Verdict & Handoff

The server writes `runs/<ticket>/<run-id>/qa-result.json` and `report.md`. `FEATURE.md` stays in the run directory. Specs and the POM live in that folder's `specs/` directory. The server copies `plan_file`, `test_files`, and `pom_files` from `planned-specs.json` and sets `test_results` from the Playwright JSON reporter. Do not invent the pass count. Do not write a run's specs under `tests/`.

## Verification

The server treats a run as `PERFECT` only when Playwright exits 0, at least one test passed, and the JSON reporter has zero unexpected tests and zero skipped tests. A skipped test does not count as a pass.

## Customization

Project-specific conventions, pitfalls, and patterns live in `references/custom-instructions.md` in this skill's directory. When present, load and apply workspace paths, POM organization, test patterns, auth setup, generator tool configuration, and known UI framework quirks.
