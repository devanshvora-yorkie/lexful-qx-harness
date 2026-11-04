import { expect, type Page, type Request } from '@playwright/test'
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

/**
 * Cooldown between CloudFront WAF retries. The blocks come in bursts while the suite runs in parallel,
 * and 45 s was not enough for them to clear in attempt 1, so the spacing is 60 s and 4 tries.
 */
export const WAF_COOLDOWN_MS = 60_000
export const WAF_ATTEMPTS = 4

/**
 * True when CloudFront blocked the page: the status is 403, or the 403 page appears after the
 * navigation returned (the app can send the browser to that page after its first load).
 */
export async function isWafBlocked(page: Page, status: number): Promise<boolean> {
  if (status === 403) return true
  return page
    .getByText('Request blocked')
    .first()
    .waitFor({ state: 'visible', timeout: 3_000 })
    .then(() => true, () => false)
}

/** CloudFront intermittently answers 403. Retry the navigation, spacing the attempts out. */
export async function gotoApp(page: Page, url: string) {
  let lastStatus = 0
  for (let attempt = 1; attempt <= WAF_ATTEMPTS; attempt++) {
    const response = await page.goto(url, { waitUntil: 'domcontentloaded' })
    lastStatus = response?.status() ?? 0
    if (!(await isWafBlocked(page, lastStatus))) return
    if (attempt < WAF_ATTEMPTS) await new Promise(resolve => setTimeout(resolve, WAF_COOLDOWN_MS))
  }
  throw new Error(`UAT blocked ${url} (HTTP ${lastStatus})`)
}

/** Load the documents list when a later API call needs the account id first. */
export async function primeAccount(page: Page) {
  await ensureSession(page)
  if (accountId) return
  // Listen rather than wait on one request: the blocked attempts send none, and the wait spans the retries.
  let captured = ''
  const onRequest = (request: Request) => {
    const id = request.headers()['x-account-id']
    if (id && !captured) captured = id
  }
  page.on('request', onRequest)
  try {
    await gotoApp(page, '/docs/d/all/system.document')
    await expect.poll(() => captured, { timeout: 60_000 }).not.toBe('')
    accountId = captured
  } finally {
    page.off('request', onRequest)
  }
}
