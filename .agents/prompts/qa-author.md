You are Phase 2 of `.agents/skills/lexful-autonomous-agent-qa/SKILL.md`. Read that phase and `references/custom-instructions.md` before you write files. Do not explore the app. Do not call Linear, GitHub, or `/auth/password`.

`FEATURE.md` is the source of truth. Also read the run's `context-pack.json`. Every acceptance criterion and every matrix row becomes a test. A missing checkbox is still a test. Specs use `injectAuthCookies` from `auth-helper.ts`. Each file is one scenario group. Every data load uses `page.waitForResponse` for an API recorded in `FEATURE.md`.

Do not wrap the assertion in a condition that lets the test pass when the behavior is absent. Do not stop at the requested count while a ticket criterion has no test.

When the files are written, write `planned-specs.json` in the run directory:

```json
{
  "plan_file": "tests/<module>/FEATURE.md",
  "test_files": ["tests/<module>/<name>.spec.ts"],
  "pom_files": ["tests/<module>/<name>-pom.ts"]
}
```

Do not run the suite.
