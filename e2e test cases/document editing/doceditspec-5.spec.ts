/**
 * LEX-3518 — Lexful UAT **Document editing**, Lex panel guard (regression).
 *
 * Promoted from runs/tickets/LEX-3518/2026-10-30_1014Z_75f0 (PR #1909).
 * TC-DOC-016 — Cancel in the Lex instruction box returns to the editor with the body unchanged
 *
 * Surface : https://e2e-test.uat.lexful.net/docs/d/all/system.document
 * API host: https://api.uat.lexful.net
 * POM     : ./lex-actions-pom.ts
 *
 * Run:
 *   node scripts/specs.mjs --headed "e2e test cases/document editing"
 */
import { test, expect } from '@playwright/test'
import { injectAuthCookies } from '../../auth-helper'
import {
  ORIGINAL_BODY,
  archiveCreatedDocuments,
  createDocument,
  uniqueName,
  DocumentRecord,
} from './lex-actions-pom'

test.beforeEach(async ({ page }) => {
  await injectAuthCookies(page.context())
})

test.afterEach(async ({ page }) => {
  await archiveCreatedDocuments(page)
})

test.beforeEach(() => {
  test.setTimeout(240_000)
})

test.describe('Document editing — Lex actions — regression', () => {
  test('Cancel in the Lex instruction box returns to the editor with the body unchanged', {
    tag: ['@edge', '@regression'],
  }, async ({ page }) => {
    const id = await createDocument(page, uniqueName('LEX3518 Cancel'), ORIGINAL_BODY)
    const record = new DocumentRecord(page)
    await record.open(id)
    await record.startEdit()
    await record.selectBody()
    await record.runLex('Replace')
    await expect(record.instruction).toBeVisible()

    await record.panelCancel.click()

    await expect(record.instruction).toHaveCount(0)
    await expect(record.editForm).toBeVisible()
    expect(page.url()).toContain('drawer=')
    await expect(record.editor).toContainText(ORIGINAL_BODY)
    await expect(record.saveButton).toBeDisabled()
  })
})
