# Custom Instructions — lexful-test

Project caveats only, loaded by `opencode.jsonc` for every session. The procedure for each phase is in `.agents/skills/lexful-autonomous-agent-qa/phases/`, and the rules every phase shares are in `.agents/prompts/qa.md`.
Everything here was verified against the live UAT DOM (2026-10); do not treat it as theory.

## Caveats
- **AG Grid loads rows async**: placeholder rows show disabled checkboxes ("Row selection is disabled
  for this row") + "Row data is loading". Wait for a real row (`rowByName('AAA-SRV-001')`) in
  beforeEach, never just the grid viewport.
- **Overlay blocks clicks** on "Clear selection" / "Actions" — use `force: true`.
- **Bulk buttons stay in the DOM at "0 selected"** — assert the count resets, not button visibility.
- **Create drawer**: Create enables only with Name **and** Organization set (all-orgs view).
- **"Ask Lex" appears 3×** in the DOM — scope with `header` or `.first()`.
- **Drawer state leaks across tests** — reset with `page.goto('about:blank')` before navigating,
  or an open drawer blocks treegrid re-render.
- **Auth cookie expiry is silent**: the default session in `runs/cache/stytch/session.json` is admin and lasts ~12h.
  `node scripts/persona.mjs support` or `node scripts/persona.mjs viewer` writes `runs/cache/stytch/<persona>.json` without replacing the admin file.
  The server refreshes a file that expires and reruns the suite. Do not call `/auth/password` per test. The API rate-limits.
- **`state-load` does not navigate.** Open the app URL after it. If the page lands on login, the session is dead: run `node scripts/persona.mjs <persona> --fresh` (the harness signs in again from its own credentials), `state-load` the file again, and reload. Never read the session file or call `/auth/password`.
- **CloudFront 403 on shared UAT**: ~1-3% of navigations; escalates if the suite runs several times an
  hour. Playwright retries a failed test once. A second failure is left for the healer. Space out runs.
- **`waitUntil: 'networkidle'` is banned** — it caused multi-minute hangs. `domcontentloaded` + an
  explicit per-page wait.
- **Environment is not product.** A CloudFront 403 "Request blocked", a listing stuck on "Row data is loading" on
  every attempt, and a missing `*_FIXTURE_*` env var are environment failures. Retry once, class `spec` with
  `environment` in the reason, and never file them. Create the fixture through the API or UI instead of reading an env var.
- **Text with hidden spaces.** The selection bar renders `'1 selected'` as `1selected` in the DOM. Match with `\s*`, or use `toContainText`.
