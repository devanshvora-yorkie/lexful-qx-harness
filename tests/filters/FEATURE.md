# FEATURE: Filters and Search (Servers listing)

**Spec:** `filters.spec.ts` · 12 tests · last full run: green (2026-10-16)

## Scenarios

- [x] Search filters by hostname/name
- [x] Search clears and shows all rows again
- [x] Search is case-insensitive
- [x] Partial search matches
- [x] Asset status filter button is visible
- [x] Filters panel opens and shows field selector
- [x] Column headers are present
- [x] Toolbar buttons are visible
- [x] Row checkboxes are present for selection
- [x] Select-all checkbox is present
- [x] Bulk action buttons appear when rows selected
- [x] Clear selection resets selection count

## Notes

- Deliberate overlap with `servers-listing` for the toolbar/checkbox grid checks — both entry points get exercised.
- Clear-selection assertion follows the bulk-actions note (count resets; buttons persist).
- Same grid-loading wait as servers-listing: wait for the real `AAA-SRV-001` row before interacting.
