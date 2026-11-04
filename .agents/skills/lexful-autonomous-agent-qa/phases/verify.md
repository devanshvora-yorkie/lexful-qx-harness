# Phase `verify`: reproduce what is about to be filed

A new session with no memory of the run. The message lists the defects the run is about to file: `finding:<id>`, `bug:<n>` (the n-th object of `bugs` in `triage.json`) or `signal:<n>`, and your browser session name. The shared rules in `.agents/prompts/qa.md` apply.

Read `pr-brief.md` and `feature-map.md` when they exist (a checked-in suite run has neither), `api-findings.json`, `triage.json` and the failing spec. When the expected result is in doubt, grep the full ticket and PR text under `context/` (when it exists): a later comment may have changed the spec, and then it is not a bug. For each item follow its `steps` in the live app (browser, or `node scripts/api-probe.mjs`), as a person would, with current data, two tries at most.

- If the product does the wrong thing, it is reproduced: save a screenshot that shows the wrong state to `<run dir>/bug-evidence/<ref with ":" replaced by "-">.png` (`finding-F1.png`, `bug-2.png`) with `playwright-cli screenshot`. One clear screenshot, the state after the last step, not a series.
- If the product behaves correctly, or the case fails because its data or locator is outdated, it is not a bug. Say what you saw and, for a checked-in case, what the case should use now (`specFix`: the equivalent record, the new label).

Write `verify.json` as:

```json
{"results":[{"ref":"bug:2","reproduced":true,"notes":"...","evidence":"...","screenshot":"bug-evidence/bug-2.png","persona":"admin","steps":["..."],"specFix":"..."}]}
```

one result per item. When you reproduced it, `steps` and `persona` are the ones you actually followed, written as `references/bug-objects.md` says; the filed bug takes them in place of the steps it was written with, so a developer reproduces it the way you did. A finding the UX audit raised is a suspicion like any other: decide it on what the product does against its criteria, and say so if it is only a matter of wording or layout, which is not a bug. A signal you reproduce as a real defect becomes a new finding in `api-findings.json` with the next free id and `confidence: "confirmed"`. What you cannot reproduce is not filed.
