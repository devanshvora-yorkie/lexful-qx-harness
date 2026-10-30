# API lane

Load this when the changed files include API code (routes, schemas, openapi). Backend tickets are where the UI walk finds the least, so most bugs are found here.

## The tool

```
node scripts/api-probe.mjs GET /v1/asset_types?limit=5
node scripts/api-probe.mjs --persona all GET /v1/permission_catalog
node scripts/api-probe.mjs --persona viewer --write POST /v1/auth/preview --body '{"changes":[]}'
```

- It uses the saved session and account id. You never read cookies.
- One line per persona: `METHOD path  persona  status  list n=57 | item keys: ... | error: CODE / message`. `--persona all` adds a line saying whether the three statuses agree.
- `POST`, `PUT`, `PATCH`, `DELETE` need `--write`. Delete what you create, and note the delete in `explore/flow.md`.
- A CDN block is tagged `[CDN block, not a product result]`. Probe again; do not report it.
- Every call is appended to `api-probes.jsonl`. Cite lines from it as evidence.

## Order (cheapest first)

1. **Reachability.** One call per route the diff adds or changes (grep the clone for the route and openapi lines), as admin. 404 `Route ... not found` means the PR is not deployed. Note it once and drop that PR from the plan.
2. **Persona matrix.** Re-run each reachable route with `--persona all`. The PR body and ticket say who may call it. A status that differs from the claim is a finding.
3. **Contract.** For each reachable route, one probe per row that applies:
   - missing required field, wrong type, empty string, over-long string
   - unknown id, malformed id, an id from another organization
   - `limit=0`, `limit=1000`, a negative `offset`, a bad `sort`
   - every error code the diff adds for that route (grep the clone): does the live answer use it?
4. **State round trip** (only with `--write`, only for routes the ticket adds): create, read back, update, read back, delete, read back. Compare each step with the claim.
5. **Diff check.** Pick two claims from the PR's own test titles and run them live. If the PR says "does nothing on legacy accounts", prove it with two calls.

Stop when each route the diff touches has been probed once per applicable row. More is not better.

## What counts

| Observation | Class |
|---|---|
| Status or error code differs from the PR, ticket, or OpenAPI | finding |
| A role gets 200 where the claim says refused, or 403 where it says allowed | finding, severity High or Critical |
| A filter, sort, or limit has no effect, or a field the OpenAPI lists is absent | finding |
| 500 on any input | finding, severity High |
| 404 `Route ... not found` | environment note, not a finding |
| `NOT_ENABLED` where the PR says legacy accounts get it | match, a regression test |
| CDN block | retry, not a finding |

Severity: Critical = data exposure or a permission bypass. High = wrong result or 500. Medium = wrong code or message. Low = cosmetic.

## Writing it up

Every finding in `api-findings.json` needs `expected` quoting its source, `actual` with the status and shape, and `evidence` pointing to `api-probes.jsonl`. Add `confidence`: `confirmed` when a second probe repeats it, otherwise `suspected`. Findings without all three are dropped by the server.

A confirmed contract becomes an API spec (see Author, 2d). A mismatch does not become a test that passes.
