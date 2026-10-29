/**
 * Inline image attachments on the organization record.
 *
 * Promoted from LEX-2328. The walk reached E2E Demo notes and the Attachments tab.
 * These three cases lock the journey: an embedded image cannot be deleted, removing
 * the image and saving restores delete, and cancelling a normal delete keeps the file.
 *
 * Surface : https://e2e-test.uat.lexful.net/docs/d/all/overview → E2E Demo
 * POM     : ./inline-attachments-pom.ts
 * Persona : admin (default session)
 */
import { test, expect } from '@playwright/test'
import { injectAuthCookies } from '../../auth-helper'
import { OrgAttachments, makePngFixture } from './inline-attachments-pom'

let created: string[] = []

test.beforeEach(async ({ page }) => {
  created = []
  await injectAuthCookies(page.context())
})

test.afterEach(async ({ page }) => {
  await new OrgAttachments(page).cleanup(created)
})

test.describe('Inline image attachments', () => {
  test('A saved inline image marks its attachment Embedded and disables Delete', {
    tag: ['@positive', '@smoke'],
  }, async ({ page }) => {
    const org = new OrgAttachments(page)
    const ordinary = makePngFixture('lex2328-ordinary')
    created.push(ordinary.name)

    await org.open()
    await org.openNoteEditor()
    await org.insertImageIntoNote(makePngFixture('lex2328-inline').file)
    await org.saveNote()

    const embedded = org.embeddedRow()
    await org.openTab('Attachments')
    await expect(embedded).toHaveCount(1)
    await expect(embedded.getByText('Embedded', { exact: true })).toBeVisible()
    await expect(org.deleteButton(embedded)).toBeDisabled()
    await expect(org.hintWrapper(embedded)).toHaveCount(1)
    created.push((await embedded.getByRole('button').nth(1).textContent()) ?? '')

    await org.uploadAttachment(ordinary.file, ordinary.name)
    const plainRow = org.attachmentRow(ordinary.name)
    await expect(plainRow.getByText('Embedded', { exact: true })).toHaveCount(0)
    await expect(org.deleteButton(plainRow)).toBeEnabled()
  })

  test('Removing the image and saving re-enables Delete, which then removes it', {
    tag: ['@positive', '@smoke'],
  }, async ({ page }) => {
    const org = new OrgAttachments(page)
    const fixture = makePngFixture('lex2328-unembed')

    await org.open()
    await org.openNoteEditor()
    await org.insertImageIntoNote(fixture.file)
    await org.saveNote()
    await org.openTab('Attachments')
    const embedded = org.embeddedRow()
    await expect(embedded).toHaveCount(1)
    const name = (await embedded.getByRole('button').nth(1).textContent()) ?? ''
    created.push(name)
    await expect(org.deleteButton(embedded)).toBeDisabled()

    await org.openNoteEditor()
    await org.removeEditorImages()
    await org.saveNote()

    await org.openTab('Attachments')
    const row = org.attachmentRow(name)
    await expect(row).toBeVisible()
    await expect(row.getByText('Embedded', { exact: true })).toHaveCount(0)
    await expect(org.deleteButton(row)).toBeEnabled()

    await org.deleteAttachment(name)
    await org.confirmDelete()
    await expect(row).toHaveCount(0)
    created = created.filter(n => n !== name)
  })

  test('Cancelling the confirmation keeps an ordinary attachment', {
    tag: ['@negative', '@smoke'],
  }, async ({ page }) => {
    const org = new OrgAttachments(page)
    const fixture = makePngFixture('lex2328-cancel')
    created.push(fixture.name)

    await org.open()
    await org.uploadAttachment(fixture.file, fixture.name)

    await org.deleteAttachment(fixture.name)
    await org.cancelDelete()

    const row = org.attachmentRow(fixture.name)
    await expect(row).toBeVisible()
    await expect(row.getByText('Embedded', { exact: true })).toHaveCount(0)
    await expect(org.deleteButton(row)).toBeEnabled()
  })
})
