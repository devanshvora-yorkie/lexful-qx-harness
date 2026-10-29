/**
 * Password records — page objects for the Passwords listing, the record drawer and the
 * New Passwords dialog on UAT.
 *
 * Promoted from LEX-3642 (run 2026-10-29_1121Z_63c8). Only the controls the promoted
 * tests use are here. Selectors come from the live UAT walk (explore/flow.md steps 3–18).
 *
 * Surface : https://e2e-test.uat.lexful.net/docs/d/all/system.password
 * API host: https://api.uat.lexful.net
 */
import { expect, type Page, type Request } from '@playwright/test'

export const APP_URL = 'https://e2e-test.uat.lexful.net'
export const API_URL = 'https://api.uat.lexful.net'
export const PASSWORDS_URL = `${APP_URL}/docs/d/all/system.password`

/** Seeded UAT data seen in the walk (explore/flow.md step 4). */
export const SEEDED_PASSWORD = 'AAA Aliquip Backup Console'
export const SEEDED_ORGANIZATION = 'Adipiscing Aliqua Academy'

export const UUID_PATTERN = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'

/** Retry a navigation that UAT answers with CloudFront 403 (custom-instructions). */
export async function gotoApp(page: Page, url: string) {
  let lastStatus = 0
  for (let attempt = 1; attempt <= 3; attempt++) {
    const response = await page.goto(url, { waitUntil: 'domcontentloaded' })
    lastStatus = response?.status() ?? 0
    const blocked =
      lastStatus === 403 || (await page.getByText('Request blocked').isVisible().catch(() => false))
    if (!blocked) return
  }
  throw new Error(`UAT blocked ${url} (HTTP ${lastStatus})`)
}

export class PasswordsListPage {
  constructor(private readonly page: Page) {}

  /**
   * Open the passwords listing and wait for the real listing response.
   * Returns the X-Account-ID the app sends.
   */
  async open(): Promise<string> {
    const accountRequest = this.page.waitForRequest(
      (request) => request.url().startsWith(API_URL) && Boolean(request.headers()['x-account-id']),
      { timeout: 20_000 },
    )
    const listing = this.page.waitForResponse(
      (response) =>
        response.url().startsWith(`${API_URL}/v1/assets/system.password?`) && response.status() === 200,
      { timeout: 20_000 },
    )
    await gotoApp(this.page, PASSWORDS_URL)
    await listing
    await this.row(SEEDED_PASSWORD).waitFor({ state: 'visible', timeout: 15_000 })
    const request: Request = await accountRequest
    return request.headers()['x-account-id']
  }

  /** The name cell of a password row (rows are grouped by organization). */
  row(name: string) {
    return this.page.getByText(name, { exact: true }).first()
  }

  /** Quick view opened by clicking the name cell. */
  quickView() {
    return this.page.getByRole('dialog', { name: 'Password quick view' })
  }

  /** Clicking "New" opens the create dialog. */
  newButton() {
    return this.page.getByRole('button', { name: 'New', exact: true })
  }

  async openQuickView(name: string) {
    await this.row(name).click()
    await expect(this.quickView()).toBeVisible()
  }

  /** "Open password" in the quick view opens the full record drawer. */
  async openRecordFromQuickView() {
    const revisions = this.page.waitForResponse(
      (response) =>
        new RegExp(`/v1/assets/system\\.password/${UUID_PATTERN}/revisions\\?`).test(response.url()) &&
        response.status() === 200,
      { timeout: 20_000 },
    )
    await this.quickView().getByRole('button', { name: 'Open password', exact: true }).click()
    await revisions
  }
}

export class PasswordRecordDrawer {
  constructor(private readonly page: Page) {}

  /** The record drawer is the active dialog that holds the Record sections tablist. */
  root() {
    return this.page.getByRole('dialog').filter({ has: this.page.getByRole('tablist', { name: 'Record sections' }) })
  }

  /** Tab names can carry a count ("Details 8"), so do not match exactly. */
  tab(name: 'Overview' | 'Details') {
    return this.root().getByRole('tab', { name })
  }

  overviewPanel() {
    return this.root().getByRole('tabpanel', { name: 'Overview' })
  }

  detailsPanel() {
    return this.root().getByRole('tabpanel', { name: 'Details' })
  }
}

export class NewPasswordDialog {
  constructor(private readonly page: Page) {}

  root() {
    return this.page.getByRole('dialog').filter({ has: this.page.getByRole('heading', { name: 'New Passwords' }) })
  }

  createButton() {
    return this.root().getByRole('button', { name: 'Create', exact: true })
  }
}
