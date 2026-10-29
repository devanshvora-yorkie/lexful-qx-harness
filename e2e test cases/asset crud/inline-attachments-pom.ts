/**
 * LEX-2328 — POM for inline (embedded) image attachments.
 *
 * Surfaces (UAT, persona admin):
 *   - Organization "E2E Demo" → Overview → note editor (Insert Image / Save changes / Cancel)
 *   - Organization "E2E Demo" → Attachments tab (Embedded badge, Delete attachment, confirm dialog)
 *   - Asset "E2E-Act-*" (Servers) → Attachments tab (ordinary upload and delete)
 *
 * The E2E Demo note is empty at baseline. cleanup() empties it again and removes the attachments a test created.
 */
import { expect, type Locator, type Page } from '@playwright/test'
import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'

export const BASE_URL = 'https://e2e-test.uat.lexful.net'
export const ORG_NAME = 'E2E Demo'
export const ORG_LIST_URL = `${BASE_URL}/docs/d/all/overview`
export const SERVERS_URL = `${BASE_URL}/docs/d/e2e-demo/servers`
export const EMBEDDED_HINT = 'Remove this image from the document and save before deleting it.'

// 1×1 PNG. Uploaded as a real file so the attachment pipeline (create → complete → S3 PUT) runs.
const PNG_BASE64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='

export interface PngFixture {
  /** Attachment name the server stores (file stem). */
  name: string
  /** Absolute path of the file on disk. */
  file: string
}

/** Writes a uniquely named PNG so repeated runs never collide on attachment name. */
export function makePngFixture(stem: string): PngFixture {
  const name = `${stem}-${Date.now()}`
  const file = path.join(os.tmpdir(), `${name}.png`)
  fs.writeFileSync(file, Buffer.from(PNG_BASE64, 'base64'))
  return { name, file }
}

export class OrgAttachments {
  constructor(private readonly page: Page) {}

  // ---------- navigation ----------

  /** Opens the organization list, then the E2E Demo drawer on the Overview tab. */
  async open(): Promise<void> {
    const listLoaded = this.page.waitForResponse(
      r => r.request().method() === 'GET' && r.url().includes('/v1/organizations') && r.ok(),
      { timeout: 20_000 },
    )
    await this.page.goto(ORG_LIST_URL, { waitUntil: 'domcontentloaded' })
    await listLoaded
    await expect(this.page.getByText(ORG_NAME, { exact: true }).first()).toBeVisible()
    await this.page.getByText(ORG_NAME, { exact: true }).first().click()
    await expect(this.page.getByRole('heading', { name: ORG_NAME, level: 2 })).toBeVisible()
  }

  async openTab(name: 'Overview' | 'Attachments' | 'History'): Promise<void> {
    await this.page.getByRole('tab', { name, exact: true }).click()
  }

  // ---------- note editor ----------

  async openNoteEditor(): Promise<void> {
    await this.openTab('Overview')
    await this.page.getByRole('button', { name: 'Edit Notes', exact: true }).click()
    await expect(this.page.getByRole('button', { name: 'Insert Image', exact: true })).toBeVisible()
  }

  /** Inserts an image into the open note draft. The editor uploads it as an attachment. */
  async insertImageIntoNote(file: string): Promise<void> {
    const chooser = this.page.waitForEvent('filechooser')
    const uploaded = this.page.waitForResponse(
      r => r.request().method() === 'POST' && r.url().endsWith('/complete') && r.ok(),
    )
    await this.page.getByRole('button', { name: 'Insert Image', exact: true }).click()
    const fileChooser = await chooser
    await fileChooser.setFiles(file)
    await uploaded
    await expect(this.editorImages()).toHaveCount(1)
  }

  editorImages(): Locator {
    return this.page.locator('[contenteditable="true"] img')
  }

  /** Selects every inline image node in the draft and deletes it. Nothing is saved here. */
  async removeEditorImages(): Promise<void> {
    const nodes = this.page.locator('[contenteditable="true"] [data-node="image"]')
    const count = await nodes.count()
    for (let i = 0; i < count; i++) {
      await nodes.first().click()
      await this.page.keyboard.press('Delete')
    }
    await expect(this.editorImages()).toHaveCount(0)
  }

  async saveNote(): Promise<void> {
    const saved = this.page.waitForResponse(
      r => ['PATCH', 'PUT', 'POST'].includes(r.request().method()) && r.url().includes('/v1/organizations/') && r.ok(),
    )
    await this.page.getByRole('button', { name: 'Save changes', exact: true }).click()
    await saved
    await expect(this.page.getByRole('button', { name: 'Edit Notes', exact: true })).toBeVisible()
  }

  /** Footer Cancel on the note form. It drops the unsaved draft without a prompt. */
  async cancelNote(): Promise<void> {
    await this.page.getByRole('button', { name: 'Cancel', exact: true }).click()
    await expect(this.page.getByRole('button', { name: 'Edit Notes', exact: true })).toBeVisible()
  }

  // ---------- attachments tab ----------

  async uploadAttachment(file: string, name: string): Promise<void> {
    await this.openTab('Attachments')
    const uploaded = this.page.waitForResponse(
      r => r.request().method() === 'POST' && r.url().endsWith('/complete') && r.ok(),
    )
    await this.page
      .getByRole('tabpanel', { name: 'Attachments' })
      .locator('input[type="file"]')
      .setInputFiles(file)
    await uploaded
    await expect(this.attachmentRow(name)).toBeVisible()
  }

  /** The list item whose name button matches exactly. */
  attachmentRow(name: string): Locator {
    return this.page
      .getByRole('listitem')
      .filter({ has: this.page.getByRole('button', { name, exact: true }) })
  }

  /** The list item carrying the Embedded badge. Only one is expected per fixture. */
  embeddedRow(): Locator {
    return this.page
      .getByRole('listitem')
      .filter({ has: this.page.getByText('Embedded', { exact: true }) })
  }

  deleteButton(row: Locator): Locator {
    return row.getByRole('button', { name: 'Delete attachment', exact: true })
  }

  /** Span that wraps the disabled Delete button. It takes focus and carries the hint as its aria-label. */
  hintWrapper(row: Locator): Locator {
    return row.locator(`span[aria-label="${EMBEDDED_HINT}"]`)
  }

  async deleteAttachment(name: string): Promise<void> {
    const row = this.attachmentRow(name)
    await expect(row).toBeVisible()
    await this.deleteButton(row).click()
    await expect(this.page.getByRole('heading', { name: 'Delete attachment?' })).toBeVisible()
  }

  async confirmDelete(): Promise<void> {
    const deleted = this.page.waitForResponse(
      r => r.request().method() === 'DELETE' && r.url().includes('/files/') && r.ok(),
    )
    await this.page
      .getByRole('dialog')
      .filter({ hasText: 'Delete attachment?' })
      .getByRole('button', { name: 'Delete', exact: true })
      .click()
    await deleted
  }

  async cancelDelete(): Promise<void> {
    await this.page
      .getByRole('dialog')
      .filter({ hasText: 'Delete attachment?' })
      .getByRole('button', { name: 'Cancel', exact: true })
      .click()
    await expect(this.page.getByRole('heading', { name: 'Delete attachment?' })).toHaveCount(0)
  }

  /**
   * Best-effort reset after a test. Empties the note, then deletes the named attachments
   * that are still present. Safe to call when nothing was created.
   */
  async cleanup(names: string[]): Promise<void> {
    await this.open()
    await this.openNoteEditor()
    if ((await this.editorImages().count()) > 0) {
      await this.removeEditorImages()
      await this.saveNote()
    } else {
      await this.cancelNote()
    }
    await this.openTab('Attachments')
    for (const name of names) {
      const row = this.attachmentRow(name)
      if ((await row.count()) === 0) continue
      await expect(this.deleteButton(row)).toBeEnabled()
      await this.deleteAttachment(name)
      await this.confirmDelete()
      await expect(row).toHaveCount(0)
    }
  }
}

export class ServerAttachments {
  constructor(private readonly page: Page) {}

  /** Opens the first E2E-Act server in the E2E Demo listing on the Attachments tab. */
  async openFirstServerAttachments(): Promise<void> {
    const listLoaded = this.page.waitForResponse(
      r => r.request().method() === 'GET' && r.url().includes('/v1/assets/servers') && r.ok(),
    )
    await this.page.goto(SERVERS_URL, { waitUntil: 'domcontentloaded' })
    await listLoaded
    const row = this.page.getByRole('row').filter({ hasText: 'E2E-Act-' }).first()
    await expect(row).toBeVisible()
    await row.getByText(/^E2E-Act-/).first().click()
    await expect(this.page.getByRole('tablist', { name: 'Record sections' })).toBeVisible()
    await this.page.getByRole('tab', { name: 'Attachments', exact: true }).click()
  }

  async upload(file: string, name: string): Promise<void> {
    const uploaded = this.page.waitForResponse(
      r => r.request().method() === 'POST' && r.url().endsWith('/complete') && r.ok(),
    )
    await this.page
      .getByRole('tabpanel', { name: 'Attachments' })
      .locator('input[type="file"]')
      .setInputFiles(file)
    await uploaded
    await expect(this.attachmentRow(name)).toBeVisible()
  }

  attachmentRow(name: string): Locator {
    return this.page
      .getByRole('listitem')
      .filter({ has: this.page.getByRole('button', { name, exact: true }) })
  }

  async deleteAndConfirm(name: string): Promise<void> {
    const row = this.attachmentRow(name)
    await row.getByRole('button', { name: 'Delete attachment', exact: true }).click()
    await expect(this.page.getByRole('heading', { name: 'Delete attachment?' })).toBeVisible()
    const deleted = this.page.waitForResponse(
      r => r.request().method() === 'DELETE' && r.url().includes('/files/') && r.ok(),
    )
    await this.page
      .getByRole('dialog')
      .filter({ hasText: 'Delete attachment?' })
      .getByRole('button', { name: 'Delete', exact: true })
      .click()
    await deleted
    await expect(row).toHaveCount(0)
  }

  /** Best-effort: removes the named file if it is still on the server. */
  async cleanup(name: string): Promise<void> {
    await this.openFirstServerAttachments()
    if ((await this.attachmentRow(name).count()) > 0) {
      await this.deleteAndConfirm(name)
    }
  }
}
