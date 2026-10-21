You are Phase 1 of `.agents/skills/lexful-autonomous-agent-qa/SKILL.md`. Read that phase before you browse. The coordinator owns Phase 2.

Explore the live app with `playwright-cli` only. The task names the URL. Do not start a dev server. Do not log in. Reuse `auth-state.json` from the run directory. Do not call Linear, GitHub, or `/auth/password`. Do not write spec files.

Snapshots go in the run directory's `explore/` folder. Write `FEATURE.md` in the run directory, not under `tests/`. It must include the URL you opened, each API call with method, URL pattern, and the action that triggered it, and an action matrix marked `[x]` or `[ ]`. One scenario per acceptance criterion the coordinator gave you. Selectors come from a fresh snapshot. Element refs go stale after a render. Do not use `waitUntil: 'networkidle'`.

Stop when `FEATURE.md` is written.
