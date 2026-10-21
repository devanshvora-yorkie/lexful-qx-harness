# Custom Instructions — lexful-test

Caveats only. Structural conventions (folder layout, POM organization, runner) live in `SKILL.md`.
Auth, Linear, and GitHub already ran in the server preflight. Reuse the run directory's `auth-state.json`. Do not call `/auth/password` per test.
Stay inside this repo. Linear is the named ticket and its connected issues. GitHub is the pull request diff only. Do not open Downloads or any other folder.
Everything here was verified against the live UAT DOM (2026-10) — do not treat as theory.

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
- **Auth cookie expiry is silent**: `auth-state.json` sessions last ~12h. `auth-helper.ts` refreshes
  via `/auth/password` only when expired — the API rate-limits, so never call it per-test.
- **CloudFront 403 on shared UAT**: ~1-3% of navigations; escalates if the suite runs several times an
  hour. `retries: 2` absorbs it, but space out runs.
- **`waitUntil: 'networkidle'` is banned** — it caused multi-minute hangs. `domcontentloaded` + an
  explicit per-page wait.
