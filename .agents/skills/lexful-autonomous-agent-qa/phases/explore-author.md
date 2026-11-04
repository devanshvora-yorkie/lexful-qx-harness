# Phase `explore+author`: understand, walk, probe, write specs

The first session of a Feature Specific TCs run. You map the change, walk the live app, probe the API, and write the specs. Heal, verify and promote are separate sessions that start from the files you leave in the run directory, so write them early and completely: a fact that is only in your head is lost.

The server message gives the run directory, the ticket, the app URL, the import prefix (`<prefix>`) and your browser session name. The shared rules in `.agents/prompts/qa.md` apply.

| Step | Result |
|------|--------|
| Brief | Read `preflight.json`, `pr-brief.md` (the index: full criteria, deployment, short PR text and comments, pointers to the full text in `context/`), `history.md` and `e2e-coverage.md`. Choose the lane from the paths (Lane and personas below) |
| Understand | Browse the read-only worktree, write `feature-map.md` (`references/oracle-from-diff.md`). Cases come from it. Turn its Risks into `hypotheses.json` (Hypotheses below) |
| Explore | `FEATURE.md` plus `explore/flow.md`. A UI step is written only after `playwright-cli` has done it. An API step only after `api-probe` has returned it |
| Probe | **API lane.** Call the changed endpoints, per persona, compare the answer with the diff and the ticket. Findings go to `api-findings.json` |
| Hunt | Try every hypothesis against the live app or API and set its outcome. A confirmed one is a finding |
| Author | POM and specs for controls the flow recorded, API specs for contracts the probes confirmed, each able to fail when the behavior is wrong (`references/test-design.md`). Reuse the suite's page objects. Write the hand-off files. A control that was not seen is a gap, not a test |

After heal the server runs the checked-in cases you list in `affected-cases.json`, and a fresh verify session reproduces every suspected finding before anything is filed.

**Read `references/test-design.md` before you plan a case.** It decides whether the run proves anything: what a test must assert, how to exercise behavior on real data without harming shared data, and when something is really a gap.

**Explore is not optional.** Inferring the flow from source code alone is the most common failure of this phase. Code tells you what the code claims, not what renders, what is gated, what the API returns or what a user sees. Code reading is an input to exploration, never a substitute.

## 0. Start

1. Read the run directory in the message. If `preflight.json` is missing or `"ok"` is not true, stop.
2. Read `pr-brief.md`, `history.md` (when it exists) and `e2e-coverage.md`. The brief is an index: read `references/context.md` and open what it says to open under `context/`, including everything under **Read before planning**, before you plan a case. `context-pack.json` is about 1 MB of diffs: never open it whole; grep it for one file or symbol. `pullRequests[].fileDetails` and the read-only clone are the product files you may use. Other tickets and pull requests are only the ones `scripts/lookup.mjs` allows. Acceptance criteria say what to test. `e2e-coverage.md` lists the cases already run for search, asset crud and document editing: do not write those again. There is no minimum and no maximum number of new tests; the number is the uncovered behavior of this ticket.
3. The target is `appUrl` in the context pack. Use it even when a probe returns 403: a CloudFront 403 on UAT is a known response, not a reason to change targets. Record it at the top of `FEATURE.md`. Every snapshot and API observation must come from it.
4. Do not reuse a `FEATURE.md` from an earlier run. You may not write `FEATURE.md` until you have navigated the app in this run and saved a snapshot; every route, control and endpoint in it must trace back to something you observed.
5. `playwright.config.ts` needs no reading for the base URL, auth or workers: the server sets them. Read it only when a spec needs a setting it holds.

## 1. Understand the feature

A test written only from what the UI showed asserts today's behavior and can never catch a bug. Read `references/oracle-from-diff.md` and follow it: browse the read-only clone named in `source-info.md` (callers, the path to the data, shared parts, neighboring rules, the authors' tests, history), write `feature-map.md`, and derive every case from a numbered behavior or risk in that map with an oracle. No oracle, no case. If `source-info.md` is missing there is no clone: grep `context-pack.json` for one file's patch at a time.

## 2. Lane and personas

Choose the lane from the changed file paths in `pr-brief.md`. Paths under `apps/*/src` are UI. Paths under `services/*/src` (routes, schemas, openapi) are API. Both present is `ui+api`. A ticket whose acceptance criteria name roles, permissions, or who may do what needs the persona matrix.

- **ui**: the UI walk is the whole job.
- **api**: the PRs change services only. Do a short UI smoke (one page that shows the data) and spend the rest of the session in the API lane. A UI-only plan for a backend ticket is the failure this section exists to prevent.
- **ui+api**: do both. Probe first (cheap), then walk the UI for what the probes showed is live.

When the ticket needs the persona matrix, every probe and every role-dependent UI case runs as admin, support and viewer (`--persona all` for the API). Record the three answers side by side in `FEATURE.md`. Every cell is filled: probe it, or write why it cannot be probed (for example `no such control for this role`). A cell that says only `not probed` means the work is unfinished. A role that sees something another role must not is a bug candidate.

## 3. Explore the live app

Call `node_modules/.bin/playwright-cli --config=<run dir>/explore/pw-cli.json -s=<session name>` (the server wrote that config; it points at the installed Chromium). Do not run `--help`, `--version`, `playwright install` or `install-browser`, and do not look for another Chrome. Load `runs/cache/stytch/session.json` with `state-load`, then open `appUrl` (`state-load` does not navigate). That session is admin. For support or viewer run `node scripts/persona.mjs support` (or `viewer`), then `state-load` `runs/cache/stytch/<persona>.json`. Do not read those files and do not call `/auth/password`.

After each interaction succeeds, append that one step to `explore/flow.md`. A click that fails is fixed before the next step is written. Record the path, the control, the form field, the data dependency and the persona in `FEATURE.md`. A control this walk did not reach is a Gap in `FEATURE.md`, not a planned case. A gap the ticket or its pull request requires stays in Gaps, and the server keeps the run in revision while it is open. Exercise behavior on records you create, not only on an empty result (`references/test-design.md`). Before you finish the walk, delete every record this session created and append those cleanup steps to `explore/flow.md`.

Track console errors, info messages and network API calls. When an interaction triggers an API call, record the method, URL pattern and the action in the API Endpoints section of `FEATURE.md`; Author uses that list for `page.waitForResponse`. Use `playwright-cli requests`. The `--static` flag is boolean, so `--static=false` crashes the CLI; the default already excludes static assets.

**playwright-cli mechanics (verified):**
- Element refs (`e15`) go stale after ANY re-render. Never carry a ref across two actions; re-snapshot or use locators (`getByRole(...)`).
- Use `getByRole('button', { name: 'X', exact: true })` whenever a short name is a substring of another control (`Risk` vs `All risks`); the non-exact resolution silently fails to click.
- Pipe raw values with the global `--raw` flag: `playwright-cli --raw snapshot > snap.yml`, `playwright-cli --raw eval "..."`.
- Inside `run-code --filename=script.js`, `setTimeout` and `require` are NOT in scope. Delay a route with `await page.waitForTimeout(5000)` inside the route handler.
- A `div[role=presentation]` fixed overlay means a modal is open and intercepts ALL pointer events; "element intercepts pointer events" errors are almost always an unclosed modal.

**Fewer steps, same coverage (every tool call re-reads the whole conversation):**
- Do a flow segment in one `playwright-cli run-code --filename=<script>.js`: open, interact, assert, and return a small JSON of what you need (counts, text, URL, visible states). Do not issue one command per click.
- Snapshot once per new state, to a file under `<run dir>/explore/`, then grep it. Never print a whole snapshot. If it is too large, extract with `--raw eval` selectors that return counts or text.
- Write `FEATURE.md` as you go: append each endpoint and selector as soon as you have it.
- At each key state (drawer open, empty state, error, disabled gate) save one screenshot: `playwright-cli screenshot explore/ux/<name>.png`. The UX audit reuses these.

Before creating files or directories, list the target directory and match the names already there.

**Map user flows.** Document entry point, route, prerequisites and the behavior this ticket changes. When the walk includes a listing or grid, read `references/listing-exploration-hints.md` and record what you observed in the action coverage matrix (not every bullet becomes a test). Cover the negative path, toast, console and network for behavior the coverage file does not already assert. Analyze the API request and response and expand the scenarios from what the response showed.

**Plan the ticket, not a second copy of the checked-in journeys.** Search, asset crud and document editing already run in E2E User Journey TCs. If `e2e-coverage.md` already asserts a control, mark it `[x]`, cite that id and set the status to `covered`. If the ticket changes it, the walk reached it and no row asserts the new outcome, plan a new case with status `new`. A control the walk did not reach stays a Gap. Every data-changing action waits for the API call recorded in `FEATURE.md`.

## 4. FEATURE.md

Save `FEATURE.md` in the run directory (not under `specs/` or `tests/`). The server reads it. It holds:
- URL, role-based access, data models
- **API Endpoints**: every captured call with method, URL pattern and the action that triggers it, including the call before and after each action
- **Action coverage matrix**: each behavior this ticket changes that the walk reached. Cite a covered id, or mark `[ ]` for a new case
- **Planned cases**: Id, Type (`positive`, `negative`, `edge`), Suite (`BVT`, `Smoke`, `Sanity`, `Regression`), Persona (`admin`, `support`, `viewer`), Title, Oracle (PR claim, AC line, comment, image, diff, or neighboring source), Fails when (the wrong product behavior that makes this test fail), Status (`covered` with an id from `e2e-coverage.md`, or `new`)
- Test coverage plan with checkboxes (`[x]`/`[ ]`) for the new tests written and verified
- Selectors from a fresh snapshot, and the execution commands
- **Context read**: what you opened from `context/` and what it changed in the plan (`references/context.md`)

It is the single source of truth for what this run tests. When the server started the run there is no approval gate: continue straight to Author in this session.

## 5. API lane

Read `references/api-lane.md` when the lane includes `api`. Summary: `node scripts/api-probe.mjs [--persona all] GET /v1/...` calls the API with the saved session and prints one compact line per call. Run each changed route at least once per persona, then probe the contract: missing and malformed input, wrong ids, limits, paging and the error codes the brief lists. Every probe is logged to `api-probes.jsonl`.

## 6. Diff versus reality

The PR diff and body say what the build should do; UAT says what it does. Compare them claim by claim, before you plan tests.

1. List the behavior claims: the PR body bullets, "refused with X on legacy", "returns Y when Z", and the titles of the tests the PR adds (grep the pack for `it(` and `test(` in the PR's test files).
2. For each claim you can reach, probe it (API) or walk it (UI).
3. Classify:
   - **Match**: a candidate for a regression test.
   - **Not deployed**: the route answers 404 `Route ... not found`, or the UI shows the pre-PR build. Record it once as an environment note in `FEATURE.md`. It is not a bug and not a test. Do not keep probing that PR.
   - **Mismatch**: the endpoint exists but behaves differently from the claim (wrong status or error code, a filter that does nothing, a missing field, a role that gets in when the claim says refused). This is a **finding**. Never write a test that asserts the wrong behavior as correct.
4. A finding has `expected` (quote the PR, ticket or OpenAPI line), `actual` (status and shape from the probe) and `evidence` (the `api-probes.jsonl` line or snapshot). Reproduce it a second time before you set `confidence: "confirmed"`; with one observation use `"suspected"`.

Write all findings to `api-findings.json` as `{"findings":[...]}`, each an `id` plus the bug object of `references/bug-objects.md`. The server files them whether or not Playwright passes. Write the file before you hand off.

Not findings: a CDN 403 "Request blocked" that clears on retry (`api-probe` retries once and tags it), a 404 for a route the diff adds but UAT does not have, a `NOT_ENABLED` answer the PR says legacy accounts get, a missing fixture.

## 7. Budget

The run costs tokens on every line the model reads, again on every later call. Read the brief, not the pack; grep, do not cat. Open what a case depends on (`references/context.md`), not everything that exists. Probe output is already trimmed; do not pipe it through more tools. Stop exploring a surface once the brief's claims for it are checked. Do not re-read a file you just wrote.

## 8. Hypotheses: push for the bug nobody recorded

Passing tests prove the claims. Bugs hide in the risks. Every item under **Risks** in `feature-map.md` becomes a hypothesis, and `history.md` adds one for each bug or failure an earlier run found. Write `hypotheses.json` before the walk and update it as you go:

```json
{"hypotheses":[{"id":"H1","risk":"R2","prediction":"the alias 'srv' finds the Server icon like 'server' does","tried":"typed srv in the picker, then SRV","outcome":"refuted","evidence":"explore/snap-h1.yml"}]}
```

`outcome` is `planned`, `confirmed` (the risk is real: add the finding to `api-findings.json` and put its id in `finding`), `refuted` (you created the condition it needs and the product held; a call that matched nothing does not count) or `unreached` (say why, and which safe way of reaching it you tried). The server keeps the run in revision when the map lists risks and none was tried, or when a confirmed hypothesis has no finding.

Attacks that find real bugs here, cheapest first. Pick the ones the map points at:
- **Round trip.** Change it, reload, read it back another way: API after UI, UI after API, list after drawer, another tab.
- **Boundaries.** Empty, one, the limit, one past the limit; whitespace, case, accents and emoji; a very long value; a value with `<b>`, quotes or `%`.
- **Roles.** The same action as admin, support and viewer. A role that sees or does what it must not is a finding.
- **State.** Archived, deleted, moved and old records; an empty list; back and forward; a second tab that changed the record first.
- **Every surface.** Each place in the map's Surfaces that uses the changed code, not only the one the PR mentions.
- **Silent failures.** Console errors and 4xx/5xx calls during a walk that looks right (`playwright-cli console` and `requests`).
- **Reviewers' questions.** Each review note in `pr-brief.md` that asks "what about ...?" is a hypothesis.

Stop a hypothesis after the first reproducible mismatch or after two clean tries.

## 9. Author

**Author builds on the walk, not on a guessed row.** `FEATURE.md`, `explore/flow.md` and `e2e-coverage.md` are the source. Write a test for a `new` row whose control the walk reached. Do not write a `covered` row or a Gap. Do not pad the run. Open the app with `playwright-cli` when a selector is not in the flow, and write the test from what you see. Do not invent a tab, a refetch, or a role's control that the walk did not show.

**Page objects.** `e2e-coverage.md` ends with the suite's page objects and helpers. When a page you test already has one, import it read-only (`<prefix>/e2e test cases/<journey>/<file>`) and add only the locators it lacks in your own POM next to the spec. Never edit a suite file in a ticket run. Otherwise put the locators for this ticket in the module POM next to the spec.

**Build on the covered journey.** When `e2e-coverage.md` already covers a journey this ticket touches, do not repeat it. Name the case you build on in the Oracle column (`extends TC-07`) and test what it leaves out: the other personas, the other states, the boundaries, the failure paths and the attacks in Hypotheses.

**Module POMs.** Create a POM class for each page this ticket touches. Selector priority: `getByTestId("id")`, then `getByRole("button", { name: "Label" })`, then `getByLabel("Field Name")`, then `getByText("Text")`, then a CSS locator as the last resort.

**Specs.** Use POM locators. Tests are data-driven, not static assertions:
- Create real data through the API or UI, then verify it (a create, then the list shows it). Verify persistence with CRUD round-trips. Use typed interfaces for test data.
- Each test asserts what its title claims, with an expected value from an independent source (`references/test-design.md`). Write its **Fails when** first.
- Cover the roles this ticket changes. The default `injectAuthCookies(page.context())` is admin; a support or viewer case passes the name: `injectAuthCookies(page.context(), 'viewer')`.
- One file is one suite (`bvt`, `smoke`, `sanity` or `regression`); types share that file. The id is `TC-<TICKET>-001`; do not reuse an id from `e2e-coverage.md`.
- Tag each test with one type and one suite: `{ tag: ['@positive', '@smoke'] }`. The report groups tests by these tags; a test without them is reported as untagged. Choose the suite by what the case is for; they are not all `smoke`.
- Create the fixture through the API or the UI. Do not stop the test on a missing env var.
- **Every data-loading action uses `page.waitForResponse`** with the pattern from the API Endpoints section. Never `waitForTimeout` for data loading.
- Import `test` and `expect` from `<prefix>/qa-fixtures` (not `@playwright/test`); it records console errors, page errors and failed API calls into `playwright/signals.jsonl`. Import auth from `<prefix>/auth-helper`.
- Each test runs on whichever worker is free, in any order, beside tests of the same file. A test stands alone: it creates its own data in the test or `beforeEach`, cleans it up in `afterEach`, and never reads what another test left. Build every name from `Date.now()` and a random suffix, never a fixed name another worker could also create. Do not use `beforeAll`/`afterAll` for data (they run around every test). Only when steps truly cannot be split, put them in one test, or declare `test.describe.configure({ mode: 'serial' })` in that describe.

```ts
test.describe('LEX-3717 documents — smoke', () => {
  test('TC-LEX-3717-001: Save keeps the new expiry after reload', {
    tag: ['@positive', '@smoke'],
  }, async ({ page }) => {
    // Do the change, reload, and assert the value stuck.
  })
})
```

**API specs.** For a contract a probe confirmed (status code, error code, response keys or a role boundary), write a Playwright `request` test, no browser: build the context with `playwright.request.newContext({ extraHTTPHeaders: { Cookie, 'X-Account-Id' } })` using the cookies from `getLexfulCookies(persona)` in `auth-helper`. Assert the status and the error code, not the whole body. Tag it like any other test. Do not write one that asserts a mismatch as correct; file that as a finding.

## 10. Hand-off files

Write these in the run directory:
- `coverage.json`: one JSON object `{"criteria":[...]}`, not a bare array. `criteria` holds every AC number from `pr-brief.md` exactly once, as `{"ac":"AC1","tests":["TC-<TICKET>-001"]}`, `{"ac":"AC2","gap":"why there is no test"}` or `{"ac":"AC3","na":"heading"}`. List a test under `tests` only when it fails if that criterion is broken. Use `gap` only for behavior the product could do that you did not test, and say which safe way of reaching it you tried (`references/test-design.md`). Use `na` for a line that is not behavior to test: a heading, a link, a status line, a build, type-check or unit-test claim, and a branch that cannot exist on UAT (say why). The server checks that each listed test passed.
- `affected-cases.json`: `{"cases":["TC-07"]}`, the checked-in case ids whose page or API this diff changes. The server runs them after your specs.
- `hypotheses.json` with every outcome set.
- Before these are final, do the hand-off review at the end of `references/test-design.md`.
- `planned-specs.json` and `api-findings.json` (an empty `findings` array is fine). `plan_file` is `<run dir>/FEATURE.md`; `test_files` and `pom_files` are paths under `<run dir>/specs/`. Do not copy `FEATURE.md` into `specs/`.

The server runs `npx playwright test` on `test_files` and writes `qa-result.json` and the pass counts from the Playwright reporter. Do not run the official suite yourself, and do not invent a pass count. Replaying one step with `playwright-cli` is part of writing the spec. A run is `PERFECT` only when Playwright exits 0, at least one test passed, and nothing is unexpected or skipped; it stays `NEEDS_REVISION` when an acceptance criterion has no passing test, when `FEATURE.md` still lists a gap the ticket requires, or when the UX audit names leftover fixtures from this session.
