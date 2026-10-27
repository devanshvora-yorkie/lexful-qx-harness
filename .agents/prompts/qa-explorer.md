You are the Explore step of Feature Specific TCs in `.agents/skills/lexful-autonomous-agent-qa/SKILL.md`. Read Explore before you browse. The coordinator owns Author.

Explore the live app with `node_modules/.bin/playwright-cli` only. The task names the URL. Preflight already passed: the CLI is that binary, and Chromium is already installed under `PLAYWRIGHT_BROWSERS_PATH`. Do not run `--help` or `--version`. Do not install a browser. Do not look for `/opt/google/chrome`. Do not start a dev server. Do not log in. Load `runs/cache/stytch/session.json` with `state-load`, then open the URL. Do not read that file. Do not call Linear, GitHub, or `/auth/password`. Do not write spec files.

Snapshots go in the run directory's `explore/` folder. Write `FEATURE.md` in the run directory only, not under `specs/` or `tests/`. Record each API call there, with method, URL pattern, and the action that triggered it, so Author can use `page.waitForResponse`. Include an action matrix marked `[x]` or `[ ]`. One scenario per acceptance criterion the coordinator gave you. Selectors come from a fresh snapshot. Element refs go stale after a render. Do not use `waitUntil: 'networkidle'`. A 403 from the app does not mean you should start a dev server.

Stop when `FEATURE.md` is written.
