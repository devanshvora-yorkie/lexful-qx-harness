You are Phase 2 of `.agents/skills/lexful-autonomous-agent-qa/SKILL.md`. Read that phase and `references/custom-instructions.md` before you write files. Do not explore the app. Do not call Linear, GitHub, or `/auth/password`.

`FEATURE.md` in the run directory is the source of truth. Also read the run's `context-pack.json`. Every acceptance criterion and every matrix row becomes a test. A missing checkbox is still a test. Specs use `injectAuthCookies` from the import path the task gives you. Each file is one scenario group. Every data load uses `page.waitForResponse` for an API recorded in `FEATURE.md`.

Write the POM, the specs, and a copy of the plan only inside the run directory's `specs/` folder. Do not write under `tests/`.

Do not wrap the assertion in a condition that lets the test pass when the behavior is absent. Do not stop at the requested count while a ticket criterion has no test.

When the files are written, write `planned-specs.json` in the run directory. Paths are relative to the repo root:

```json
{
  "plan_file": "runs/<ticket>/<run-id>/specs/FEATURE.md",
  "test_files": ["runs/<ticket>/<run-id>/specs/<name>.spec.ts"],
  "pom_files": ["runs/<ticket>/<run-id>/specs/<name>-pom.ts"]
}
```

Do not run the suite.
