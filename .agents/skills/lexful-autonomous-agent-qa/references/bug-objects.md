# Bug objects

Every defect you report, as a `bugs[]` object in `triage.json` or a finding in `api-findings.json`, is filed as its own ticket. The server copies your words into it and adds nothing, so write it for a developer who has never seen this run. A bug object that cites `"finding": "<id>"` takes the finding's fields; do not repeat them.

| Field | What to write |
|---|---|
| `area` | The screen, drawer or API, two to four words, no colon: `Organization picker search`, `Documents create drawer`, `GET /v1/organizations` |
| `failure` | What goes wrong, as the user sees it, in under 80 characters, present tense, no ticket or test id: `Blank or padded search returns no matches`. The title is `<area>: <failure>` |
| `description` | One to three sentences: what the user sees, then why it is wrong. Impact first, mechanism after |
| `severity`, `severityReason` | Critical, High, Medium or Low (priority follows: P0 to P3), and one sentence on the impact that sets it |
| `persona` | `admin`, `support` or `viewer`: who was signed in |
| `preconditions` | The data or state step 1 needs: `an organization with at least two Foundation records`. Empty when nothing is needed |
| `steps` | One user action per step, the way a person does it in the app with today's data. Start with where to go (the path, `/docs/d/all/system.document`). Name controls by their visible label, not by locators or test code. No `Observe` steps: what you see goes in `actual` |
| `expected` | What should happen, and where that comes from (the AC line, the PR, the API contract) |
| `actual` | What happened: the text on screen, the status code and the request that was sent |
| `rootCause` | What the diff or source suggests, with the file and line, or `Unknown` |
| `evidence` | Where you saw it: the walk step, the probe line, the screenshot. One item per source |
| `affectedTests` | The ids of the tests that fail because of it (`TC-LEX-3700-008`) |
| `confidence` | `confirmed` when you reproduced it twice, otherwise `suspected` |

Findings in `api-findings.json` also need `id` (F1, F2, ...). A finding without `expected` (quoting its source), `actual` (status and shape) and `evidence` (for example the `api-probes.jsonl` line) is dropped by the server. A fresh verify session follows the steps before anything is filed; what it cannot reproduce is not filed.
