import { expect, type Page } from '@playwright/test'
import { ensureSession, gotoApp } from './document-session'

const LIST_PATH = '/docs/d/all/system.document'

/** Documents grid at `/docs/d/all/system.document`. */
export class AssetRecordListPage {
  constructor(public page: Page, public assetType: string) {}

  async goto() {
    await ensureSession(this.page)
    await gotoApp(this.page, LIST_PATH)
    await expect(this.page.getByRole('heading', { name: 'Documents', level: 1 })).toBeVisible()
  }

  async recordTotal() {
    const summary = this.page.getByText(/\d[\d,]* documents/).first()
    await expect(summary).toBeVisible()
    const text = await summary.innerText()
    const match = text.match(/([\d,]+)\s+documents/)
    if (!match) throw new Error(`Document count was not on the page: ${text}`)
    return Number(match[1].replace(/,/g, ''))
  }

  async search(name: string) {
    const input = this.page.locator("input[placeholder='Search Documents...']")
    // The grid search is GET /v1/assets?search=…&asset_type=<type>[,…], not /v1/assets/<type>.
    const results = this.page.waitForResponse(response => {
      if (response.request().method() !== 'GET') return false
      const url = new URL(response.url())
      const types = (url.searchParams.get('asset_type') ?? '').split(',')
      return (
        url.pathname === '/v1/assets' &&
        url.searchParams.has('search') &&
        types.includes(this.assetType)
      )
    })
    await input.fill(name)
    await results
  }
}
