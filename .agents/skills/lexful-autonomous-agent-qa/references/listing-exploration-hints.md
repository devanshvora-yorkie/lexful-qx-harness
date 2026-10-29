# Listing and grid exploration hints

Use this when the walk includes an AG Grid listing or table (passwords, servers, documents, and similar). It is a **scan list for Explore**, not a mandate to write one test per bullet on every ticket.

## Plan against E2E coverage first

Search, asset crud, and document editing already run in **E2E User Journey TCs**. Read `e2e-coverage.md` in the run directory.

- Behavior already asserted there → mark **covered**, cite the id, do not plan a duplicate case.
- This ticket **changes** the behavior and the walk reached it → plan **new**.
- Control the walk did not reach → **Gap**, not a planned case.

There is no minimum or maximum count of new tests.

## When you walk a listing, notice

Use these to fill the action coverage matrix and API Endpoints section. Only plan a **new** test when the ticket changes that behavior and coverage does not already assert it.

- **Loading** — placeholder or skeleton before the API returns; real rows after.
- **Row selection** — single-row checkbox or select.
- **Select all / deselect** — header checkbox and clearing selection.
- **Row actions** — open drawer, actions menu, inline edit.
- **Update / delete** — edit → save → persistence; delete → confirm → row gone.
- **Bulk actions** — multi-select → bulk menu (delete, move, archive, and similar).
- **Search** — filter results; clear restores the list; search from a later page returns to page 1 when that applies.
- **Sort** — column headers ascending and descending.
- **Filter** — apply, verify, clear.
- **Pagination** — next, previous, page number, row count labels ("Total X", "1–N of X").
- **Column visibility** — show and hide columns when the UI exposes it.
- **Empty state** — message when nothing matches.
- **API loading** — record method, URL pattern, and trigger for each data-changing action; Author uses `page.waitForResponse`, never `waitForTimeout` for data load.
- **CRUD round-trip** — create → list → update → delete when the ticket touches create or edit flows.
- **Permissions** — support and viewer when AC requires it; use `node scripts/persona.mjs` and record which persona saw each control.

## Surfaces with no E2E baseline

If the ticket is not on search, asset crud, or document editing, there is no checked-in journey. Plan from acceptance criteria and what the walk reached, still using this list as a reminder during Explore.
