---
name: lexful-autonomous-agent-qa
description: Generate and verify Playwright E2E tests from a test plan.
version: 1.0.0
author: Hermes
tags: [qa, testing, e2e, playwright, test-generation, test-debugging, automation, pom-pattern]
---

# lexful-autonomous-agent-qa

This skill is **Feature Specific TCs**: tests written for one ticket. It is not **E2E User Journey TCs**, the checked-in suite in `e2e test cases`. The server runs that suite on its own and calls the same **`qa`** agent for heal-only work.

One **`qa`** session owns Explore, Author, Heal, and Promote. Do not spawn subagents. The walk, the specs, and the fixes stay in one thread so flow evidence is always available.

| Step | Result |
|------|--------|
| Explore | `FEATURE.md` plus `explore/flow.md`. A step is written only after `playwright-cli` has done it |
| Author | POM and specs for controls the flow recorded. A control that was not seen is a gap, not a test |
| Heal | Fix the locator, rewrite the step to the control that was seen, create the missing fixture, or remove the case as a gap. A product bug is only a step this session already completed where the page then did the wrong thing |
| Promote | Copy up to three **passing** journeys into `e2e test cases` using `playwright/test-outcomes.json` |

UI/UX audit is not a step in this skill. The server runs it after functional QA only when `QA_RUN_UX_AUDIT` is true. Set that to false to run QA only.

Project conventions live in `references/custom-instructions.md`.

## Prerequisites

- The server has already written `runs/<run-id>/preflight.json` with `"ok": true` and a `context-pack.json` beside it
- `appUrl` in the context pack is the live target
- Workspace exists with target repository
- `references/custom-instructions.md` in this skill's directory (read it at Step 0; it is not auto-loaded)
- No Using Browser-use tool, or preview-pane. or chrome remote-debugging. use playwright-cli only.

## How to Run

The server is the orchestrator. It runs preflight, starts one `qa` session, then runs Playwright and writes the verdict. That session does Explore, Author, Heal, and Promote. `.agents/prompts/qa.md` is a short entry point; this skill is the procedure.

A Feature Specific TCs run always explores the live `appUrl` before any spec is written. Do not start a local dev server. Do not reuse an existing `FEATURE.md`. Use the model.

An E2E User Journey TCs run is not a ticket. The server message says `E2E User Journey TCs`. The server already executed `e2e test cases` against UAT and did not call Linear. Do not explore and do not write new specs. Follow **§3 E2E User Journey heal** only. Patch spec drift: a renamed locator, a locator that matches several elements, or an existing wait that expired while that control was already on the page. Do not add `waitForTimeout`. Report a product bug on the `bugs` array in `triage.json` and leave that spec alone. The server writes `bugs.md`. A skipped or deprecated test is not a bug. The result stays in the run folder.

## Quick Reference

| Step | Action |
|------|--------|
| Step 0 | Read `runs/<run-id>/preflight.json` (`ok: true`) and `context-pack.json`. Do not call Linear, GitHub, or `/auth/password` yourself |
| Step 0b | Use `appUrl` from the context pack. Do not start a dev server. A 403 does not change the target |
| Explore | Walk the live app and append each successful step to `explore/flow.md`. Write `FEATURE.md` from those steps |
| Author | Generate the POM and the specs from the flow. Open the app when a selector is missing. Leave out any control the flow did not reach |
| Heal | Same session. For each failing test, replay, fix, and stop after 3 attempts at that test. The server re-runs the files that changed |
| Handoff | The server writes `runs/<run-id>/qa-result.json` from the Playwright reporter |

**Explore is not optional.** Skipping it and inferring the flow from source code is the single most common failure mode this skill exists to prevent.

## Procedure

### 0. Pre-Workflow

0. Read the run directory in the user message. If `preflight.json` is missing or `"ok"` is not true, stop. Do not run `scripts/preflight.mjs` and do not call Linear, GitHub, or `/auth/password`. On success, read `context-pack.json` and `e2e-coverage.md`, and nothing else from Linear or GitHub. Acceptance criteria say what to test. `e2e-coverage.md` lists the cases already run for search, asset crud, and document editing. Do not write those again. There is no minimum and no maximum number of new tests. The number is the uncovered behavior of this ticket. `pullRequests[].fileDetails` are the only product files you may use. `connectedTickets` are the only other issues. Do not clone the product repo and do not read folders outside this one. Do exploration, specs, heals, and promote in this session.
1. Read `references/custom-instructions.md` for project conventions and known pitfalls.
2. Read any agent instruction files in order: `AGENTS.md`, `CLAUDE.md`, `copilot-instructions.md`, `CURSOR.md`.
3. Read `playwright.config.ts` to understand:
   - **Base URL**: Is it local (`http://localhost:5173`) or remote (`https://...`)?
   - **Auth setup**: The session is `runs/cache/stytch/session.json`, loaded with `injectAuthCookies` or `playwright-cli state-load`. Do not open that file and do not look for a password in this config.
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

**1a. Explore the Application** — Preflight already installed the tools. Call `node_modules/.bin/playwright-cli`. Chromium is already at `PLAYWRIGHT_BROWSERS_PATH` (`/ms-playwright` in the container). Do not run `--help` or `--version`. Do not run `playwright install`, `install-browser`, or look for `/opt/google/chrome`. Load `runs/cache/stytch/session.json` with `state-load`, then open `appUrl`. That session is admin. When a case needs support or viewer, run `node scripts/persona.mjs support` or `node scripts/persona.mjs viewer`, then `state-load` `runs/cache/stytch/<persona>.json`. Do not read the file and do not call `/auth/password`. After each interaction succeeds, append that one step to `explore/flow.md`. A click that fails is fixed before the next step is written. Record the path, the control, the form field, the data dependency, and the persona in `FEATURE.md`. A control this walk did not reach is a Gap in `FEATURE.md`. It is not a planned case. Before you finish the walk, delete every record this session created and append those cleanup steps to `explore/flow.md`. A gap that the ticket or its pull request requires stays in Gaps. The server keeps the run in revision while that gap is open.

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

**1b. Check existing structure** — Before creating new directories or files, list the target directory with `ls` or `find` and match the names already there.

**1c. Map User Flows** — Read `e2e-coverage.md` first. Document entry point, route, prerequisites, and the behavior this ticket changes. When the walk includes a listing or grid, read `references/listing-exploration-hints.md` and record what you observed in the action coverage matrix (not every bullet becomes a test). Cover the negative path, toast, console, and network for behavior the coverage file does not already assert.

Analyze the API request and response and expand the scenarios from what the response showed. Write every new scenario, selector, and API call into `FEATURE.md` only when the walk reached it. `explore/flow.md` is the record of those steps. Do not write the POM suite during Explore.

**Plan the ticket, not a second copy of the checked-in journeys.** Search, asset crud, and document editing already run in E2E User Journey TCs. Plan a case only when this ticket's acceptance criteria or the walk reached that control. If `e2e-coverage.md` already asserts it, mark it `[x]`, cite that id, and set the planned-cases status to `covered`. If the ticket changes it, the walk reached it, and no row asserts the new outcome, plan a new case and set the status to `new`. A control the walk did not reach stays a Gap. There is no minimum count and no maximum count. Every data-changing action waits for the API call recorded in FEATURE.md.

**1e. Write the FEATURE.md** — Save `FEATURE.md` in the run directory (`runs/<ticket>/<run-id>/FEATURE.md`). Do not put it under `specs/` or `tests/`. The coordinator reads that file. It documents:
- URL, role-based access, data models
- **API Endpoints section** — List all captured API calls with method, URL pattern, and which action triggers it. Include the call before and after each action so Author can wait on it
- **Action coverage matrix** — Each behavior this ticket changes that the walk reached. Cite a covered id, or mark `[ ]` for a new case. A control the walk did not reach goes under Gaps, not in this matrix
- Planned-cases table: Id, Type (`positive`, `negative`, `edge`), Suite (`BVT`, `Smoke`, `Sanity`, `Regression`), Persona (`admin`, `support`, or `viewer`), Title, Status (`covered` with an id from `e2e-coverage.md`, or `new`)
- Test coverage plan with checkboxes (`[x]`/`[ ]`) tracking which new tests are written and verified
- Detailed selectors from a fresh snapshot
- Execution commands

This is the single source of truth for what each module tests and its current status.

**1f. Approval Gate** — When a person is driving the session, present the FEATURE.md plan and wait for approval. When the server started the run, skip the gate and continue to Author in this session. The server runs the suite after the specs exist.

### 2. Author: Test Generation

**CRITICAL: Author builds on the walk, not on a guessed row.** `FEATURE.md`, `explore/flow.md`, and `e2e-coverage.md` are the source. Write a test for a `new` row whose control the walk reached. Do not write a `covered` row. Do not write a Gap. There is no minimum and no maximum. Do not pad the run. Open the app with `playwright-cli` when a selector is not in the flow, and write the test from what you see. Do not invent a tab, a refetch, or a role's control that the walk did not show.

**2a. Page objects** — Put locators for this ticket in the module POM next to the spec. Add a shared POM only when two page objects in this run use the same control.

**2b. Generate Module POMs** — Create a POM class for each page this ticket touches. Follow selector priority:
1. `getByTestId("id")` — most stable
2. `getByRole("button", { name: "Label" })` — semantic
3. `getByLabel("Field Name")` — form fields
4. `getByText("Text")` — fallback
5. CSS locator — last resort

**2c. Generate Test Specs** — Write spec files using POM locators. **Tests must be data-driven**, not static assertions:
- Create real data via API/UI (e.g., create a lead, then verify it appears in the list)
- Verify persistence (CRUD round-trips prove the API works end-to-end)
- Use typed interfaces for test data (not inline objects)
- Cover the roles this ticket changes
- One file is one suite (`bvt`, `smoke`, `sanity`, or `regression`). Types share that file
- The id is `TC-<TICKET>-001`. Do not reuse an id from `e2e-coverage.md`
- Tag each test with one type and one suite: `{ tag: ['@positive', '@smoke'] }`
- The default `injectAuthCookies(page.context())` is admin. A support or viewer case passes that name: `injectAuthCookies(page.context(), 'viewer')`
- Write a test for each `new` row the walk reached. Do not write a `covered` row or a Gap
- Create the fixture through the API or the UI. Do not stop the test on a missing env var
- **Every data-loading action must use `page.waitForResponse`** — reference the API Endpoints section from Explore. Never use `waitForTimeout` for data loading
- A `[ ]` row is a test only when the walk reached that control. A covered row is not a test

```ts
test.describe('LEX-3717 documents — smoke', () => {
  test('TC-LEX-3717-001: Save keeps the new expiry after reload', {
    tag: ['@positive', '@smoke'],
  }, async ({ page }) => {
    // Do the change, reload, and assert the value stuck.
  })
})
```

**2e. Hand off** — Write `planned-specs.json` in the run directory. `plan_file` is `runs/<ticket>/<run-id>/FEATURE.md`. Do not copy that file into `specs/`. The server runs `npx playwright test` on `test_files`. Do not run that official suite yourself. Replaying one step with `playwright-cli` is part of writing the spec.

### 3. E2E User Journey heal

This section applies only when the server message says `E2E User Journey TCs`. Do not use Feature Specific Heal for that suite.

Read `playwright/results.json`, `playwright/output.log`, and `e2e test cases/changes.log` before editing. If the log already records the locator you would change, leave the file as is. Do not edit `changes.log`. Replay with `playwright-cli` and `state-load` on `runs/cache/stytch/session.json`. Do not read that file.

Write `triage.json` as `{"failures":[...],"bugs":[...]}`. Every failure appears once. `class` is `spec` or `bug`. `action` is `patched` or `reported`.

**spec** — the checked-in test is wrong and product behavior under test is unchanged: renamed locator, strict-mode match, or an existing wait that expired while the snapshot already shows that control. No `waitForTimeout`. No `playwright.config.ts` edits. Leave the expected outcome.

**bug** — do not edit the spec: wrong loaded value, blocked request was sent, or error page from product failure.

**Environment:** UAT CloudFront **403 Request blocked** that clears on reload is not a product bug. Class **spec**, add navigation retry per custom-instructions, do not add to `bugs`.

If you are unsure, class **bug** and do not edit. The server writes `bugs.md`. Do not run the suite.

### 4. Feature Specific Heal

The server starts this after Playwright fails, in the same session, with `playwright/results.json`, `explore/`, `FEATURE.md`, and `explore/flow.md`. Do not apply the E2E User Journey heal section above.

For each failing test, replay the step, then do one of these. Stop after 3 attempts at that test.

1. The control is on the page under another role, name, or test id, or the locator matched several elements. Update the locator. Leave the outcome.
2. The step targeted the wrong surface: a tab, a refetch, or a role's control that this session did not see. Rewrite the test to the control the walk showed, or remove the test. Class it `gap`. Say why in `triage.json`. Do not add it to `bugs`.
3. The fixture was missing. Create it through the API or the UI and point the test at it. Class it `spec`.
4. An existing wait expired while the snapshot already shows that control. Raise that timeout. Do not add `waitForTimeout`. Do not edit `playwright.config.ts`.
5. This session completed the step, and the page then showed the wrong loaded value, sent a request the step requires to be blocked, or returned an error page. Class it `bug`. Do not change the expected outcome. Add one object to `bugs`. Several tests for the same defect go on that one object, with steps, expected, actual, evidence, severity, and `severityReason`.

If you are unsure, class it `gap`, remove the test or rewrite it to a step you completed, and do not add a `bugs` entry. A gap is not a product bug.

Write `triage.json` as `{"failures":[...],"bugs":[...]}`. `class` is `spec`, `gap`, or `bug`. `action` is `patched`, `removed`, or `reported`. Do not run the official suite. The server re-runs the spec files you changed. A required gap that you removed from the spec stays in `FEATURE.md` and keeps the run in revision.

**Debug playbook (each failing test, up to 3 attempts):**

1. Read the failure line and file from `playwright/results.json` and `playwright/output.log`.
2. Replay the step with `playwright-cli` using the same persona and URL as the spec.
3. Compare the snapshot to `explore/flow.md` and `FEATURE.md` selectors.
4. Decide: locator drift (**spec**), wrong surface never walked (**gap**), missing fixture (**spec**), timeout with control already visible (**spec**), or wrong product outcome after a completed step (**bug**).
5. Patch or report, update `triage.json`, stop at 3 attempts for that test.

Transient **403** during replay on UAT: treat as environment; retry navigation per custom-instructions before classing **bug**.

### 5. Promote, then sign off

After the feature specs have run and the UX audit has finished, copy the passing journeys into `e2e test cases` before the server seals the run. Read **`playwright/test-outcomes.json`** for the final pass/fail of each test title after all heals (the server merges partial reruns). If a title is `passed`, it qualifies. Take at most three tests that **passed** in this run:

1. The positive path that completes the new behavior end to end.
2. The guard that would make that behavior unsafe if it regressed.
3. The ordinary path that must keep working beside the new behavior.

Leave out gaps, failures, skips, tooltip-only checks, and any title already listed in `e2e-coverage.md`. Put document-editor flows in `document editing` (the next free `TC-DOC-` id), record drawers and attachments in `asset crud` (the next free `AC-` id), and search-palette flows in `search`. Import auth as `../../auth-helper`, keep cleanup, and append one inventory row per test to that folder's `FEATURE.md`. The `test()` title must match the Title cell. Write `promoted.json` in the run directory. Do not run the suite. The next E2E User Journey run picks the new files up.

### 6. Verdict & Handoff

The server writes `runs/<ticket>/<run-id>/qa-result.json` and `report.md`. `FEATURE.md` stays in the run directory. Specs and the POM live in that folder's `specs/` directory. The server copies `plan_file`, `test_files`, and `pom_files` from `planned-specs.json` and sets `test_results` from the Playwright JSON reporter. Do not invent the pass count. Do not write a run's specs under `tests/`.

## Verification

The server treats a run as `PERFECT` only when Playwright exits 0, at least one test passed, and the JSON reporter has zero unexpected tests and zero skipped tests. A skipped test does not count as a pass. The run stays `NEEDS_REVISION` when an acceptance criterion has no passing test, when `FEATURE.md` still lists a gap the ticket or its pull request requires, or when the UX audit notes leftover fixtures from this session.

## Customization

Project-specific conventions, pitfalls, and patterns live in `references/custom-instructions.md` in this skill's directory. When present, load and apply workspace paths, POM organization, test patterns, auth setup, generator tool configuration, and known UI framework quirks.
