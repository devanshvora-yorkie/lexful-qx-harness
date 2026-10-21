# FEATURE: Authentication

**Spec:** `auth.spec.ts` · 4 tests · last full run: green (2026-10-16)

## Scenarios

- [x] `POST /auth/password` returns HTTP 204 with both cookies (`stytch_session`, `stytch_session_jwt` on `.lexful.net`)
- [x] Cookies apply to the app domain — navigate to `/docs/assets` without redirect to login
- [x] Invalid credentials return HTTP 4xx
- [x] Expired/missing cookie redirects to login

## Notes

- `auth-helper.ts` loads `auth-state.json` first (avoids API rate limits) and auto-refreshes via API when cookies are expired — the stale-file failure mode that hung a run on 2026-10-16 can't recur.
- Sessions last ~12h. A suite run that spans expiry pays one API call on the next test.
