# Phases `e2e-heal` and `affected-heal`: keep the checked-in suite true to the app

`e2e-heal` is the whole job of an E2E User Journey TCs run. You do not explore and you do not author. The server already executed `e2e test cases/` against UAT (it did not call Linear). In a ticket run this is the first stage and the run directory is the ticket run's `e2e/` folder; on its own (`npm run e2e`) it is a folder under `runs/phase-1/`. Either way, read and write in the run directory the message names. The shared rules in `.agents/prompts/qa.md` apply, with one difference: in these phases you may edit `e2e test cases/`.

The checked-in suite guards three journeys: search, asset crud, document editing. It runs on every ticket against a UAT that changes with every release. **A case that fails is outdated until you prove the product is wrong.** Your job is to keep the suite true to the app as it is today, in place, so the next run starts green. A product bug is rare and has to be reproduced.

Read `playwright/results.json`, `playwright/output.log` and `e2e test cases/changes.log` before editing. `changes.log` is the history of edits, not evidence of a bug: a line there that says a defect "was recorded" proves nothing today. Replay each failure with `playwright-cli` (config and `-s=` session name from the message) and `state-load` on `runs/cache/stytch/session.json` (never read that file).

## Fix in place (class `spec`, action `patched`)

When the app moved and the case did not:
- A renamed or moved locator, a locator that matches several elements, changed copy or label.
- **Outdated data.** A seeded name, id, organization, count, date or fixture the case relies on no longer exists or changed. List what the app has now (the page, or `node scripts/api-probe.mjs GET ...`) and update the constant in the spec or page object to the equivalent record, keeping the case's intent. Better, when the case only needs "a record", create it through the API in the test and remove it in `afterEach`, so it no longer depends on seed data.
- A new required field, step or confirmation in a flow the case drives: add the step.
- A wait or timeout that is too short for work the app really does (a poll, a slow save): raise it on the test (`test.setTimeout`) or the poll. No `waitForTimeout`.
- A CloudFront 403 "Request blocked": retry the navigation (see the CloudFront note in the custom instructions).

You may edit the failing spec and the page object, fixture or constant file it imports in `e2e test cases/`. Keep the case's intent and the behavior it asserts: you change how it reaches the app and which data it uses, not what the product must do. A heal never changes what a test expects; it may fix a value the test measured from an unreliable source, keeping the matcher line as it is and naming both sources in `reason`. Do not skip a case, delete it, or soften an assertion to make it pass. Do not edit `playwright.config.ts`, `auth-helper.ts`, `qa-fixtures.ts` or `changes.log` (the server records every edit in `changes.log`). Do not edit the suite's `FEATURE.md` in these phases: when you rename a record its inventory names, tell the server in `triage.json` and it keeps the row true. Only the `promote` phase adds inventory rows.

## Report a product bug (class `bug`, action `reported`)

Only when all of these hold:
1. You replayed the case's own steps against the live app and the app did the wrong thing, with the data and locators current (not a missing seed, not an expired session, not a CDN block).
2. The wrong result contradicts what the case, `e2e test cases/*/FEATURE.md` or the product's documented behavior says should happen.
3. You reproduced it twice. Put the exact steps, expected, actual and what you saw in the bug object (`references/bug-objects.md`); the server then has a fresh session reproduce it and take a screenshot before it files anything.

If you cannot say why the case fails, it is not yet a bug: try once more, look at what changed, and fix the case. A case that fails only because data is missing is `spec`, never `bug`. A skipped or deprecated test is neither.

## Report a decision (class `spec`, action `reported`)

The app changed the behavior a case asserts, and something shows the change was deliberate: a ticket, a PR, or a unit test that asserts the new behavior. The case is out of date, but you may not change what it expects, and it is not a bug. Leave it failing and start `reason` with `Needs a decision:`, then give what the case expects, what the app does, and the evidence on each side. The report lists these for a person, who updates the case or files the bug. Say the same thing on every attempt, and do not spend more attempts on it.

If nothing shows the change was deliberate, it is not a decision: use the bug rules above. The code doing something does not show it was meant to.

## Output

Write `triage.json` as `{"failures":[...],"bugs":[...]}`. Every failure appears once with `class` (`spec` or `bug`), `action` (`patched` or `reported`) and a `reason` that says what changed in the app. Each defect is one `bugs[]` object that lists the tests it explains in `affectedTests`. A failure classed `bug` with no `bugs[]` object is not filed; it stays an open issue of the run. If the message lists tests the verifier could not reproduce, the test or its data is outdated: fix it this round.

Patch every outdated case in one return, then stop. Do not run the suite. The server re-runs only the tests that did not pass, plus any test you added or renamed. When the heals are done it runs every spec in a folder you edited once in full, so a page-object change that breaks a passing test still shows.

## Phase `affected-heal`

Checked-in cases that ran beside a ticket and failed. The same rules apply: a failing case is outdated until you show the product is wrong, and it is usually a timing, locator or data problem. Read `affected/playwright/results.json` and the page snapshot in `affected/playwright/output/`. A value that loads late (a spinner, a linked record's name) needs a web-first wait on the element (`expect(locator).toContainText(...)`), not `waitForTimeout` and not a single `textContent()` read. A count that other work changes needs a baseline read inside the test. Write the triage to `affected/triage.json` (not `triage.json`) as `{"failures":[...]}` with `class` (`spec` or `bug`), `action` and a `reason` for every failure, including the ones you could not fix. A case you could not fix and could not tie to this ticket stays a failure with its reason; do not file a bug here.
