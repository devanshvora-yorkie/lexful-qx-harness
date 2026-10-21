/**
 * TC-DOC-011 … TC-DOC-013 — Lexful UAT **Document editing**, edge coverage.
 *
 * Surface : https://e2e-test.uat.lexful.net/docs/d/all/system.document
 * API host: https://api.uat.lexful.net
 * POM     : playwright-tests/pages/docs/document.page.ts
 *
 * Companion to `tests/document-editing-e2e/doceditspec.ts` (which holds TC-DOC-001 … TC-DOC-010). The
 * harness caps a spec file at 10 tests, so the edge cases live here.
 *
 * These three cover the "escape hatches" of the editing surface — the paths where a
 * user backs out of a change and the record must be left exactly as it was:
 *
 *   TC-DOC-011  Discard a staged rename        → nothing is persisted
 *   TC-DOC-012  Cancel the body editor         → nothing is persisted
 *   TC-DOC-013  Clear an expiry date           → only the expiry is removed
 *
 * Run:
 *   cd playwright-tests && npx playwright test tests/document-editing-e2e/doceditspec-2.spec.ts --project=chromium
 */
import { test, expect } from '@playwright/test'
import { ApiContext, DocumentRecordDrawer, DOCUMENT_TYPE } from '../../pages/docs/document.page'
import {
  cleanupCreatedRecords,
  createDocument,
  TEST_ORGANIZATION,
  uniqueName,
} from '../../support/document-fixtures'

test.afterEach(async ({ page }) => {
  await cleanupCreatedRecords(page)
})

// =======================================================================================
// Edge
// =======================================================================================

test.describe('Document editing — edge', () => {
  test('TC-DOC-011: Discard a staged rename leaves the record name unchanged', async ({ page }) => {
    const api = new ApiContext(page)
    const original = uniqueName('Onboarding Checklist')
    const id = await createDocument(page, api, { name: original, body: 'Steps for the vendor to follow.' })

    const patches: string[] = []
    page.on('request', request => {
      if (
        request.method() === 'PATCH' &&
        request.url().includes(`/v1/assets/${DOCUMENT_TYPE}/`)
      ) {
        patches.push(request.url())
      }
    })

    const record = await DocumentRecordDrawer.openById(page, id)
    await record.rename(uniqueName('Onboarding Checklist Revised'))
    await record.expectChangeSummary('1 change')
    await expect(record.saveButton).toBeEnabled()
    await expect(record.discardButton).toBeVisible()

    await record.discardButton.click()

    // The staged change is dropped: the title is back to the persisted name and the
    // save bar disappears, so nothing was written.
    await expect(record.title).toHaveText(original)
    await expect(record.saveButton).toBeHidden()
    expect(patches).toHaveLength(0)

    // A reload proves the server never saw the new name.
    await record.close()
    const reopened = await DocumentRecordDrawer.openById(page, id)
    await expect(reopened.title).toHaveText(original)
  })

  test('TC-DOC-012: Cancel the body editor keeps the stored content', async ({ page }) => {
    const api = new ApiContext(page)
    const name = uniqueName('Escalation Matrix')
    const body = 'Page the on-call engineer for sev-1 incidents.'
    const id = await createDocument(page, api, { name, body })

    const patches: string[] = []
    page.on('request', request => {
      if (
        request.method() === 'PATCH' &&
        request.url().includes(`/v1/assets/${DOCUMENT_TYPE}/`)
      ) {
        patches.push(request.url())
      }
    })

    const record = await DocumentRecordDrawer.openById(page, id)
    await record.startBodyEdit()
    await record.typeBody(' This sentence must never be stored.')
    await record.expectChangeSummary('1 change')
    await expect(record.cancelButton).toBeVisible()

    await record.cancelButton.click()

    // The editor closes and the read view shows the original text.
    await expect(record.editForm).toBeHidden()
    await expect(record.contentArticle).toContainText(body)
    await expect(record.contentArticle).not.toContainText('This sentence must never be stored.')
    expect(patches).toHaveLength(0)
  })

  test('TC-DOC-013: Clear an expiry date removes only the expiry', async ({ page }) => {
    const api = new ApiContext(page)
    const name = uniqueName('Temporary Vendor Credential')
    const body = 'Valid for the duration of the migration window.'
    const id = await createDocument(page, api, { name, body })

    const now = new Date()
    const target = new Date(now.getFullYear(), now.getMonth() + 1, 15)

    const record = await DocumentRecordDrawer.openById(page, id)
    await record.setExpiry(target)
    await record.expectChangeSummary('1 change')
    await record.saveChanges()
    await expect(record.expiryButton).toContainText('Expires')

    // Clear it again — the record keeps its name and body.
    await record.clearExpiry()
    await record.expectChangeSummary('1 change')
    const response = await record.saveChanges()
    const payload = (await response.json()) as { name: string; content: string; expires_on: string | null }
    expect(payload.expires_on).toBeNull()
    expect(payload.name).toBe(name)
    expect(payload.content).toContain('Valid for the duration of the migration window.')

    await expect(record.expiryButton).toContainText('Set expiry')
  })
})
