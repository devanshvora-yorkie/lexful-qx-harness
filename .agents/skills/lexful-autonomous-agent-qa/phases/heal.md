# Phase `heal`: fix the ticket's failing specs

The server starts this after Playwright fails on the ticket's specs, in a new session that has no memory of the walk. Your memory is the run files: read `FEATURE.md` (selectors, endpoints, gaps), `explore/flow.md` and `feature-map.md` first, then `playwright/results.json` and the failing spec. `playwright/signals.jsonl` shows the console errors, page errors and failed API calls of each test; a 5xx there is evidence for a bug. The message lists the failing tests, the attempt and your browser session name. The shared rules in `.agents/prompts/qa.md` apply. This is not the E2E User Journey heal (`phases/e2e-heal.md`).

For each failing test, replay the step with `playwright-cli` (same persona and URL as the spec), then do one of the things below. Stop after the attempt limit the message gives (3 by default) for that test.

When you are unsure what the product should do here, read that criterion or the review note in `context/` (`references/context.md`) before you decide `bug` or `spec`.

**You fix how a test reaches the page, never what it expects.** Locators, waits, fixtures and steps may change. The matcher and its expected value (`toHaveText('3')`, `toBe(true)`) stay. The server compares every expectation before and after the heal and keeps the run in revision when one changed. If the product's answer differs from the oracle, the test is right: class it `bug`.

**A test can also measure badly.** Sometimes the product is right and the test computed its expected value from an unreliable source, such as counting rows a virtualized list has not rendered (`references/test-design.md`). You may fix where that value comes from: keep the matcher line as it is (`expect(count).toBe(loaded)`) and change how `loaded` is computed. Do this only when all of these hold:
- The new value comes from a source independent of what the test checks (an API response, a total the page reports, the records the test created). It never comes from the value under test.
- You replayed it and the measured value was stable, while the old source was not.
- `reason` names the old source, the new source and why the old one could not be right.

If you cannot meet these, leave the test failing and report it as a decision (below). Never loosen a matcher to get a pass.

1. The control is on the page under another role, name or test id, or the locator matched several elements. Update the locator. Leave the outcome.
2. The step targeted the wrong surface: a tab, a refetch, or a role's control that this session did not see. Rewrite the test to the control the walk showed, or remove the test. Class it `gap`, say why in `triage.json`, and do not add it to `bugs`.
3. The fixture was missing. Create it through the API or the UI and point the test at it. Class it `spec`.
4. An existing wait expired while the snapshot already shows that control. Raise that timeout. Do not add `waitForTimeout`. Do not edit `playwright.config.ts`.
5. This session completed the step, or a probe returned the answer, and the result was wrong: the wrong loaded value, a request sent that the step requires to be blocked, an error page, a wrong status or error code, a role that got in or was kept out against the PR or ticket. Class it `bug` and do not change the expected outcome. Add one object to `bugs` as `references/bug-objects.md` says. If `api-findings.json` already has that defect, do not repeat it: put `"finding": "<id>"` on the bug object instead. Several tests for the same defect go on that one object.
6. The environment failed, not the product: a CloudFront 403 "Request blocked" that clears on retry, a listing that stalls with placeholder rows on every attempt, or a missing fixture env var. Class it `spec`, retry navigation once, and say `environment` in the reason. Do not add it to `bugs`. If it persists on all attempts, leave the test failing and say so in `triage.json`; the server will not file it.

7. The product works as someone evidently intends, and the test's oracle disagrees: a later comment, the PR, or a unit test in the source shows the behavior is deliberate. It is not a bug and you may not change the expectation. Leave the test failing, class it `spec`, action `reported`, and start `reason` with `Needs a decision:`, then give what the test expects, what the product does, and the evidence on each side. A person decides. Code alone is not evidence of intent: if nothing shows the behavior is deliberate, treat it as case 5.

**Unsure?** Re-run the step or the probe once. Same wrong result twice: `bug`, `confidence: "confirmed"`. Wrong once, cannot reproduce: `bug`, `confidence: "suspected"`, keep the evidence. Only a control you never reached is a `gap`. A gap is not a verdict on the product, and a suspected bug is not a failure to find one.

**Playbook for each failing test:**
1. Read the failure line and file from `playwright/results.json` and `playwright/output.log`.
2. Replay the step with `playwright-cli`.
3. Compare the snapshot to `explore/flow.md` and the `FEATURE.md` selectors.
4. Decide: locator drift (`spec`), wrong surface never walked (`gap`), missing fixture (`spec`), timeout with the control already visible (`spec`), or a wrong product outcome after a completed step (`bug`).
5. Patch or report, update `triage.json`, stop at the attempt limit.

A transient 403 during replay on UAT is environment; retry navigation (see the CloudFront note in the custom instructions) before classing `bug`.

## Output

Write `triage.json` as `{"failures":[...],"bugs":[...]}`. `class` is `spec`, `gap` or `bug`. `action` is `patched`, `removed` or `reported`. Every failure appears once with a `reason`. Do not run the official suite. The server re-runs only the tests that did not pass, plus any test you added or renamed, so `playwright/results.json` after a heal holds only those. A required gap that you removed from the spec stays in `FEATURE.md` and keeps the run in revision.
