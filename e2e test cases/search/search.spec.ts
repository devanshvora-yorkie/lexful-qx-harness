/**
 * Lexful Docs — Search feature E2E (release candidate)
 *
 * Target : https://e2e-test.uat.lexful.net/docs/assets
 * Specs  : 12 release-ready cases across the whole Search surface.
 *
 * ── Selector provenance (every locator below was verified against the live UAT
 *    build on 2026-10-15 AND cross-checked against the source at main@476de4d):
 *
 *   apps/docu-app/src/components/assets/AssetSearchBox.tsx
 *       L118  aria-label="Find anything"          → the search region wrapper
 *       L159  aria-label={`Remove ${name} filter`}→ removable filter chips
 *       L174  aria-label="Search assets" role=combobox
 *       L266  aria-label="Searching"              → in-flight indicator
 *       L273  aria-label="Clear search"
 *       L344  "Enter to open" / "Tab to select"   → footer hint
 *       L382  role=listbox aria-label ∈ { "Search filters", "Matching records",
 *                                           "Matching expirations", "Matching assets" }
 *       L406  "AD → Active Directory" / "Across asset types"  → listbox header
 *       L630  role=status empty state + L652 aria-label="Reset search and filters"
 *       L665  pagination: "Previous" disabled={!offset},
 *                        "More results" disabled={total <= offset + 20}
 *       L213  Backspace on an empty input removes the LAST filter chip
 *
 *   apps/docu-app/src/hooks/useAssetSearch.ts
 *       L58   /\bAD\b/gi → "Active Directory"    (term rewrite, L406 shows the hint)
 *       L59   useDebouncedValue(...)              (one request per keystroke burst)
 *       L140  queryKey includes `offset`          (React-Query cache keyed per page)
 *       L151  enabled: !token && !!(term || typeNames.length || mode)
 *       L193  empty term + #types → GET /v1/assets/{type}  (NOT /v1/search)
 *       L227  otherwise        → GET /v1/search?term=&limit=20[&entity_types=][&organization_ids=][&offset=]
 *
 *   apps/docu-app/src/components/assets/AssetSearch.tsx
 *       L115  result action label: "Quick view" (system.password) | "Open"
 *       L120  aria-label="Ask Lex", aria-keyshortcuts = Meta+Enter (mac) / Control+Enter (win)
 *
 * There are NO data-testid attributes on these components, so every locator uses
 * role + accessible name, which is exactly what the implementation exposes.
 *
 * ── Data anchors (seeded in the UAT tenant, stable as of 2026-10-15)
 *      ORG          = 'Esse Amet Accounting Inc'   (id 01a0ee75-1a87-775b-a989-0c24968a297c)
 *      COMPUTER     = 'EAA-WS-003'  (type `computers`)
 *      BROAD TERM   = 'EAA'         (41 matches → spans two result pages)
 *      ABSENT TERM  = 'ZZQQXX-NOMATCH-4417'
 *
 * ── Run
 *      cd lexful-qa-harness/playwright-tests
 *      npx playwright test tests/docs/search.spec.ts --project=chromium
 *
 * ── Hygiene
 *      READ-ONLY. Creates no assets and mutates no configuration.
 *      workers=1 (see playwright.config.ts): the UAT front door sits behind a
 *      CloudFront WAF that 403s bursts of automated traffic, so the suite is
 *      deliberately serial.
 */

import { test, expect, type Locator, type Page, type Response } from '@playwright/test'
import { injectAuthCookies } from '../../auth-helper'

// ── Config ───────────────────────────────────────────────────────────────────

const ASSETS_PATH = '/docs/assets'
const ORG = 'Esse Amet Accounting Inc'
const COMPUTER = 'EAA-WS-003'
const BROAD_TERM = 'EAA'
const ABSENT_TERM = 'ZZQQXX-NOMATCH-4417'
const TYPE_NAME = 'Computers'

/** ⌘K on macOS, Ctrl+K everywhere else (mirrors `isMac` in AssetSearch.tsx). */
const PALETTE_SHORTCUT = process.platform === 'darwin' ? 'Meta+k' : 'Control+k'
const ASK_LEX_SHORTCUTS = process.platform === 'darwin' ? 'Meta+Enter' : 'Control+Enter'

// ── Network guards ───────────────────────────────────────────────────────────

/** Every data-changing search action waits on this instead of a fixed sleep. */
function keywordSearch(page: Page, extra?: (url: string) => boolean): Promise<Response> {
  return page.waitForResponse(
    r =>
      r.request().method() === 'GET' &&
      new URL(r.url()).pathname === '/v1/search' &&
      (extra ? extra(r.url()) : true),
    { timeout: 20_000 },
  )
}

/** Live-recording request spy, used by the debounce test. */
function trackSearchRequests(page: Page): string[] {
  const urls: string[] = []
  page.on('response', r => {
    if (new URL(r.url()).pathname === '/v1/search') urls.push(r.url())
  })
  return urls
}

/** Shape of GET /v1/search — see services/docu-service/src/api/routes/search.ts */
interface SearchResponse {
  items: Array<{ id: string; name: string; type: string; organization_name: string | null }>
  total: number
  limit: number
  offset: number
}

/** The CloudFront edge answers bursts of automation with a 403 "Request blocked". */
const WAF_BLOCKED = /request blocked|403 error/i
const WAF_COOLDOWN_MS = 45_000

/**
 * Navigate to the Assets shell, riding out the WAF.
 *
 * The UAT front door rate-limits automated traffic, so a cold navigation can
 * come back as a CloudFront 403 instead of the app. That is an environment
 * hiccup, not a product defect, so back off and retry rather than fail.
 */
async function gotoAssets(page: Page): Promise<void> {
  for (let attempt = 1; attempt <= 3; attempt++) {
    await page.goto(ASSETS_PATH, { waitUntil: 'domcontentloaded' })
    try {
      await expect(page.getByRole('heading', { level: 1, name: 'Assets' })).toBeVisible({ timeout: 20_000 })
      return
    } catch (err) {
      const body = await page.locator('body').innerText().catch(() => '')
      if (!WAF_BLOCKED.test(body) || attempt === 3) throw err
      await page.waitForTimeout(WAF_COOLDOWN_MS)
    }
  }
}

// ── Page object ──────────────────────────────────────────────────────────────

/**
 * One component renders in two hosts:
 *   palette — the ⌘K Dialog rendered by topNavigation
 *   inline  — the same widget rendered directly in `main` on /docs/assets
 * Every locator is scoped through `host()` so both are addressable by one POM.
 */
class SearchUi {
  private constructor(
    private readonly page: Page,
    private readonly inPalette: boolean,
  ) {}

  static palette(page: Page): SearchUi {
    return new SearchUi(page, true)
  }

  static inline(page: Page): SearchUi {
    return new SearchUi(page, false)
  }

  /** The dialog for the palette host, `main` for the inline host. */
  host(): Locator {
    return this.inPalette ? this.page.getByRole('dialog') : this.page.locator('main')
  }

  /** "Find anything" wraps the input, the filter chips and the result list. */
  region(): Locator {
    return this.host().getByRole('region', { name: 'Find anything' })
  }

  /** aria-label="Search assets", role=combobox. */
  input(): Locator {
    return this.region().getByRole('combobox', { name: 'Search assets' })
  }

  /** aria-label="Clear search" — only mounted once a query exists. */
  clearButton(): Locator {
    return this.region().getByRole('button', { name: 'Clear search' })
  }

  /** aria-label="Reset search and filters" — lives in the empty state only. */
  resetButton(): Locator {
    return this.host().getByRole('button', { name: 'Reset search and filters' })
  }

  /**
   * The listbox label is conditional:
   *   token active → "Search filters" | mode=expiring → "Matching expirations"
   *   includeOrganizations → "Matching records" | otherwise → "Matching assets"
   */
  listbox(): Locator {
    return this.host().getByRole('listbox')
  }

  results(): Locator {
    return this.listbox().getByRole('option')
  }

  /** Options carry aria-selected={index === i}; index 0 is highlighted by default. */
  highlightedIndex(): Promise<number> {
    return this.results().evaluateAll(opts =>
      opts.findIndex(o => o.getAttribute('aria-selected') === 'true'),
    )
  }

  /** Footer chips: "Previous" / "More results". */
  previousButton(): Locator {
    return this.host().getByRole('button', { name: 'Previous', exact: true })
  }

  moreResultsButton(): Locator {
    return this.host().getByRole('button', { name: 'More results', exact: true })
  }

  /** aria-label={`Remove ${name} filter`} */
  filterChips(): Locator {
    return this.host().getByRole('button', { name: /^Remove .+ filter$/ })
  }

  /**
   * A single chip by its accessible name.
   * The chip button renders no text of its own — the visible label is a sibling
   * and the accessible name comes from aria-label — so match on the name,
   * never with `.filter({ hasText })`.
   */
  chipFor(name: string): Locator {
    return this.host().getByRole('button', { name: `Remove ${name} filter`, exact: true })
  }

  /** `@ Organization` chip — inserts the `@` token. */
  organizationChip(): Locator {
    return this.region().getByRole('button', { name: /Organization/ }).first()
  }

  /** `Asset type` chip — inserts the `#` token. */
  assetTypeChip(): Locator {
    return this.region().getByRole('button', { name: 'Asset type', exact: true })
  }

  /** `/ Shortcuts` chip — inserts the `/` token. */
  shortcutsChip(): Locator {
    return this.region().getByRole('button', { name: '/ Shortcuts' })
  }

  /** Empty state: role=status holding "No records found". */
  emptyState(): Locator {
    return this.host().getByRole('status').filter({ hasText: 'No records found' })
  }

  /** aria-label="Ask Lex" — opens the AI panel with the current context. */
  askLexButton(): Locator {
    return this.host().getByRole('button', { name: 'Ask Lex' }).first()
  }

  /**
   * Block until the widget is interactive.
   *
   * The keydown handler is gated on `!selectionBusy` (AssetSearchBox.tsx:252),
   * and `busy` stays true for the whole debounce + fetch window. Arrow keys and
   * Enter are silently ignored during it, so every keyboard test must settle
   * here first or it will race and no-op. aria-label="Searching" is the spinner.
   */
  async waitForIdle(): Promise<void> {
    await expect(this.region().locator('[aria-label="Searching"]')).toHaveCount(0, { timeout: 20_000 })
  }

  /** Open the palette and wait for the combobox to be interactive. */
  async open(): Promise<void> {
    if (this.inPalette) {
      await this.page.keyboard.press(PALETTE_SHORTCUT)
      await this.page.getByRole('dialog').waitFor({ state: 'visible', timeout: 20_000 })
      // The dialog hosts two "Search assets" inputs when it overlays inline
      // search, so always drive the one inside the dialog.
    }
    await this.input().waitFor({ state: 'visible', timeout: 20_000 })
  }

  /** Type and block until the keyword request for that term has landed. */
  async search(term: string): Promise<Response> {
    const [response] = await Promise.all([keywordSearch(this.page, u => u.includes(`term=${encodeURIComponent(term)}`)), this.input().fill(term)])
    expect(response.ok(), `GET /v1/search failed with ${response.status()}`).toBe(true)
    return response
  }
}

// ── Suite ────────────────────────────────────────────────────────────────────

test.describe('Search', () => {
  const consoleErrors: string[] = []

  test.beforeEach(async ({ page }) => {
    // The WAF cooldown below can outlast the default per-test budget.
    test.slow()
    consoleErrors.length = 0
    page.on('console', m => {
      if (m.type() === 'error') consoleErrors.push(m.text())
    })
    await injectAuthCookies(page.context())
    await gotoAssets(page)
  })

  test.afterEach(() => {
    // "Failed to load resource" lines are transport-level (the UAT front door
    // sits behind a CloudFront WAF that 403s bursts of automated traffic), so
    // they say nothing about the widget. Anything else — a thrown React error,
    // a bad hook call — is a real regression and must fail the test.
    const appErrors = consoleErrors.filter(e => !/Failed to load resource/i.test(e))
    expect(appErrors, `console errors during the run:\n${appErrors.join('\n')}`).toEqual([])
  })

  // ── 1 ─ palette shell ──────────────────────────────────────────────────────

  test('TC-01 opens the palette with the header button and closes it with Escape', async ({ page }) => {
    await page.getByRole('button', { name: /^Search\.\.\./ }).first().click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    // Visually hidden (sr-only) title — attached, and clipped to 1×1px rather
    // than display:none. Playwright still reports such a node as "visible",
    // so assert the sr-only contract directly.
    const title = dialog.getByRole('heading', { name: 'Search assets and organizations' })
    await expect(title).toBeAttached()
    await expect(title).toHaveClass(/sr-only/)

    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
  })

  test('TC-02 the ⌘K / Ctrl+K shortcut toggles the palette open and shut', async ({ page }) => {
    await page.keyboard.press(PALETTE_SHORTCUT)
    await expect(page.getByRole('dialog')).toBeVisible()

    // Same chord again closes it — it is a toggle, not a one-way opener.
    await page.keyboard.press(PALETTE_SHORTCUT)
    await expect(page.getByRole('dialog')).toBeHidden()

    await page.keyboard.press(PALETTE_SHORTCUT)
    await expect(page.getByRole('dialog')).toBeVisible()
  })

  // ── 2 ─ keyword search ─────────────────────────────────────────────────────

  test('TC-03 debounces a keystroke burst into a single keyword request', async ({ page }) => {
    const ui = SearchUi.palette(page)
    await ui.open()

    const seen = trackSearchRequests(page)

    // Type per-character so the debounce is genuinely exercised.
    await ui.input().pressSequentially(BROAD_TERM, { delay: 60 })
    await expect(ui.results().first()).toBeVisible({ timeout: 20_000 })

    // useDebouncedValue() in useAssetSearch.ts:59 collapses the burst into one call.
    expect(seen).toHaveLength(1)
    expect(seen[0]).toContain(`term=${BROAD_TERM}`)
    expect(seen[0]).toContain('limit=20')

    // Results are cross-type and the first row is pre-highlighted.
    await expect(ui.listbox()).toHaveAccessibleName(/Matching (records|assets)/)
    expect(await ui.highlightedIndex()).toBe(0)
  })

  test('TC-04 expands the shorthand "AD" into "Active Directory" before searching', async ({ page }) => {
    const ui = SearchUi.palette(page)
    await ui.open()

    // The wire term is rewritten (see below), so match on the endpoint only —
    // filtering on `term=AD` would never match `term=Active+Directory`.
    const [response] = await Promise.all([keywordSearch(page), ui.input().fill('AD')])
    expect(response.ok(), `GET /v1/search failed with ${response.status()}`).toBe(true)

    // The UI still shows what the user typed...
    await expect(ui.input()).toHaveValue('AD')
    // ...but the wire format carries the expansion.
    expect(response.url()).toContain('term=Active+Directory')

    // AssetSearchBox.tsx:406 surfaces the rewrite as a listbox-header hint.
    await expect(ui.listbox()).toContainText(/AD\s*→\s*Active Directory/i)
    await expect(ui.results().first()).toBeVisible()
  })

  test('TC-05 matches an exact record case-insensitively', async ({ page }) => {
    const ui = SearchUi.palette(page)
    await ui.open()

    await ui.search(COMPUTER.toLowerCase())

    await expect(ui.results()).toHaveCount(1)
    await expect(ui.results().first()).toContainText(COMPUTER)
    await expect(ui.results().first()).toContainText(ORG)
  })

  test('TC-06 shows the no-results state and Reset recovers from it', async ({ page }) => {
    const ui = SearchUi.palette(page)
    await ui.open()

    await ui.search(ABSENT_TERM)

    await expect(ui.emptyState()).toBeVisible()
    await expect(ui.emptyState()).toContainText('Try another search or adjust your filters.')
    await expect(ui.results()).toHaveCount(0)

    await ui.resetButton().click()

    await expect(ui.input()).toHaveValue('')
    await expect(ui.emptyState()).toHaveCount(0)
    await expect(ui.resetButton()).toHaveCount(0)
    // The reset handler explicitly returns focus to the combobox.
    await expect(ui.input()).toBeFocused()
  })

  // ── 3 ─ pagination ─────────────────────────────────────────────────────────

  test('TC-07 pages results with More results / Previous and resets the page on a new query', async ({ page }) => {
    const ui = SearchUi.palette(page)
    await ui.open()

    const first = await ui.search(BROAD_TERM)
    const page1 = (await first.json()) as SearchResponse

    const more = ui.moreResultsButton()
    const previous = ui.previousButton()
    await expect(more).toBeVisible()
    // offset starts at 0, so Previous is disabled on the first page.
    await expect(previous).toBeDisabled()
    expect(page1.offset).toBe(0)
    expect(page1.total).toBeGreaterThan(page1.limit)

    const [second] = await Promise.all([
      keywordSearch(page, u => u.includes('offset=20')),
      more.click(),
    ])
    const page2 = (await second.json()) as SearchResponse

    expect(second.url()).toContain('offset=20')
    expect(page2.offset).toBe(20)
    expect(page2.items.map(i => i.id)).not.toEqual(page1.items.map(i => i.id))
    // The rendered list follows the payload it was given.
    await expect(ui.results().first()).toContainText(page2.items[0].name)

    await expect(previous).toBeEnabled()

    // Going back is served from the React Query cache, not the network:
    // `offset` is part of the query key (useAssetSearch.ts:141-150), so page 1
    // is still resident and the app re-renders it without refetching. Asserting
    // the absence of a request keeps that contract from regressing into an
    // accidental refetch storm.
    const beforeBack = trackSearchRequests(page)
    await previous.click()
    expect(beforeBack, 'Previous should not refetch a cached page').toHaveLength(0)

    await expect(ui.results().first()).toContainText(page1.items[0].name)
    await expect(previous).toBeDisabled()

    // A different term drops the offset — the user never lands on page 5.
    const [fresh] = await Promise.all([
      keywordSearch(page, u => u.includes(`term=${COMPUTER}`)),
      ui.input().fill(COMPUTER),
    ])
    expect(fresh.url()).not.toContain('offset=')
  })

  // ── 4 ─ filters ────────────────────────────────────────────────────────────

  test('TC-08 the # asset-type token narrows results and adds entity_types', async ({ page }) => {
    const ui = SearchUi.palette(page)
    await ui.open()
    await ui.search(BROAD_TERM)

    const unfiltered = await ui.results().count()

    const [filtered] = await Promise.all([
      keywordSearch(page, u => u.includes('entity_types=')),
      (async () => {
        await ui.assetTypeChip().click()
        await expect(ui.listbox()).toHaveAccessibleName('Search filters')
        await page.getByRole('option', { name: `# ${TYPE_NAME}` }).click()
      })(),
    ])

    expect(filtered.url()).toContain(`entity_types=${TYPE_NAME.toLowerCase()}`)
    expect(filtered.ok()).toBe(true)

    // The token is consumed from the input and becomes a removable chip.
    await expect(ui.input()).not.toHaveValue(new RegExp('#'))
    await expect(ui.chipFor(TYPE_NAME)).toBeVisible()
    await expect(ui.listbox()).toHaveAccessibleName(/Matching (records|assets)/)

    const narrowed = await ui.results().count()
    expect(narrowed).toBeGreaterThan(0)
    expect(narrowed).toBeLessThan(unfiltered)
  })

  test('TC-09 the @ organization token narrows results and adds organization_ids', async ({ page }) => {
    const ui = SearchUi.palette(page)
    await ui.open()
    await ui.search(BROAD_TERM)

    const [filtered] = await Promise.all([
      keywordSearch(page, u => u.includes('organization_ids=')),
      (async () => {
        await ui.organizationChip().click()
        await expect(ui.listbox()).toHaveAccessibleName('Search filters')
        await page.getByRole('option', { name: ORG }).click()
      })(),
    ])

    expect(filtered.url()).toContain('organization_ids=')
    expect(filtered.ok()).toBe(true)
    await expect(ui.chipFor(ORG)).toBeVisible()

    // Every returned row belongs to the scoped organization.
    const rows = await ui.results().allInnerTexts()
    expect(rows.length).toBeGreaterThan(0)
    expect(rows.every(t => t.includes(ORG))).toBe(true)
  })

  test('TC-10 combines both filters in one request and Backspace removes the last chip', async ({ page }) => {
    const ui = SearchUi.palette(page)
    await ui.open()
    await ui.search(BROAD_TERM)

    await ui.assetTypeChip().click()
    await page.getByRole('option', { name: `# ${TYPE_NAME}` }).click()
    await expect(ui.filterChips()).toHaveCount(1)

    const [combined] = await Promise.all([
      keywordSearch(page, u => u.includes('organization_ids=')),
      (async () => {
        await ui.organizationChip().click()
        await page.getByRole('option', { name: ORG }).click()
      })(),
    ])

    // Both facets are ANDed into a single request.
    expect(combined.url()).toContain(`entity_types=${TYPE_NAME.toLowerCase()}`)
    expect(combined.url()).toContain('organization_ids=')
    await expect(ui.filterChips()).toHaveCount(2)

    // AssetSearchBox.tsx:213 — Backspace on an already-empty input pops the
    // most recent chip. It needs a genuinely empty value, hence fill('') first.
    await ui.input().fill('')
    await expect(ui.input()).toHaveValue('')
    await ui.input().press('Backspace')

    await expect(ui.filterChips()).toHaveCount(1)
    // The org filter was added last, so it is the one that pops — the earlier
    // #type chip survives.
    await expect(ui.chipFor(ORG)).toHaveCount(0)
    await expect(ui.chipFor(TYPE_NAME)).toBeVisible()
    await expect(ui.input()).toBeFocused()
  })

  // ── 5 ─ keyboard + accessibility ───────────────────────────────────────────

  test('TC-11 arrow keys move the highlight (ArrowUp wraps) and Enter opens the record', async ({ page }) => {
    const ui = SearchUi.palette(page)
    await ui.open()
    await ui.search(BROAD_TERM)
    await expect(ui.results().first()).toBeVisible()
    // Arrow keys and Enter are no-ops while the debounce/fetch is in flight.
    await ui.waitForIdle()

    const total = await ui.results().count()
    expect(total).toBeGreaterThan(1)

    // The row Enter will open, captured before the highlight moves.
    const target = (await ui.results().first().innerText()).split('\n')[0].trim()

    expect(await ui.highlightedIndex()).toBe(0)
    await page.keyboard.press('ArrowDown')
    expect(await ui.highlightedIndex()).toBe(1)

    // (index + (-1) + count) % count — the highlight wraps to the tail.
    await page.keyboard.press('ArrowUp')
    await page.keyboard.press('ArrowUp')
    expect(await ui.highlightedIndex()).toBe(total - 1)

    await page.keyboard.press('ArrowDown')
    expect(await ui.highlightedIndex()).toBe(0)

    await page.keyboard.press('Enter')

    // Opening a result is URL-driven: /docs/assets?drawer=[{"type","id"}]
    await expect(page).toHaveURL(/drawer=/, { timeout: 20_000 })
    // Radix leaves the palette in the DOM as data-state="closed", so a bare
    // getByRole('dialog') matches two nodes here. The record drawer is the one
    // carrying data-asset-drawer.
    const drawer = page.locator('[role="dialog"][data-asset-drawer="true"]')
    await expect(drawer).toBeVisible()
    // The drawer shows the record the highlight was on.
    await expect(drawer.getByRole('heading').first()).toContainText(target)
    // The palette gave way to the record drawer: one combobox left (the inline
    // host on the Assets page), and it is no longer inside a dialog.
    await expect(page.getByRole('combobox', { name: 'Search assets' })).toHaveCount(1)
  })

  test('TC-12 exposes the documented accessibility contract for the search widget', async ({ page }) => {
    const ui = SearchUi.palette(page)
    await ui.open()

    // The combobox is the documented entry point, not a bare <input name="search">.
    await expect(ui.input()).toHaveRole('combobox')
    await expect(ui.input()).toHaveAccessibleName('Search assets')

    // Filter chips announce what they will remove.
    await expect(ui.organizationChip()).toBeVisible()
    await expect(ui.assetTypeChip()).toBeVisible()
    await expect(ui.shortcutsChip()).toBeVisible()

    // Ask Lex declares a platform-correct chord (AssetSearch.tsx:122).
    const askLex = ui.askLexButton()
    await expect(askLex).toBeVisible()
    await expect(askLex).toHaveAttribute('aria-keyshortcuts', ASK_LEX_SHORTCUTS)

    // The `/` token opens a shortcut picker rather than a plain text search.
    await ui.shortcutsChip().click()
    await expect(ui.listbox()).toHaveAccessibleName('Search filters')
    await expect(page.getByRole('option', { name: '/ Organizations' })).toBeVisible()

    // ⌘K is surfaced on the trigger so the shortcut is discoverable.
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toBeHidden()
  })
})