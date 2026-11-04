/**
 * LEX-3554 — Move dialog gating (Smoke).
 *
 * Promoted from runs/tickets/LEX-3554/2026-10-29_0929Z_45ca (TC-LEX-3554-002).
 * Surface : Passwords list → Ctrl-K palette → Password quick view → Open password → More actions → Move…
 * POM     : ./move-records-pom.ts
 * Persona : admin (default session)
 */
import { test, expect } from '@playwright/test'
import { injectAuthCookies } from '../../auth-helper'
import {
  ORG_ADIPISCING_FOUNDATION,
  PASSWORDS_URL,
  MovePage,
  getAsset,
  moveAssetBack,
  openRecordFromPalette,
  pickEligibleAsset,
  gotoApp,
} from './move-records-pom'

// The record this test may have moved. afterEach puts it back in its original organization.
let touched: { assetType: string; id: string; organizationId: string } | null = null

test.beforeEach(async ({ page }) => {
  touched = null
  await injectAuthCookies(page.context())
})

test.afterEach(async ({ page }) => {
  if (!touched) return
  const current = await getAsset(page, touched.assetType, touched.id)
  if (current.organization_id !== touched.organizationId) {
    await moveAssetBack(page, touched.assetType, touched.id, touched.organizationId)
  }
  touched = null
})

test.beforeEach(() => {
  test.setTimeout(240_000)
})

test.describe('LEX-3554 move records — smoke', () => {
  test('Move password stays disabled until a destination is chosen and excludes the current organization', {
    tag: ['@edge', '@smoke'],
  }, async ({ page }) => {
    const asset = await pickEligibleAsset(page, 'system.password', ORG_ADIPISCING_FOUNDATION)
    touched = { assetType: 'system.password', id: asset.id, organizationId: asset.organization_id }
    const move = new MovePage(page)

    await gotoApp(page, PASSWORDS_URL)
    await openRecordFromPalette(page, asset.name)
    await page.getByRole('button', { name: 'Open password', exact: true }).click()
    await move.openMoveFromDrawer()

    await expect(move.dialog('password')).toBeVisible()
    await expect(move.submitButton('password')).toBeDisabled()

    await move.destinationField('password').click()
    const options = page.getByRole('listbox', { name: 'Suggestions' }).getByRole('option')
    await expect(options.filter({ hasText: ORG_ADIPISCING_FOUNDATION.name }).first()).toBeVisible()
    await expect(options.filter({ hasText: asset.organization_name })).toHaveCount(0)

    await page.getByRole('listbox', { name: 'Suggestions' }).getByRole('option', { name: ORG_ADIPISCING_FOUNDATION.name, exact: true }).click()
    await expect(move.submitButton('password')).toBeEnabled()

    await move.cancelButton('password').click()
    await expect(move.dialog('password')).toHaveCount(0)
  })
})
