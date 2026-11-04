import { expect, type Locator, type Page } from '@playwright/test'
import { gotoApp } from './document-session'

/**
 * Code block page object for Document editing (promoted from LEX-3800).
 * Locators and waits were seen in the live walk. Records are created through the API
 * and archived in afterEach by the spec that created them.
 */
export const APP_URL = 'https://e2e-test.uat.lexful.net'
export const LIST_URL = `${APP_URL}/docs/d/all/system.document`
export const API_URL = 'https://api.uat.lexful.net'
export const DOCUMENT_TYPE = 'system.document'
export const ORG_ID = '01a0ee54-00c2-7054-ae8b-a4cb9e1b7d8b'
export const ORG_NAME = 'E2E Demo'

/** Light palette comment colour from code-highlight.css (#6a737d). */
export const LIGHT_COMMENT_RGB = 'rgb(106, 115, 125)'

export const createdIds: string[] = []

export function uniqueName(label: string) {
  return `LEX-3800 ${label} ${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

export async function openList(page: Page) {
  await page.goto(LIST_URL)
  await expect(page.getByRole('heading', { name: 'Documents', level: 1 })).toBeVisible()
}

/** Create a document through the API. Status is asserted here; the id is kept for cleanup. */
export async function createViaApi(page: Page, fields: { name: string; content: string }) {
  const response = await page.request.post(`${API_URL}/v1/assets/${DOCUMENT_TYPE}`, {
    headers: { 'X-Account-Id': ORG_ID, 'Content-Type': 'application/json' },
    data: { name: fields.name, content: fields.content, organization_id: ORG_ID, visibility: 'inherit' },
    // UAT answered in 8-9 s on a slow run; the default request timeout is 8 s.
    timeout: 30_000,
  })
  expect(response.status()).toBe(201)
  const payload = (await response.json()) as { id: string }
  createdIds.push(payload.id)
  return payload.id
}

/** Archive every document this file created. 204 or 404 is fine. */
export async function deleteCreated(page: Page) {
  while (createdIds.length) {
    const id = createdIds.pop()
    if (!id) break
    const response = await page.request.delete(`${API_URL}/v1/assets/${DOCUMENT_TYPE}/${id}`, {
      headers: { 'X-Account-Id': ORG_ID },
    })
    expect([204, 404]).toContain(response.status())
  }
}

/** Record drawer for a saved document. */
export function recordDrawer(page: Page): Locator {
  return page.getByRole('dialog').filter({ has: page.getByRole('button', { name: 'More actions' }) })
}

export function recordArticle(page: Page): Locator {
  return recordDrawer(page).getByRole('article', { name: 'Document content' })
}

export async function openRecord(page: Page, id: string) {
  const drawer = JSON.stringify([{ type: DOCUMENT_TYPE, id }])
  await gotoApp(page, `${LIST_URL}?drawer=${encodeURIComponent(drawer)}`)
  const article = recordArticle(page)
  await expect(article).toBeVisible()
  return article
}
