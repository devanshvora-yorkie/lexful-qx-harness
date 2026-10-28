You are the Heal step. Read Heal in `.agents/skills/lexful-autonomous-agent-qa/SKILL.md`. On E2E User Journey TCs, patch the checked-in suite in `e2e test cases`. On Feature Specific TCs, patch the specs in the run directory. Do not explore a new flow. Do not add a test. Do not call Linear.

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

If you are unsure, class it as `bug` and do not edit.

Add a `bugs` array to the same `triage.json`. One object is one defect. When several failed TCs are the same defect, list them all on that object. The server writes `bugs.md` from this array. Do not write `bugs.md` yourself. Do not file a skipped or deprecated test.

```json
{
  "failures": [
    {"class": "bug", "action": "reported", "title": "TC-LEX-3717-002: Create is blocked while the name is empty"}
  ],
  "bugs": [
    {
      "area": "Documents",
      "failure": "Create stays enabled when the name is empty",
      "context": "LEX-3717 document name guard",
      "severity": "High",
      "severityReason": "A technician can save a document with no name, so the new row cannot be identified.",
      "description": "The create drawer enables Create while Name is empty. The API accepts the write and the grid shows a blank name. A technician cannot tell which record was just added.",
      "affectedTests": [
        {"id": "TC-LEX-3717-002", "suite": "Smoke", "title": "Create is blocked while the name is empty", "note": "Create stayed enabled and the POST returned 201"}
      ],
      "steps": [
        "Navigate to https://e2e-test.uat.lexful.net/docs/d/all/system.document as Admin",
        "Open the New document drawer",
        "Choose an organization and leave Name empty",
        "Click Create"
      ],
      "expected": "Create stays disabled, and no document is written.",
      "actual": "Create is enabled. POST /v1/assets/system.document returns 201 and a blank-name row appears.",
      "rootCause": "Unknown — requires investigation",
      "evidence": [
        {"test": "TC-LEX-3717-002", "step": 4, "detail": "playwright/output.log: expected disabled, received enabled"}
      ],
      "labels": ["documents", "create"]
    }
  ]
}
```

Severity is Critical, High, Medium, or Low. Say why in `severityReason`. The server writes that reason into the description and sets priority from severity: Critical is P0, High is P1, Medium is P2, Low is P3. Include repro steps and at least one evidence item. Do not file a skipped or deprecated test.

Do not run the suite. Say which files you changed, or say that you changed none.
