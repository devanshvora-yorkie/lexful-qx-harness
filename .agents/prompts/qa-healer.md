You are the debug loop in `.agents/skills/lexful-autonomous-agent-qa/SKILL.md`. Read that section. Patch only the specs the server names.

Read `playwright/results.json` and `playwright/output.log` in the run directory. If a selector is wrong, reproduce that step with `playwright-cli`, then edit the spec or POM. Do not explore a new flow, do not add scenarios, and do not call Linear, GitHub, or `/auth/password`. Make one patch and stop. This is one heal of the whole suite, not three attempts per test. Do not run the suite.
