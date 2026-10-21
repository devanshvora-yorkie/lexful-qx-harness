import { expect, type Page, type Response } from '@playwright/test'
import { ensureSession, gotoApp, apiHeaders } from './document-session'

export const DOCUMENT_TYPE = 'system.document'

/** Local midnight, the same instant `serializeDateTime` sends. */
export function expectedExpiresOn(date: Date) {
  const midnight = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  return `${midnight.toISOString().slice(0, 19)}Z`
}

/** "October 15, 2026" — the expiry button's friendly label. */
export function friendlyDate(date: Date) {
  return date.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
}

/** Grid cell for a datetime expiry: local midnight rendered as `yyyy-MM-dd HH:mm`. */
export function gridExpiryText(date: Date) {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day} 00:00`
}

function dayButtonName(date: Date) {
  const weekday = date.toLocaleDateString('en-US', { weekday: 'long' })
  const month = date.toLocaleDateString('en-US', { month: 'long' })
  const n = date.getDate()
  const suffix =
    n % 10 === 1 && n % 100 !== 11 ? 'st'
    : n % 10 === 2 && n % 100 !== 12 ? 'nd'
    : n % 10 === 3 && n % 100 !== 13 ? 'rd'
    : 'th'
  return `${weekday}, ${month} ${n}${suffix}, ${date.getFullYear()}`
}

export class ApiContext {
  constructor(public page: Page) {}

  apiBase() {
    return process.env.STYTCH_API_URL || 'https://api.uat.lexful.net'
  }

  headers() {
    return apiHeaders()
  }
}

/** "New Documents" drawer. */
export class DocumentCreateDrawer {
  constructor(public page: Page) {}

  get dialog() {
    return this.page.getByRole('dialog').filter({
      has: this.page.getByRole('heading', { name: /New Documents/i }),
    })
  }

  get createButton() {
    return this.dialog.getByRole('button', { name: 'Create', exact: true })
  }

  get nameInput() {
    return this.dialog.getByRole('textbox', { name: 'Name' })
  }

  static async open(page: Page) {
    await ensureSession(page)
    const drawer = new DocumentCreateDrawer(page)
    if (!(await drawer.dialog.isVisible().catch(() => false))) {
      await page.getByRole('button', { name: 'New', exact: true }).click()
    }
    await expect(drawer.dialog).toBeVisible()
    return drawer
  }

  async typeName(name: string) {
    await this.nameInput.fill(name)
  }

  async selectOrganization(name: string) {
    await this.dialog.locator('button[role="combobox"]').first().click()
    await this.page.getByRole('option', { name: new RegExp(`^${name}`) }).click()
  }

  async typeBody(text: string) {
    const editor = this.dialog.locator('.tiptap[contenteditable="true"]')
    await editor.click()
    await this.page.keyboard.type(text)
  }

  async submit() {
    const response = this.page.waitForResponse(
      candidate =>
        candidate.request().method() === 'POST' &&
        candidate.url().includes(`/v1/assets/${DOCUMENT_TYPE}`),
    )
    await this.createButton.click()
    return response
  }
}

/** An open document record. */
export class DocumentRecordDrawer {
  constructor(public page: Page) {}

  get dialog() {
    return this.page.getByRole('dialog').filter({
      has: this.page.getByRole('button', { name: 'More actions' }),
    })
  }

  get title() {
    return this.dialog.getByRole('heading', { level: 2 })
  }

  get contentArticle() {
    return this.dialog.getByRole('article', { name: 'Document content' })
  }

  get editForm() {
    return this.dialog.getByRole('form', { name: 'Edit Content' })
  }

  get editor() {
    return this.editForm.locator('.tiptap[contenteditable="true"]')
  }

  get saveButton() {
    return this.dialog.getByRole('button', { name: 'Save changes' })
  }

  get discardButton() {
    return this.dialog.getByRole('button', { name: 'Discard', exact: true })
  }

  get cancelButton() {
    return this.dialog.getByRole('button', { name: 'Cancel', exact: true })
  }

  get expiryButton() {
    return this.dialog.getByRole('button', { name: 'Document expiry' })
  }

  static async openById(page: Page, id: string) {
    await ensureSession(page)
    await gotoApp(page, `/docs/d/all/${DOCUMENT_TYPE}/${id}`)
    const record = new DocumentRecordDrawer(page)
    await expect(record.dialog).toBeVisible()
    return record
  }

  async close() {
    await this.dialog.getByRole('button', { name: 'Close', exact: true }).click()
    await expect(this.dialog).toBeHidden()
  }

  async rename(name: string) {
    await this.dialog.getByRole('button', { name: 'Edit Name' }).click()
    const input = this.dialog.getByRole('form', { name: 'Edit Name' }).getByRole('textbox', { name: 'Name' })
    await input.fill(name)
    await input.press('Enter')
  }

  async expectChangeSummary(text: string) {
    await expect(this.dialog.getByRole('status').filter({ hasText: text })).toBeVisible()
  }

  async saveChanges(): Promise<Response> {
    const response = this.page.waitForResponse(
      candidate =>
        candidate.request().method() === 'PATCH' &&
        candidate.url().includes(`/v1/assets/${DOCUMENT_TYPE}/`),
    )
    await this.saveButton.click()
    return response
  }

  async startBodyEdit() {
    await this.dialog.getByRole('button', { name: 'Edit content', exact: true }).click()
    await expect(this.editForm).toBeVisible()
  }

  async typeBody(text: string) {
    await this.editor.click()
    await this.page.keyboard.press('ControlOrMeta+ArrowDown')
    await this.page.keyboard.type(text)
  }

  async applyFormat(name: string) {
    await this.dialog.locator(`[aria-label="Document formatting"] button[title="${name}"]`).click()
  }

  async underlineAvailable() {
    const markdown = this.dialog.locator('button[title="Underline (not supported in Markdown)"]')
    if (await markdown.count()) return false
    return this.dialog.locator('button[title="Underline"]').isEnabled()
  }

  async toggleContentType() {
    const toHtml = !(await this.underlineAvailable())
    await this.dialog.getByRole('button', { name: toHtml ? 'HTML' : 'Markdown', exact: true }).click()
    return toHtml ? 'html' : 'markdown'
  }

  async setExpiry(date: Date) {
    await this.expiryButton.click()
    const day = this.page.getByRole('button', { name: dayButtonName(date), exact: true })
    for (let step = 0; step < 14 && !(await day.isVisible().catch(() => false)); step++) {
      await this.page.getByRole('button', { name: 'Go to the Next Month' }).click()
    }
    await day.click()
  }

  async clearExpiry() {
    await this.expiryButton.click()
    await this.page.getByRole('button', { name: 'Clear', exact: true }).click()
  }

  async availableTags() {
    await this.dialog.getByRole('button', { name: 'Add tag' }).click()
    const tree = this.page.getByRole('tree', { name: 'Tags' })
    await expect(tree).toBeVisible()
    return tree.getByRole('checkbox').evaluateAll(nodes =>
      nodes
        .map(node => node.getAttribute('aria-label') ?? '')
        .filter(name => name && name !== 'Top level'),
    )
  }

  async toggleTag(name: string) {
    const tree = this.page.getByRole('tree', { name: 'Tags' })
    if (!(await tree.isVisible().catch(() => false))) {
      await this.dialog.getByRole('button', { name: 'Add tag' }).click()
    }
    await tree.getByRole('checkbox', { name, exact: true }).click()
    await this.page.keyboard.press('Escape')
  }

  async archive() {
    await this.dialog.getByRole('button', { name: 'More actions' }).click()
    await this.page.getByRole('menuitem', { name: 'Archive…' }).click()
    const confirm = this.page.getByRole('dialog').filter({
      has: this.page.getByRole('heading', { name: 'Archive 1 asset?' }),
    })
    const response = this.page.waitForResponse(
      candidate =>
        candidate.request().method() === 'DELETE' &&
        candidate.url().includes(`/v1/assets/${DOCUMENT_TYPE}/`),
    )
    await confirm.getByRole('button', { name: 'Archive asset' }).click()
    return response
  }
}
