# FEATURE: Create New Server Asset

**Spec:** `create-server.spec.ts` · 7 tests · last full run: green (2026-10-16)

## Scenarios

- [x] Clicking New opens the create drawer
- [x] Name field is required — Create disabled when empty
- [x] Create button enables when Name and Organization are set
- [x] Optional fields are visible in the Details tab
- [x] Cancel button closes the drawer without creating
- [x] Drawer Close (X) button closes the drawer
- [x] Navigating to a different asset type opens its create form

## Notes

- **Create enables only when both Name AND Organization are set** (from 2026-10-16 probe: Name alone never enables Create; the org combobox is required because the listing is the all-organizations view). Drawer org combobox: `combobox` filtered by `hasText: "Select organization"`, then first `getByRole('option')`.
- Create-state is debounce-driven — asserted with `expect.poll`, not fixed waits.
