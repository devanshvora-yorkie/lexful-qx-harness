import { expect, type Page } from '@playwright/test'
import { injectAuthCookies } from '../../auth-helper'

/**
 * Page objects and fixtures for LEX-3518 (PR #1909): Lex Replace and Translate inside
 * the document editor must not submit the enclosing document form.
 * Promoted from the LEX-3518 run (runs/tickets/LEX-3518/2026-10-30_1014Z_75f0).
 *
 * Surface : https://e2e-test.uat.lexful.net/docs/d/all/system.document
 * API     : https://api.uat.lexful.net  (POST / PATCH / DELETE /v1/assets/system.document)
 */

export const APP_URL = 'https://e2e-test.uat.lexful.net'
export const API_URL = 'https://api.uat.lexful.net'
export const DOCUMENT_TYPE = 'system.document'
/** "E2E Demo" organization id used by the checked-in document fixtures. */
export const DOCUMENT_ORGANIZATION_ID = '01a0ee54-00c2-7054-ae8b-a4cb9e1b7d8b'
export const ORIGINAL_BODY = 'Original paragraph for the LEX-3518 walk.'

let accountId = ''
const createdIds: string[] = []

export function uniqueName(label: string) {
  return `${label} ${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

/**
 * Learn X-Account-Id from the app's own traffic (the API needs it), with the admin cookies.
 * CloudFront answers 403 intermittently, so retry the navigation up to three times.
 */
export async function ensureAccount(page: Page) {
  await injectAuthCookies(page.context())
  if (accountId) return
  const seen = page.waitForRequest(request => Boolean(request.headers()['x-account-id']), {
    timeout: 30_000,
  })
  for (let attempt = 1; attempt <= 3; attempt++) {
    const response = await page.goto(`${APP_URL}/docs/d/all/${DOCUMENT_TYPE}`, { waitUntil: 'domcontentloaded' })
    if (response?.status() !== 403) break
  }
  accountId = (await seen).headers()['x-account-id']
}

/** Create a document through the API. Archived again in afterEach. */
export async function createDocument(page: Page, name: string, body: string) {
  await ensureAccount(page)
  const response = await page.request.post(`${API_URL}/v1/assets/${DOCUMENT_TYPE}`, {
    headers: { 'Content-Type': 'application/json', 'X-Account-Id': accountId },
    data: { name, content: body, organization_id: DOCUMENT_ORGANIZATION_ID, visibility: 'inherit' },
  })
  expect(response.status(), 'create fixture document').toBe(201)
  const payload = (await response.json()) as { id: string }
  createdIds.push(payload.id)
  return payload.id
}

/** Archive every document this worker created. A 404 means it is already gone. */
export async function archiveCreatedDocuments(page: Page) {
  const failures: string[] = []
  while (createdIds.length) {
    const id = createdIds.pop()
    if (!id) break
    const response = await page.request.delete(`${API_URL}/v1/assets/${DOCUMENT_TYPE}/${id}`, {
      headers: { 'X-Account-Id': accountId },
    })
    if (response.status() !== 204 && response.status() !== 404) {
      failures.push(`${id} HTTP ${response.status()}`)
    }
  }
  if (failures.length) throw new Error(`Could not archive fixture documents: ${failures.join('; ')}`)
}

/** An open document record drawer, with its body editor and the Lex menu. */
export class DocumentRecord {
  constructor(public page: Page) {}

  get dialog() {
    return this.page.getByRole('dialog').filter({
      has: this.page.getByRole('button', { name: 'More actions' }),
    })
  }

  get editContentButton() {
    return this.dialog.getByRole('button', { name: 'Edit content', exact: true })
  }

  get editForm() {
    return this.page.getByRole('form', { name: 'Edit Content' })
  }

  get editor() {
    return this.editForm.locator('.tiptap[contenteditable="true"]')
  }

  /** Drawer header "Lex" button (description "Lex Actions"). */
  get lexMenu() {
    return this.page.getByRole('button', { name: 'Lex', description: 'Lex Actions' })
  }

  get saveButton() {
    return this.dialog.getByRole('button', { name: 'Save changes' })
  }

  /** The Lex instruction box, inside the Edit Content form. */
  get instruction() {
    return this.editForm.getByRole('textbox', { name: /Tell Lex what to do|Target language/ })
  }


  get panelCancel() {
    return this.editForm.getByRole('button', { name: 'Cancel', exact: true })
  }



  async open(id: string) {
    await ensureAccount(this.page)
    const url = `${APP_URL}/docs/d/all/${DOCUMENT_TYPE}?drawer=${encodeURIComponent(
      JSON.stringify([{ type: DOCUMENT_TYPE, id }]),
    )}`
    for (let attempt = 1; attempt <= 3; attempt++) {
      const response = await this.page.goto(url, { waitUntil: 'domcontentloaded' })
      if (response?.status() !== 403) break
    }
    await expect(this.dialog).toBeVisible({ timeout: 30_000 })
    await expect(this.editContentButton).toBeVisible({ timeout: 30_000 })
  }

  async startEdit() {
    await this.editContentButton.click()
    await expect(this.editForm).toBeVisible()
  }

  async selectBody() {
    await this.editor.getByText('Original paragraph').click()
    await this.page.keyboard.press('ControlOrMeta+a')
  }

  async runLex(action: 'Replace' | 'Translate') {
    await this.lexMenu.click()
    await this.page.getByRole('menuitem', { name: new RegExp(`^${action}`) }).click()
  }
}
