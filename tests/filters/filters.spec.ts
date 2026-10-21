import { test, expect } from '@playwright/test';
import { injectAuthCookies } from '../../auth-helper';
import { ServersListingPOM } from '../servers-listing/servers-listing-pom';

test.describe('Filters and Search', () => {
  let pom: ServersListingPOM;

  test.beforeEach(async ({ page }) => {
    await injectAuthCookies(page.context());
    
    // Reset URL first, then navigate fresh (prevents AG Grid from not re-rendering)
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

  test('search filters by hostname/name', async ({ page }) => {
    let row = pom.rowByName('AAA-SRV-001');
    await expect(row).toBeVisible({ timeout: 5000 });
    await pom.searchBox().fill('ZZZ-NOT-EXIST');
    await page.waitForTimeout(1500);
    row = pom.rowByName('AAA-SRV-001');
    const visible = await row.isVisible({ timeout: 3000 }).catch(() => false);
    expect(visible).toBe(false);
  });

  test('search clears and shows all rows again', async ({ page }) => {
    await pom.searchBox().fill('ZZZ-NOT-EXIST');
    await page.waitForTimeout(1500);
    await pom.searchBox().clear();
    await page.waitForTimeout(2000);
    const row = pom.rowByName('AAA-SRV-001');
    await expect(row).toBeVisible({ timeout: 10000 });
  });

  test('search is case-insensitive', async ({ page }) => {
    await pom.searchBox().fill('AAA-SRV-001');
    await page.waitForTimeout(1500);
    let row = pom.rowByName('AAA-SRV-001');
    await expect(row).toBeVisible({ timeout: 5000 });
    await pom.searchBox().clear();
    await page.waitForTimeout(1000);
    await pom.searchBox().fill('aaa-srv-001');
    await page.waitForTimeout(1500);
    row = pom.rowByName('AAA-SRV-001');
    await expect(row).toBeVisible({ timeout: 5000 });
  });

  test('partial search matches', async ({ page }) => {
    await pom.searchBox().fill('AAA');
    await page.waitForTimeout(1500);
    const row = pom.rowByName('AAA-SRV-001');
    await expect(row).toBeVisible({ timeout: 5000 });
  });

  test('Asset status filter button is visible', async () => {
    await expect(pom.assetStatusFilter()).toBeVisible();
    const text = await pom.assetStatusFilter().textContent();
    expect(text).toContain('Active');
  });

  test('Filters panel opens and shows field selector', async ({ page }) => {
    await pom.filtersButton().click();
    await page.waitForTimeout(500);
    const filterField = pom.page.getByRole('combobox', { name: 'Filter field' });
    await expect(filterField).toBeVisible({ timeout: 5000 });
  });

  test('column headers are present', async () => {
    await expect(pom.columnHeader('Name')).toBeVisible();
    await expect(pom.columnHeader('Role')).toBeVisible();
    await expect(pom.columnHeader('Hostname')).toBeVisible();
    await expect(pom.columnHeader('IP Address')).toBeVisible();
  });

  test('toolbar buttons are visible', async () => {
    await expect(pom.collapseAllButton()).toBeVisible();
    await expect(pom.displayButton()).toBeVisible();
    await expect(pom.newButton()).toBeVisible();
  });

  test('row checkboxes are present for selection', async () => {
    const count = await pom.rowCheckboxes().count();
    expect(count).toBeGreaterThan(0);
  });

  test('select-all checkbox is present', async () => {
    await expect(pom.selectAllCheckbox()).toBeVisible();
  });

  test('bulk action buttons appear when rows selected', async ({ page }) => {
    await pom.rowCheckboxes().first().click({ timeout: 10000 });
    await page.waitForTimeout(500);
    await expect(pom.bulkAccessButton()).toBeVisible({ timeout: 5000 });
    await expect(pom.bulkTagsButton()).toBeVisible();
    await expect(pom.bulkActionsButton()).toBeVisible();
  });

  test('clear selection resets selection count', async ({ page }) => {
    await pom.rowCheckboxes().first().click({ timeout: 10000 });
    await page.waitForTimeout(500);
    await expect(pom.bulkAccessButton()).toBeVisible({ timeout: 5000 });

    // Use force to bypass overlay
    await pom.clearSelectionButton().click({ timeout: 10000, force: true });

    // App keeps bulk buttons visible even at 0 selected — assert the selection was reset
    await expect(page.getByText(/0 selected/)).toBeVisible({ timeout: 5000 });
  });
});
