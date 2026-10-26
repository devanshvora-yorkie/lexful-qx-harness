You heal the checked-in Playwright suite. Read the debug loop in `.agents/skills/lexful-autonomous-agent-qa/SKILL.md`. Do not explore a new flow. Do not add a test. Do not call Linear.

Read `playwright/results.json` and `playwright/output.log` in the run directory. Read `e2e test cases/changes.log` before editing. If that log already records the locator you would change, leave the file as it is. Do not edit `changes.log`. Replay a failing step with `playwright-cli`. Load `runs/cache/stytch/session.json` with `playwright-cli state-load`. Do not read that file. Do not log in.

Write `triage.json` in the run directory as one object: `{"failures":[...]}`. Every failure in the report appears once. `class` is `spec` or `bug`. `action` is `patched` or `reported`.

`spec` means the test is wrong and the product behavior under test is unchanged. Patch all of these in this one return, then stop:

- The control is on the page under a different role, name, or test id. Update that locator. Leave the expected outcome.
- The locator matched several elements (strict mode). Narrow it to the control the test meant. Leave the expected count and the expected text.
- An existing `waitForResponse` or `expect` timeout expired, and the snapshot shows that same control already on the page. Raise that timeout only. Do not insert `waitForTimeout`. Do not edit `playwright.config.ts`.

`bug` means the product did the wrong thing. Do not edit the spec. Set `action` to `reported`.

- A loaded value is wrong: a count, a status, or field text after the control has finished loading.
- A request was sent that the test requires to be blocked.
- The response is an error page (403, 4xx, 5xx) and the control is absent because of that error.

If you are unsure, class it as `bug` and do not edit. Do not run the suite. Say which files you changed, or say that you changed none.
