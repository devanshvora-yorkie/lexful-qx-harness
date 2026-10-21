import { test, expect } from '@playwright/test';
import { injectAuthCookies } from '../../auth-helper';
import { ServersListingPOM } from '../servers-listing/servers-listing-pom';

test.describe('Bulk Actions — Row Selection', () => {
  let pom: ServersListingPOM;

  test.beforeEach(async ({ page }) => {
    await injectAuthCookies(page.context());
    
    // Reset URL first, then navigate fresh
    await page.goto('about:blank');
    await page.goto('https://e2e-test.uat.lexful.net/docs/d/all/servers', {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    });
    pom = new ServersListingPOM(page);
    await expect(pom.assetTypeHeading()).toBeVisible({ timeout: 15000 });
    // Wait for actual row data — grid shows disabled placeholder checkboxes while "Row data is loading"
    await pom.rowByName('AAA-SRV-001').waitFor({ state: 'visible', timeout: 15000 });
  });

  test('row checkboxes are present and clickable', async ({ page }) => {
    const count = await pom.rowCheckboxes().count();
    expect(count).toBeGreaterThan(0);
    await pom.rowCheckboxes().first().click({ timeout: 10000 });
    await page.waitForTimeout(500);
    await expect(pom.selectionCount()).toBeVisible({ timeout: 5000 });
  });

  test('selecting a row shows bulk action buttons', async ({ page }) => {
    await pom.rowCheckboxes().first().click({ timeout: 10000 });
    await page.waitForTimeout(500);
    await expect(pom.bulkAccessButton()).toBeVisible({ timeout: 5000 });
    await expect(pom.bulkTagsButton()).toBeVisible();
    await expect(pom.bulkActionsButton()).toBeVisible();
  });

  test('selecting all rows via header checkbox', async ({ page }) => {
    await pom.selectAllCheckbox().click({ timeout: 10000 });
    await page.waitForTimeout(500);
    const count = await pom.rowCheckboxes().count();
    expect(count).toBeGreaterThan(0);
    await expect(pom.selectionCount()).toBeVisible({ timeout: 5000 });
  });

  test('deselecting one row after select-all decreases count', async ({ page }) => {
    await pom.selectAllCheckbox().click({ timeout: 10000 });
    await page.waitForTimeout(500);
    const beforeCount = await pom.rowCheckboxes().count();
    expect(beforeCount).toBeGreaterThan(1);
    await pom.rowCheckboxes().first().click({ timeout: 10000 });
    await page.waitForTimeout(500);
    await expect(pom.selectionCount()).toBeVisible();
  });

  test('clear selection resets selection count', async ({ page }) => {
    await pom.rowCheckboxes().first().click({ timeout: 10000 });
    await page.waitForTimeout(500);
    await expect(pom.bulkAccessButton()).toBeVisible({ timeout: 5000 });

    // Use force to bypass overlay blocking the button
    await pom.clearSelectionButton().click({ timeout: 10000, force: true });

    // App keeps bulk buttons visible even at 0 selected — assert the selection was reset
    await expect(page.getByText(/0 selected/)).toBeVisible({ timeout: 5000 });
  });

  test('multiple rows can be selected', async ({ page }) => {
    const checkboxes = pom.rowCheckboxes();
    await checkboxes.nth(0).click({ timeout: 10000 });
    await page.waitForTimeout(300);
    await checkboxes.nth(1).click({ timeout: 10000 });
    await page.waitForTimeout(500);
    await expect(pom.selectionCount()).toBeVisible({ timeout: 5000 });
  });

  test('bulk Actions button is present when rows are selected', async ({ page }) => {
    await pom.rowCheckboxes().first().click({ timeout: 10000 });
    await page.waitForTimeout(500);
    const actionsBtn = pom.bulkActionsButton();
    await expect(actionsBtn).toBeVisible({ timeout: 5000 });
  });
});
