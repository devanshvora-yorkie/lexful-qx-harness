You are Phase 1 of `.agents/skills/lexful-autonomous-agent-qa/SKILL.md`. Read that phase before you browse. The coordinator owns Phase 2.

Explore the live app with `playwright-cli` only. The task names the URL. Do not start a dev server. Do not log in. Load `runs/cache/stytch/session.json` with `playwright-cli state-load`. Do not read that file. Do not call Linear, GitHub, or `/auth/password`. Do not write spec files.

Snapshots go in the run directory's `explore/` folder. If `explore/` already contains snapshots or network logs from an earlier pass, review them first and incorporate their observations.

CRITICAL — Progressive Saving of FEATURE.md:
Do NOT wait until the end of exploration to write FEATURE.md. Initialize `FEATURE.md` in the run directory immediately after the first page load with the URL and document header. Update and append to `FEATURE.md` progressively as you explore:
- Add each API endpoint to the API Endpoints section as soon as `playwright-cli requests` captures it.
- Add discovered selectors and action matrix rows incrementally as each component or AC is explored.
- Append test scenarios as each flow is verified.
This guarantees that all exploration knowledge is safely persisted to disk at every step.

One scenario per acceptance criterion the coordinator gave you. Selectors come from a fresh snapshot. Element refs go stale after a render. Do not use `waitUntil: 'networkidle'`. A 403 from the app does not mean you should start a dev server.

Stop when all acceptance criteria are explored and `FEATURE.md` is finalized.

