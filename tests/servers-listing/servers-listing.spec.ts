import { test, expect } from '@playwright/test';
import { injectAuthCookies } from '../../auth-helper';
import { ServersListingPOM } from './servers-listing-pom';
import { ServersDetailPOM } from '../servers-detail/servers-detail-pom';

test.describe('Servers Listing Page', () => {
  let pom: ServersListingPOM;

  test.beforeEach(async ({ page }) => {
    await injectAuthCookies(page.context());
    
    // Reset URL first (remove any drawer params from previous test), then navigate fresh
    await page.goto('about:blank');
    await page.goto('https://e2e-test.uat.lexful.net/docs/d/all/servers', {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    });
    pom = new ServersListingPOM(page);
    // Wait for heading to be visible (SPA rendered)
    await expect(pom.assetTypeHeading()).toBeVisible({ timeout: 15000 });
    // Wait for actual row data — grid shows disabled placeholder checkboxes while "Row data is loading"
    await pom.rowByName('AAA-SRV-001').waitFor({ state: 'visible', timeout: 15000 });
  });

  test('page loads with heading and treegrid', async () => {
    await expect(pom.assetTypeHeading()).toBeVisible();
    await expect(pom.treegrid()).toBeVisible({ timeout: 5000 });
  });

  test('treegrid shows server rows with data', async () => {
    const row = pom.rowByName('AAA-SRV-001');
    await expect(row).toBeVisible({ timeout: 10000 });

    const cells = row.locator('[role=gridcell]');
    const cellCount = await cells.count();
    expect(cellCount).toBeGreaterThan(1);

    await expect(cells.first()).toContainText('AAA-SRV-001');
    await expect(cells.nth(1)).toContainText('Domain Controller');
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

  test('open row detail drawer and verify', async ({ page }) => {
    await pom.openRowDetail('AAA-SRV-001');

    expect(page.url()).toContain('drawer=');
    expect(page.url()).toContain('servers');

    await expect(
      page.getByRole('heading', { name: 'AAA-SRV-001', level: 2 })
    ).toBeVisible({ timeout: 5000 });

    await pom.closeDrawer();
    await page.waitForTimeout(500);
  });

  test('detail drawer has all 8 tabs', async ({ page }) => {
    await pom.openRowDetail('AAA-SRV-001');

    await expect(pom.overviewTab()).toBeVisible();
    await expect(pom.detailsTab()).toBeVisible();
    await expect(pom.relationshipsTab()).toBeVisible();
    await expect(pom.attachmentsTab()).toBeVisible();
    await expect(pom.accessTab()).toBeVisible();
    await expect(pom.historyTab()).toBeVisible();
    await expect(pom.sourcesTab()).toBeVisible();
    await expect(pom.systemInfoTab()).toBeVisible();

    await pom.closeDrawer();
  });

  test('details tab shows editable fields', async ({ page }) => {
    await pom.openRowDetail('AAA-SRV-001');
    await pom.detailsTab().click();
    await page.waitForTimeout(500);

    const detail = new ServersDetailPOM(page);
    await expect(detail.editRoleButton()).toBeVisible();
    await expect(detail.editIPAddressButton()).toBeVisible();
    await expect(detail.editOperatingSystemButton()).toBeVisible();
    await expect(detail.editPlatformButton()).toBeVisible();
    await expect(detail.editWarrantyExpirationButton()).toBeVisible();
    await expect(detail.editConfigurationButton()).toBeVisible();

    await pom.closeDrawer();
  });

  test('overview tab shows linked items', async ({ page }) => {
    await pom.openRowDetail('AAA-SRV-001');
    await pom.overviewTab().click();
    await page.waitForTimeout(500);

    await expect(pom.page.getByRole('heading', { name: 'Relationships', level: 3 })).toBeVisible({ timeout: 5000 });
    await expect(pom.page.getByRole('button', { name: 'View all' }).first()).toBeVisible();

    await pom.closeDrawer();
  });
});
