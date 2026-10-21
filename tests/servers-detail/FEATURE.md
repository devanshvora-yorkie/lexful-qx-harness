# FEATURE: Server Detail Drawer

**Spec:** `servers-detail.spec.ts` · 10 tests · last full run: green (2026-10-16)

## Scenarios

- [x] Clicking a row opens the detail drawer
- [x] Detail drawer has Edit Name button
- [x] Overview tab shows Relationships section
- [x] Details tab shows all editable fields
- [x] Details tab shows additional fields
- [x] Drawer close button closes the drawer
- [x] Escape key closes the drawer
- [x] Copy link button is present
- [x] Expand record button is present
- [x] More actions button is present

## Notes

- Drawer opens via URL param: `?drawer=[{"type":"servers","id":"<uuid>"}]` (URL-encoded in the address bar).
- Each field has its own **Edit X** button; empty fields show **Add X**.
- Tests assert presence of edit affordances, not save-flows (see below).
