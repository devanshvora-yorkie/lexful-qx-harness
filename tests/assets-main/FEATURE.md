# FEATURE: Assets Main Page (`/docs/assets`)

**Spec:** `assets-main.spec.ts` · 10 tests · last full run: green (2026-10-16)

## Scenarios

- [x] Page loads with Assets heading and counts
- [x] Displays asset type cards with counts (32 visible)
- [x] Clicking into Servers type navigates to listing
- [x] Clicking into Applications type navigates to listing
- [x] Search opens Ask Lex with matching records listbox
- [x] Search shows browse buttons for asset types
- [x] Ask Lex button opens AI panel
- [x] Top bar elements are visible
- [x] Sidebar navigation links are present
- [x] User menu opens and shows options

## Notes

- Searching on this page opens the **Ask Lex AI panel**, it does not filter cards (verified against live DOM).
- "Ask Lex" button exists 3× in the DOM (sidebar duplicates) — scoping uses `header`.

## Not covered (deliberately)

- "20 available" load-more (low value, fragile counts)
- Following user-menu links (Settings/Account/Platform navigate out of scope)
