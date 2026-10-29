/**
 * LEX-3554 — Move dialog gating, Cancel, and the ordinary PATCH guard (Smoke).
 *
 * Promoted from runs/tickets/LEX-3554/2026-10-29_0929Z_45ca (TC-LEX-3554-002, -003, -004).
 * Surface : Passwords list → Ctrl-K palette → Password quick view → Open password → More actions → Move…
 * POM     : ./move-records-pom.ts
 * Persona : admin (default session)
 */
import { test, expect } from '@playwright/test'
import { injectAuthCookies } from '../../auth-helper'
import {
  ACCOUNT_ID,
  ORG_ADIPISCING_FOUNDATION,
  PASSWORDS_URL,
  MovePage,
  getAsset,
  listAssets,
  moveAssetBack,
  openRecordFromPalette,
  pickEligibleAsset,
  API_URL,
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

  test('Cancel closes the Move dialog and submits no move', {
    tag: ['@edge', '@smoke'],
  }, async ({ page }) => {
    test.setTimeout(90000)
    const asset = await pickEligibleAsset(page, 'system.password', ORG_ADIPISCING_FOUNDATION)
    touched = { assetType: 'system.password', id: asset.id, organizationId: asset.organization_id }
    const move = new MovePage(page)
    const moveRequests: string[] = []
    page.on('request', (req) => {
      // Match the submit path exactly. /v1/assets/jobs/move/preview is a read-only POST and is not a move.
      if (req.method() === 'POST' && new URL(req.url()).pathname === '/v1/assets/jobs/move') moveRequests.push(req.url())
    })

    await gotoApp(page, PASSWORDS_URL)
    await openRecordFromPalette(page, asset.name)
    await page.getByRole('button', { name: 'Open password', exact: true }).click()
    await move.openMoveFromDrawer()
    await move.chooseDestination('password', ORG_ADIPISCING_FOUNDATION.name)
    await expect(move.submitButton('password')).toBeEnabled()

    await move.cancelButton('password').click()
    await expect(move.dialog('password')).toHaveCount(0)

    // Give any stray request time to leave the page before asserting none was sent.
    await expect.poll(() => moveRequests.length, { timeout: 3000 }).toBe(0)
    const current = await getAsset(page, 'system.password', asset.id)
    expect(current.organization_id).toBe(asset.organization_id)
  })

  test('Ordinary PATCH rejects an organization change and leaves the record in place', {
    tag: ['@negative', '@smoke'],
  }, async ({ page }) => {
    const asset = (await listAssets(page, 'system.password')).find((row) => row.organization_id !== ORG_ADIPISCING_FOUNDATION.id)
    if (!asset) throw new Error('No password outside the destination organization to test the PATCH guard')
    const before = await getAsset(page, 'system.password', asset.id)
    touched = { assetType: 'system.password', id: asset.id, organizationId: before.organization_id }

    const res = await page.request.patch(`${API_URL}/v1/assets/system.password/${asset.id}`, {
      headers: { 'X-Account-Id': ACCOUNT_ID, 'Content-Type': 'application/json' },
      data: { organization_id: ORG_ADIPISCING_FOUNDATION.id },
    })
    expect(res.status()).toBe(400)
    const body = await res.json()
    expect(body.error_code).toBe('ORGANIZATION_CHANGE_REQUIRES_MOVE')
    expect(body.message).toBe('Organization cannot be changed through PATCH. Use Move instead.')

    const after = await getAsset(page, 'system.password', asset.id)
    expect(after.organization_id).toBe(before.organization_id)
    expect(after.organization_name).toBe(before.organization_name)
  })
})
