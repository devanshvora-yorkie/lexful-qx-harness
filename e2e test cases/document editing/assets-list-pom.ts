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
    const results = this.page.waitForResponse(
      response =>
        response.request().method() === 'GET' &&
        response.url().includes(`/v1/assets/${this.assetType}`) &&
        response.url().includes('search='),
    )
    await input.fill(name)
    await results
  }
}
