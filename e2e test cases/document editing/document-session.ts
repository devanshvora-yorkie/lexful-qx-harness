import type { Page } from '@playwright/test'
import { injectAuthCookies } from '../../auth-helper'

const LISTENING = new WeakSet<Page>()
let accountId = ''

/** Remember `X-Account-Id` from the app's own API calls and reuse the Stytch cookies. */
export async function ensureSession(page: Page) {
  if (!LISTENING.has(page)) {
    LISTENING.add(page)
    page.on('request', request => {
      const id = request.headers()['x-account-id']
      if (id) accountId = id
    })
  }
  await injectAuthCookies(page.context())
}

export function apiHeaders() {
  if (!accountId) throw new Error('No X-Account-Id yet. Open the app before calling the API.')
  return {
    'Content-Type': 'application/json',
    'X-Account-Id': accountId,
  }
}

export function accountHeader() {
  if (!accountId) throw new Error('No X-Account-Id yet. Open the app before calling the API.')
  return accountId
}

/** CloudFront intermittently answers 403. Retry the navigation. */
export async function gotoApp(page: Page, url: string) {
  let lastStatus = 0
  for (let attempt = 1; attempt <= 3; attempt++) {
    const response = await page.goto(url, { waitUntil: 'domcontentloaded' })
    lastStatus = response?.status() ?? 0
    const blocked =
      lastStatus === 403 ||
      (await page.getByText('Request blocked').isVisible().catch(() => false))
    if (!blocked) return
  }
  throw new Error(`UAT blocked ${url} (HTTP ${lastStatus})`)
}

/** Load the documents list when a later API call needs the account id first. */
export async function primeAccount(page: Page) {
  await ensureSession(page)
  if (accountId) return
  const seen = page.waitForRequest(request => Boolean(request.headers()['x-account-id']), {
    timeout: 20_000,
  })
  await gotoApp(page, '/docs/d/all/system.document')
  await seen
}
