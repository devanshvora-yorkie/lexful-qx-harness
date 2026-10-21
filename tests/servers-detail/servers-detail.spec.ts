import { test, expect } from '@playwright/test';
import { injectAuthCookies } from '../../auth-helper';
import { ServersListingPOM } from '../servers-listing/servers-listing-pom';
import { ServersDetailPOM } from './servers-detail-pom';

test.describe('Server Detail Drawer', () => {
  let listingPom: ServersListingPOM;

  test.beforeEach(async ({ page }) => {
    await injectAuthCookies(page.context());
    await page.goto('https://e2e-test.uat.lexful.net/docs/d/all/servers', {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    });
    listingPom = new ServersListingPOM(page);
    // Wait for actual row data — grid shows placeholder rows while loading
    await listingPom.rowByName('AAA-SRV-001').waitFor({ state: 'visible', timeout: 15000 });
  });

  test('clicking a row opens the detail drawer', async ({ page }) => {
    await listingPom.openRowDetail('AAA-SRV-001');

    // URL should have drawer param with the server UUID
    expect(page.url()).toContain('drawer=');
    expect(page.url()).toContain('servers');

    // Detail heading visible (h2 level)
    await expect(
      page.getByRole('heading', { name: 'AAA-SRV-001', level: 2 })
    ).toBeVisible({ timeout: 5000 });
  });

  test('detail drawer has Edit Name button', async ({ page }) => {
    await listingPom.openRowDetail('AAA-SRV-001');
    const detail = new ServersDetailPOM(page);

    // The Edit Name button is inside the h2 heading element
    await expect(detail.editNameButton()).toBeVisible({ timeout: 5000 });
  });

  test('Overview tab shows Relationships section', async ({ page }) => {
    await listingPom.openRowDetail('AAA-SRV-001');
    const detail = new ServersDetailPOM(page);

    // Overview tab should be selected by default
    await expect(detail.overviewTab()).toHaveAttribute('aria-selected', 'true');

    await expect(detail.overviewRelationshipsHeading()).toBeVisible({ timeout: 5000 });
    await expect(detail.viewAllRelationshipsButton()).toBeVisible();
  });

  test('Details tab shows all editable fields', async ({ page }) => {
    await listingPom.openRowDetail('AAA-SRV-001');
    const detail = new ServersDetailPOM(page);

    await detail.detailsTab().click();
    await page.waitForTimeout(500);

    // Role field — button text is "Edit Role" with value "Domain Controller"
    const roleBtn = detail.editRoleButton();
    await expect(roleBtn).toBeVisible();
    const roleText = await roleBtn.textContent();
    expect(roleText).toContain('Domain Controller');

    // IP Address field
    const ipBtn = detail.editIPAddressButton();
    await expect(ipBtn).toBeVisible();
    const ipText = await ipBtn.textContent();
    expect(ipText).toContain('10.27.10.20');

    // Operating System field
    const osBtn = detail.editOperatingSystemButton();
    await expect(osBtn).toBeVisible();
    const osText = await osBtn.textContent();
    expect(osText).toContain('IpsumLinux');
  });

  test('Details tab shows additional fields', async ({ page }) => {
    await listingPom.openRowDetail('AAA-SRV-001');
    const detail = new ServersDetailPOM(page);

    await detail.detailsTab().click();
    await page.waitForTimeout(500);

    // Platform
    const platformBtn = detail.editPlatformButton();
    await expect(platformBtn).toBeVisible();
    const platText = await platformBtn.textContent();
    expect(platText).toContain('Physical');

    // Warranty Expiration
    const warrantyBtn = detail.editWarrantyExpirationButton();
    await expect(warrantyBtn).toBeVisible();
    const warText = await warrantyBtn.textContent();
    expect(warText).toContain('2027');

    // Backup Plan
    const backupBtn = detail.editBackupPlanButton();
    await expect(backupBtn).toBeVisible();
    const backupText = await backupBtn.textContent();
    expect(backupText).toContain('AAA Aliquip Backup');
  });

  test('drawer close button closes the drawer', async ({ page }) => {
    await listingPom.openRowDetail('AAA-SRV-001');
    const detail = new ServersDetailPOM(page);

    // Verify drawer is open
    expect(page.url()).toContain('drawer=');

    // Close via the Close button
    await detail.drawerCloseButton().click({ timeout: 10000 });
    await page.waitForTimeout(500);

    // Drawer should be closed — URL should not have drawer param with id
    const url = page.url();
    expect(url).not.toContain('id=');
  });

  test('Escape key closes the drawer', async ({ page }) => {
    await listingPom.openRowDetail('AAA-SRV-001');

    // Verify drawer is open
    expect(page.url()).toContain('drawer=');

    // Press Escape
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);

    // Drawer should be closed
    const url = page.url();
    expect(url).not.toContain('id=');
  });

  test('Copy link button is present', async ({ page }) => {
    await listingPom.openRowDetail('AAA-SRV-001');
    const detail = new ServersDetailPOM(page);

    await expect(detail.copyLinkButton()).toBeVisible({ timeout: 5000 });
  });

  test('Expand record button is present', async ({ page }) => {
    await listingPom.openRowDetail('AAA-SRV-001');
    const detail = new ServersDetailPOM(page);

    await expect(detail.expandRecordButton()).toBeVisible({ timeout: 5000 });
  });

  test('More actions button is present', async ({ page }) => {
    await listingPom.openRowDetail('AAA-SRV-001');
    const detail = new ServersDetailPOM(page);

    await expect(detail.moreActionsButton()).toBeVisible({ timeout: 5000 });
  });
});
