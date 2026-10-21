# FEATURE: Bulk Actions — Row Selection

**Spec:** `bulk-actions.spec.ts` · 7 tests · last full run: green (2026-10-16)

## Scenarios

- [x] Row checkboxes are present and clickable
- [x] Selecting a row shows bulk action buttons
- [x] Selecting all rows via header checkbox
- [x] Deselecting one row after select-all decreases count
- [x] Clear selection resets selection count
- [x] Multiple rows can be selected
- [x] Bulk Actions button is present when rows are selected

## Notes

- **Bulk buttons (Access/Tags/Actions/Clear selection) stay in the DOM even at "0 selected"** — verified from failure snapshots. "Clear selection" therefore asserts the count resets to `0 selected`, *not* that buttons disappear.
- An overlay div (`.flex.flex-1.flex-col.gap-4.px-6.pb-12.pt-6`) intercepts pointer events on **Clear selection** and **Actions** — those clicks use `force: true`.
