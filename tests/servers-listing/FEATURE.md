# FEATURE: Servers Listing (`/docs/d/all/servers`)

**Spec:** `servers-listing.spec.ts` · 14 tests · last full run: green (2026-10-16)

## Scenarios

- [x] Page loads with heading and treegrid
- [x] Treegrid shows server rows with data (`AAA-SRV-001`)
- [x] Search filters by hostname/name
- [x] Search clears and shows all rows again
- [x] Asset status filter button is visible
- [x] Filters panel opens and shows field selector
- [x] Column headers are present (Name/Role/Hostname/…)
- [x] Toolbar buttons are visible
- [x] Row checkboxes are present for selection
- [x] Select-all checkbox is present ("Select loaded rows")
- [x] Open row detail drawer and verify
- [x] Detail drawer has all 8 tabs
- [x] Details tab shows editable fields
- [x] Overview tab shows linked items

## Notes

- **Grid is async**: rows render after data loads. Until then checkboxes show *"Row selection is disabled for this row"* with a "Row data is loading" cell — every `beforeEach` waits for the real `AAA-SRV-001` row, not just the grid viewport.
- Row checkboxes: `input[type=checkbox][aria-label*="Press Space"]` (no `role=checkbox`).
- Column headers match by exact text (no aria-labels) — `exact: true` prevents "Name" matching "Hostname".

## Not covered

- Column sort / Display column toggles / Collapse all
- Save-flows of inline edits (covered as presence checks in `servers-detail`)
