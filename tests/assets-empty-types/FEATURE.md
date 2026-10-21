# FEATURE: Assets overview — empty asset types with quick add (LEX-3500)

**Resolved URL:** `https://e2e-test.uat.lexful.net/docs/assets`
**Type list URL:** `https://e2e-test.uat.lexful.net/docs/d/all/<type>`
**Auth:** saved `auth-state.json` cookies (preflight, support login `SE`) via `injectAuthCookies`
**Explored:** 2026-10-16 via playwright-cli (live UAT DOM)
**Ticket:** LEX-3500 — "Asset types missing from asset type list page"
**PR:** #1579 — "LEX-3500: Show empty asset types with quick add" (merged 2026-10-08)

---

## 1. What changed (from the PR diff)

- `apps/docu-app/src/routes/_/assets.tsx` — the overview no longer filters out zero-count types. Each category keeps populated types visible and places eligible empty types behind an independent **"N available"** `Collapsible` disclosure, collapsed by default. Header summary counts all eligible types.
- `apps/docu-app/src/components/assets/AssetEmptyState.tsx` — asset-list empty states now name the asset type: **"No Active Directory yet"**, **"Add Active Directory to get started."**, **"Add Active Directory"**.
- `apps/docu-app/src/components/assets/AssetPropertiesGrid.tsx` + `AssetCreateForm.tsx` — creation autofocus uses the first field in the saved display layout.

## 2. Live observations (2026-10-16)

| Observation | Value |
|---|---|
| Header summary | `1,038 assets · 52 types` |
| Category heading | `UNCATEGORIZED` (only category in this org scope) |
| Populated type rows | 31 cards with real counts (e.g. Servers 47) |
| Empty-type disclosure | button **"21 available"**, `aria-expanded="false"` by default |
| Empty rows after expand | 21 cards, each with a `0` count + an `Add <type>` button |
| 31 populated + 21 empty | = 52 = header "types" count |
| Empty row link class | `after:absolute after:inset-0 text-muted-foreground` (muted) |
| Populated row link class | `after:absolute after:inset-0` (not muted) |
| `Add <type>` button class | `[@media(hover:hover)]:opacity-0 group-hover:opacity-100 group-focus-within:opacity-100` |
| Add button opacity (no hover/focus) | `0` |
| Add button opacity (row hover) | `1` |
| Add button opacity (row focus-within) | `1` |
| Collapsed content | not rendered (empty-type link `count() === 0`) |
| Keyboard | focus disclosure → `Enter` expands, `Space` collapses |
| Quick-add URL | `?drawer=[{"type":"active_directory","id":"new"}]` |
| Drawer heading | `New Active Directory` |
| First focused field | textbox `Enter domain controller` (first displayed field) |
| Empty-state copy | heading `No Active Directory yet`, body `Add Active Directory to get started.`, button `Add Active Directory` |

## 3. API Endpoints

| Action | Method | URL pattern |
|---|---|---|
| Asset types (overview) | GET | `/v1/asset_types?limit=200` |
| Asset counts | GET | `/v1/assets/counts` |
| Categories | GET | `/v1/asset_categories?limit=200&offset=0` |
| Asset type definition (drawer) | GET | `/v1/asset_types?name=<type>` |
| Organizations (drawer) | GET | `/v1/organizations?limit=1000` |

Data loads once on navigation; expanding the disclosure and quick-add are client-side except the drawer's `/v1/asset_types?name=<type>` fetch.

## 4. Action coverage matrix — `/docs/assets`

| Action | Support user |
|---|---|
| Header summary (assets + all types) | [x] |
| Empty types hidden by default | [x] |
| Disclosure accessible name / collapsed / focusable | [x] |
| Expand disclosure → empty rows + 0 count + list link | [x] |
| Muted styling vs populated | [x] |
| Disclosure count == empty row count | [x] |
| Keyboard Enter/Space toggle | [x] |
| Collapse re-hides empty rows | [x] |
| Hover reveals `+ Add <type>` | [x] |
| Focus-within reveals `+ Add <type>` | [x] |
| Quick-add opens drawer with type preselected | [x] |
| Exclusions (Files + primary-nav types) | [x] |
| Empty type link navigates to list | [x] |
| Empty-state capitalized copy + action | [x] |
| Empty-state action opens drawer | [x] |

## 5. Test plan (15 tests) — `assets-empty-types.spec.ts`

**Status: 15/15 green — last run 2026-10-16 (`npx playwright test tests/assets-empty-types/ --workers=1`).**

- [x] 1. header summary shows asset total and the count of all eligible types
- [x] 2. empty types are hidden behind a collapsed disclosure by default
- [x] 3. disclosure is labelled "<N> available", starts collapsed, is keyboard-focusable
- [x] 4. expanding reveals empty rows with a `0` count and the type list link
- [x] 5. empty rows use muted styling; populated rows do not
- [x] 6. disclosure count equals the number of empty rows / Add buttons
- [x] 7. keyboard: Enter expands, Space collapses (`aria-expanded`)
- [x] 8. collapsing hides the empty rows again (round trip)
- [x] 9. hovering an empty row reveals the `+ Add <type>` button
- [x] 10. focusing an empty row reveals the `+ Add <type>` button (focus-within)
- [x] 11. quick-add opens the creation drawer with the type preselected + org context + first-field autofocus
- [x] 12. Files and primary-navigation types are excluded from the cards
- [x] 13. an empty type's link navigates to its list page
- [x] 14. asset-list empty state uses capitalized type copy and an Add action
- [x] 15. the empty-state Add action opens the create drawer with the type preselected

## 6. Files

- `tests/assets-empty-types/assets-empty-types-pom.ts`
- `tests/assets-empty-types/assets-empty-types.spec.ts`
- `tests/assets-empty-types/FEATURE.md`

## 7. Execution

```bash
npx playwright test tests/assets-empty-types/ --workers=1
```

## 8. Data dependencies & notes

- Anchored on **Active Directory** (`/docs/d/all/active_directory`), a seeded type that is currently empty (0 records) and sorts first in the disclosure. If it is ever populated, tests 4–11/13–15 need a different empty type (the disclosure count test #6 stays data-driven).
- The disclosure label is data-driven (`/^\d+ available$/`); test #6 asserts label vs live row count rather than a hardcoded 21.
- No new API is called on expand — expansion is client-side; data tests wait for the initial `asset_types`/`assets/counts` responses.
- Support user has create permission, so empty rows expose the `Add` button and the org combobox is present but unselected in the drawer.
- Drawers appear as `role="dialog"`; create stays disabled until required fields are set.
