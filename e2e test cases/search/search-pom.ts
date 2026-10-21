import { expect, type Locator, type Page, type Response } from '@playwright/test'

const ASSETS_PATH = '/docs/assets'

/** ⌘K on macOS, Ctrl+K everywhere else. */
export const PALETTE_SHORTCUT = process.platform === 'darwin' ? 'Meta+k' : 'Control+k'
export const ASK_LEX_SHORTCUTS = process.platform === 'darwin' ? 'Meta+Enter' : 'Control+Enter'

// ── Network guards ───────────────────────────────────────────────────────────

/** Every data-changing search action waits on this instead of a fixed sleep. */
export function keywordSearch(page: Page, extra?: (url: string) => boolean): Promise<Response> {
  return page.waitForResponse(
    r =>
      r.request().method() === 'GET' &&
      new URL(r.url()).pathname === '/v1/search' &&
      (extra ? extra(r.url()) : true),
    { timeout: 20_000 },
  )
}

/** Live-recording request spy, used by the debounce test. */
export function trackSearchRequests(page: Page): string[] {
  const urls: string[] = []
  page.on('response', r => {
    if (new URL(r.url()).pathname === '/v1/search') urls.push(r.url())
  })
  return urls
}

/** Shape of GET /v1/search — see services/docu-service/src/api/routes/search.ts */
export interface SearchResponse {
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
export async function gotoAssets(page: Page): Promise<void> {
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
export class SearchUi {
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

