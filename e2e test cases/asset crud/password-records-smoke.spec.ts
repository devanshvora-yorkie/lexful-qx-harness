/**
 * Password records — smoke. Record drawer and Copy password.
 *
 * Promoted from LEX-3642 (run 2026-10-29_1121Z_63c8). Rows AC-039 and AC-040 in FEATURE.md.
 *
 * Surface : https://e2e-test.uat.lexful.net/docs/d/all/system.password
 * POM     : ./password-records-pom.ts
 * Persona : admin (default session)
 */
import { test, expect } from '@playwright/test'
import { injectAuthCookies } from '../../auth-helper'
import {
  PasswordRecordDrawer,
  PasswordsListPage,
  SEEDED_PASSWORD,
  UUID_PATTERN,
} from './password-records-pom'

test.beforeEach(async ({ page }) => {
  await injectAuthCookies(page.context())
})

test.afterEach(async ({ page }) => {
  // Nothing is created here. Leaving the page closes any open drawer or dialog,
  // so the next test starts from a clean listing.
  await page.goto('about:blank')
})

test.describe('Password records — smoke', () => {
  test(
    'password record drawer Overview shows username, URL and a masked password',
    { tag: ['@positive', '@smoke'] },
    async ({ page }) => {
      const list = new PasswordsListPage(page)
      await list.open()
      await list.openQuickView(SEEDED_PASSWORD)
      await list.openRecordFromQuickView()

      const drawer = new PasswordRecordDrawer(page)
      await expect(drawer.tab('Overview')).toHaveAttribute('aria-selected', 'true')

      const overview = drawer.overviewPanel()
      await expect(overview.getByText('Username', { exact: true })).toBeVisible()
      await expect(overview.getByText('URL', { exact: true })).toBeVisible()
      await expect(overview.getByText('Password', { exact: true })).toBeVisible()
      await expect(overview.getByText(/^•+$/)).toBeVisible()
      await expect(overview.getByRole('button', { name: 'Copy password', exact: true })).toBeVisible()
      await expect(overview.getByRole('button', { name: 'Copy username', exact: true })).toBeVisible()
    },
  )

  test(
    'Copy password requests the secure password from the API',
    { tag: ['@positive', '@smoke'] },
    async ({ page }) => {
      const list = new PasswordsListPage(page)
      await list.open()
      await list.openQuickView(SEEDED_PASSWORD)
      await list.openRecordFromQuickView()

      const drawer = new PasswordRecordDrawer(page)
      await drawer.tab('Details').click()
      await expect(drawer.detailsPanel()).toBeVisible()

      const secureRead = page.waitForResponse(
        (response) =>
          new RegExp(`/v1/assets/system\\.password/${UUID_PATTERN}/secure/password$`).test(
            response.url().split('?')[0],
          ) && response.status() === 200,
        { timeout: 20_000 },
      )
      await drawer.detailsPanel().getByRole('button', { name: 'Copy password', exact: true }).click()
      const response = await secureRead
      expect(response.status()).toBe(200)
      await expect(page.getByText('You don’t have permission to reveal this secret.')).toHaveCount(0)
    },
  )
})
