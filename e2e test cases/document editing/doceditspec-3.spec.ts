/**
 * TC-DOC-014 … TC-DOC-015 — Lexful UAT **Document editing**, code block highlighting (smoke).
 *
 * Promoted from LEX-3800 (PowerShell and shared code-block highlighting, PR #2186).
 * Surface : https://e2e-test.uat.lexful.net/docs/d/all/system.document
 * API host: https://api.uat.lexful.net
 * POM     : ./code-block-pom.ts
 *
 * Run:
 *   node scripts/specs.mjs --headed "e2e test cases/document editing"
 */
import { test, expect } from '@playwright/test'
import { injectAuthCookies } from '../../auth-helper'
import { createViaApi, deleteCreated, openRecord, uniqueName } from './code-block-pom'

test.beforeEach(async ({ page }) => {
  await injectAuthCookies(page.context())
})

test.afterEach(async ({ page }) => {
  await deleteCreated(page)
})

test.beforeEach(() => {
  test.setTimeout(240_000)
})

test.describe('Document editing — code blocks — smoke', () => {
  test('A saved PowerShell block is highlighted and labelled in the read-only document', {
    tag: ['@positive', '@smoke'],
  }, async ({ page }) => {
    const id = await createViaApi(page, {
      name: uniqueName('read-only powershell'),
      content: '```powershell\nGet-ChildItem -Path C:\\ # list big files\n```\n',
    })
    const article = await openRecord(page, id)

    const block = article.locator('[class~="language-powershell"]').first()
    await expect(block).toBeVisible()
    await expect(article.getByText('powershell', { exact: true })).toBeVisible()
    await expect(block.locator('.hljs-built_in').first()).toHaveText('Get-ChildItem')
    const base = await block.evaluate((el) => getComputedStyle(el).color)
    const comment = await block
      .locator('.hljs-comment')
      .first()
      .evaluate((el) => getComputedStyle(el).color)
    expect(comment).not.toBe(base)
  })

  test('A block with no language stays plain in the read-only document', {
    tag: ['@edge', '@smoke'],
  }, async ({ page }) => {
    const id = await createViaApi(page, {
      name: uniqueName('plain block'),
      content: '```\nplain fence\n```\n',
    })
    const article = await openRecord(page, id)

    await expect(article.locator('pre').first()).toContainText('plain fence')
    await expect(article.locator('pre span[class*="hljs-"]')).toHaveCount(0)
  })
})
