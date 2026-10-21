# FEATURE: Assets Manager — E2E Test Plan

**Resolved URL:** `https://e2e-test.uat.lexful.net/docs/assets`  
**Auth Method:** Custom `/auth/password` endpoint → injects `stytch_session` + `stytch_session_jwt` cookies on `.lexful.net`  
**Test User:** `e2e-test+admin@lexful.ai` (Admin role)  
**Organization:** `organization-live-2928086d-1015-4fc0-a3eb-898cade37abd`  
**Explored:** 2026-10-15 via playwright-cli  

---

## 1. Authentication Flow

### Endpoint
```
POST https://api.uat.lexful.net/auth/password
Content-Type: application/json

{
  "account_external_id": "organization-live-2928086d-1015-4fc0-a3eb-898cade37abd",
  "email": "e2e-test+admin@lexful.ai",
  "password": "<from env>"
}

Response: HTTP 204 No Content
Set-Cookie: stytch_session=...; Domain=.lexful.net; HttpOnly; Secure; SameSite=Lax
Set-Cookie: stytch_session_jwt=...; Domain=.lexful.net; HttpOnly; Secure; SameSite=Lax
```

### Cookie Injection (Playwright)
```js
await context.addCookies([{
  name: 'stytch_session', value: '<value>', domain: '.lexful.net', path: '/',
  httpOnly: true, secure: true, sameSite: 'Lax'
}, {
  name: 'stytch_session_jwt', value: '<value>', domain: '.lexful.net', path: '/',
  httpOnly: true, secure: true, sameSite: 'Lax'
}]);
```

### Auth Test Scenarios
- [ ] `auth-success`: POST /auth/password → HTTP 204 + both cookies present
- [ ] `auth-invalid-password`: Wrong password → HTTP 401
- [ ] `auth-invalid-email`: Non-existent email → HTTP 400 or 401
- [ ] `auth-cookie-domain`: Cookies set on `.lexful.net` apply to `e2e-test.uat.lexful.net`
- [ ] `auth-expired-cookie`: Expired cookie → redirect to /login

---

## 2. Navigation Structure

### Sidebar Menu (always visible)
| Item | URL | Count |
|------|-----|-------|
| Assets | `/docs/assets` | 1,038 |
| Organizations | `/docs/d/all/overview` | 26 |
| Expirations | `/docs/d/all/expirations` | 0 |
| Documents | `/docs/d/all/system.document` | 79 |
| Passwords | `/docs/d/all/system.password` | 313 |
| Contacts | `/docs/d/all/system.contact` | 93 |
| Locations | `/docs/d/all/system.location` | 38 |
| **ADMINISTRATION** | | |
| Settings | `/docs/platform` | — |
| Account | `https://.../platform/account` | — |
| Platform | `https://.../platform/settings` | — |

### Top Bar Elements
- Logo link → `/docs/` (home)
- "Ask Lex" button → opens AI chat panel
- Search bar `⌘K` → global search
- User avatar ("AE") → dropdown: Settings, Account, Platform, Feedback, Support
- Collapse navigation button

### Asset Type Cards (32 types on main page, 20 more behind "20 available")
Access Points(40), Applications(58), Backups(30), Cameras(29), Computers(95), Configurations(45), Contracts(20), Domains(20), Email Services(15), Firewalls(20), Internet Circuits(20), Licenses(29), Microsoft 365 Groups(40), Microsoft 365 Users(69), Mobile Devices(29), Nas Storage(14), Networks(37), Phone Systems(13), Policies(14), Printers(39), Remote Access(15), Server Hardware(5), Servers(47), Service Accounts(30), Software Inventory(78), Ssl Certificates(20), Switches(34), Ups Devices(20), Vendors(39), Virtual Machines(39), Wireless(35)

---

## 3. API Endpoints (observed during exploration)

| Action | Method | URL Pattern | Notes |
|--------|--------|-------------|-------|
| Auth login | POST | `https://api.uat.lexful.net/auth/password` | Custom proxy endpoint |
| Asset list | GET | `/docs/d/all/{type}` | Renders treegrid, data loaded client-side |
| Asset detail | GET | `/docs/d/all/{type}?drawer=[{type,id}]` | Drawer with UUID |
| Create asset | POST | (via drawer) | URL: `?drawer=[{type,id:"new"}]` |
| Update field | PATCH (likely) | (via edit buttons) | Inline edit per field |

---

## 4. Action Coverage Matrix

### 4a. Main Assets Page (`/docs/assets`)

| Action | Admin | Advisor | Viewer |
|--------|-------|---------|--------|
| View asset type cards | [x] | [?] | [?] |
| Click into asset type | [x] | [?] | [?] |
| "New" button (create) | [x] | [?] | [?] |
| "Display options" | [x] | [?] | [?] |
| Search assets | [x] | [?] | [?] |
| Filter by Organization | [x] | [?] | [?] |
| Filter by Asset type | [x] | [?] | [?] |
| "Ask Lex" AI panel | [x] | [x] | [x] |
| Load more (20 available) | [x] | [?] | [?] |

### 4b. Asset Listing Page (`/docs/d/all/servers` — representative)

| Action | Admin |
|--------|-------|
| Search by hostname/name | [x] |
| Filter by Asset status (Active/Inactive/etc.) | [x] |
| Open Filters panel → choose field + condition | [x] |
| Filter by Organization combobox | [x] |
| Filter by Tags combobox | [x] |
| Sort columns (click header) | [?] |
| Toggle column visibility (Display) | [x] |
| Select single row checkbox | [x] |
| Select all rows checkbox ("Select loaded rows") | [x] |
| Deselect all after select-all | [x] |
| Bulk: Access button | [x] |
| Bulk: Tags button | [x] |
| Bulk: Actions button | [x] |
| Bulk: Clear selection | [x] |
| Click row → open detail drawer | [x] |
| Detail: Overview tab | [x] |
| Detail: Details tab (edit fields) | [x] |
| Detail: Relationships tab | [?] |
| Detail: Attachments tab | [?] |
| Detail: Access tab | [?] |
| Detail: History tab | [?] |
| Detail: Sources tab | [?] |
| Detail: System info tab | [?] |
| Edit Name inline | [x] |
| Edit Role inline | [?] |
| Edit IP Address inline | [?] |
| Create new asset via "New" button | [x] |
| Cancel create | [x] |
| Validate required fields on create | [x] |
| "Collapse all" in treegrid | [?] |

### 4c. User Menu

| Action | Admin |
|--------|-------|
| Click avatar → menu opens | [x] |
| Settings link | [x] |
| Account link | [x] |
| Platform link | [x] |
| Feedback link | [x] |
| Support button | [?] |

---

## 5. Test File Plan

### POM Structure
```
lexful-test/
├── FEATURE.md                    ← this overview
├── .agents/skills/lexful-autonomous-agent-qa/  ← project QA skill: SKILL.md + references/custom-instructions.md
├── auth-helper.ts                ← cookie load + expiry-checked API refresh
├── auth-state.json               ← saved session cookies
└── tests/
    ├── common-pom.ts             ← shared shell locators (sidebar, topbar, drawers)
    ├── auth/FEATURE.md + auth.spec.ts
    ├── assets-main/FEATURE.md + assets-main.spec.ts + assets-listing-pom.ts
    ├── servers-listing/FEATURE.md + servers-listing.spec.ts + servers-listing-pom.ts
    ├── servers-detail/FEATURE.md + servers-detail.spec.ts + servers-detail-pom.ts
    ├── create-server/FEATURE.md + create-server.spec.ts + create-asset-pom.ts
    ├── bulk-actions/FEATURE.md + bulk-actions.spec.ts   ← pom via ../servers-listing/
    └── filters/FEATURE.md + filters.spec.ts             ← pom via ../servers-listing/
```

### Test Scenarios by Feature

Each feature's scenarios and live status of record:

| Feature | Tests | Status |
|---|---|---|
| [auth](tests/auth/FEATURE.md) | 4 | green |
| [assets-main](tests/assets-main/FEATURE.md) | 10 | green |
| [assets-empty-types](tests/assets-empty-types/FEATURE.md) | 15 | green (LEX-3500) |
| [servers-listing](tests/servers-listing/FEATURE.md) | 14 | green |
| [servers-detail](tests/servers-detail/FEATURE.md) | 10 | green |
| [create-server](tests/create-server/FEATURE.md) | 7 | green |
| [bulk-actions](tests/bulk-actions/FEATURE.md) | 7 | green |
| [filters](tests/filters/FEATURE.md) | 12 | green |

*(Last full run 2026-10-16: 64/64 passing. Original per-spec planning lists live in git history / the linked files supersede them.)*

---

## 6. Known UI Patterns & Pitfalls

### Treegrid (not standard table)
- Uses `treegrid` role with `row`, `rowgroup`, `columnheader`, `gridcell` elements
- Rows have checkboxes with text: "Press Space to toggle row selection (unchecked)"
- Header checkbox: "Select loaded rows" (not "Select all" — only loads visible page)

### Drawers (not modals)
- Side drawers open via URL query params: `?drawer=[{type:"servers",id:"new"}]` or `?drawer=[{type:"servers",id:"<uuid>"}]`
- Close button has text "Close" — no aria-label
- "Expand record" button expands drawer to full-screen

### Inline Editing
- Each field has its own edit button: "Edit Name", "Edit Role", "Edit IP Address", etc.
- "Add" for empty fields: "Add Hostname", "Add Parent Host"
- Create button is disabled until Name and Organization are set (org picker is required when creating from the all-organizations view)

### Ask Lex Panel
- Fixed right-side panel with input area
- Input placeholder: "Ask Lex anything…"
- Connector hints: "@ mention · / skills"
- Quick action buttons: "Find a password", "Look up a contact", "Draft a playbook"
- Submit button is disabled when input is empty

### Asset Status Filter
- Default shows "Asset status: Active" as a pill/button
- Clicking opens status options (likely: Active, Inactive, Archived, etc.)

### Organization Selector
- Combobox labeled "All Organizations"
- Located in sidebar and in listing page filter bar
- Multiple organizations have data (26 total)

---

## 7. Execution Commands

### Run all tests
```bash
cd ~/lexful-test && npx playwright test --workers=1 --timeout=30000   # 1 worker: UAT rate limits
```

### Run single feature
```bash
npx playwright test tests/auth/
```

### With headed browser (for debugging)
```bash
npx playwright test --headed
```

### Auth state refresh
No manual step — `auth-helper.ts` checks `auth-state.json` expiry on first test and refreshes via API when stale.

---

## 8. Reference: Element Refs from Exploration Session

These refs are valid for the snapshot taken at `2026-10-15T06:47:41Z`. They may change on re-exploration but serve as examples of locator patterns:

| Element | Pattern | Example Ref |
|---------|---------|-------------|
| User avatar | `button:has-text("AE")` | f4e12 |
| Sidebar collapse | `button "Collapse navigation"` | f3e21 |
| Asset type link (Servers) | `getByRole('link', { name: 'Servers' })` | f3e446 |
| Search box (listing) | `textbox "Search Servers..."` | f3e620 |
| Asset status filter | `button "Asset status: Active"` | f3e621 |
| Filters button | `button "Filters"` | f3e622 |
| Display button | `button "Display"` | f3e613 |
| New button | `button "New"` | f3e614 |
| Treegrid | `[role=treegrid]` | f3e630 |
| Row checkbox | `checkbox:has-text("Press Space")` | varies per row |
| Create drawer name field | `textbox "Name" [active]` | f3e1586 |
| Create Cancel button | `button "Cancel"` | f3e1665 |
| Create Create button | `button "Create"` | disabled until Name + Organization set |
| Detail drawer close | `button "Close"` | f3e2467 |
| Detail Overview tab | `tab "Overview"` | f3e2484 |
| Detail Details tab | `tab "Details"` | f3e2485 |

---

## 9. Test Data Dependencies

- **Servers**: 47 servers across 20 organizations, sample: AAA-SRV-001 (Domain Controller, 10.27.10.20)
- **Applications**: 58 apps
- **Computers**: 95 computers
- **Passwords**: 313 passwords (some linked to assets via Relationships tab)
- **Organizations**: 26 orgs (sample: Adipiscing Aliqua Academy, Adipiscing Market LLC)

Test creation/deletion should use unique names (e.g., `E2E-Test-SRV-${timestamp}`) to avoid conflicts.
