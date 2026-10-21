import { test, expect } from '@playwright/test';
import { injectAuthCookies } from '../../auth-helper';
import { ServersListingPOM } from '../servers-listing/servers-listing-pom';
import { CreateAssetPOM } from './create-asset-pom';

test.describe('Create New Server Asset', () => {
  let listingPom: ServersListingPOM;
  let createPom: CreateAssetPOM;

  test.beforeEach(async ({ page }) => {
    await injectAuthCookies(page.context());
    
    // Reset URL first, then navigate fresh
    await page.goto('about:blank');
    await page.goto('https://e2e-test.uat.lexful.net/docs/d/all/servers', {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    });
    listingPom = new ServersListingPOM(page);
    createPom = new CreateAssetPOM(page);
    await expect(listingPom.assetTypeHeading()).toBeVisible({ timeout: 15000 });
    await page.locator('.ag-body-viewport').first().waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
  });

  test('clicking New opens the create drawer', async ({ page }) => {
    await listingPom.newButton().waitFor({ state: 'visible', timeout: 10000 });
    await listingPom.newButton().click();
    await page.waitForTimeout(2000);

    expect(page.url()).toContain('drawer=');
    expect(page.url()).toContain('new');

    await expect(createPom.createHeading()).toBeVisible({ timeout: 5000 });
  });

  test('Name field is required — Create disabled when empty', async ({ page }) => {
    await listingPom.newButton().waitFor({ state: 'visible', timeout: 10000 });
    await listingPom.newButton().click();
    await page.waitForTimeout(2000);

    await expect(createPom.nameField()).toBeVisible({ timeout: 5000 });

    const isDisabled = await createPom.isCreateDisabled();
    expect(isDisabled).toBe(true);
  });

  test('Create button enables when Name and Organization are set', async ({ page }) => {
    await listingPom.newButton().waitFor({ state: 'visible', timeout: 10000 });
    await listingPom.newButton().click();
    await page.waitForTimeout(2000);

    const nameField = createPom.nameField();
    await nameField.waitFor({ state: 'visible', timeout: 5000 });
    await nameField.fill('E2E-Test-SRV-' + Date.now());

    // In the all-organizations view the drawer requires an org before Create enables
    await page.getByRole('combobox').filter({ hasText: 'Select organization' }).first().click();
    await page.getByRole('option').first().click({ timeout: 5000 });

    // Form enablement is debounce-driven — poll instead of fixed waits
    await expect.poll(() => createPom.isCreateDisabled(), { timeout: 8000 }).toBe(false);
  });

  test('optional fields are visible in the Details tab', async ({ page }) => {
    await listingPom.newButton().waitFor({ state: 'visible', timeout: 10000 });
    await listingPom.newButton().click();
    await page.waitForTimeout(2000);

    await expect(createPom.hostnameField()).toBeVisible({ timeout: 5000 });
    await expect(createPom.ipAddressField()).toBeVisible();
    await expect(createPom.configurationField()).toBeVisible();
  });

  test('Cancel button closes the drawer without creating', async ({ page }) => {
    await listingPom.newButton().waitFor({ state: 'visible', timeout: 10000 });
    await listingPom.newButton().click();
    await page.waitForTimeout(2000);

    await createPom.nameField().fill('E2E-Test-SRV-' + Date.now());
    await page.waitForTimeout(500);

    await createPom.cancelButton().click({ timeout: 10000 });
    await page.waitForTimeout(1000);

    const url = page.url();
    expect(url).not.toContain('id=');
  });

  test('drawer Close (X) button closes the drawer', async ({ page }) => {
    await listingPom.newButton().waitFor({ state: 'visible', timeout: 10000 });
    await listingPom.newButton().click();
    await page.waitForTimeout(2000);

    await createPom.nameField().fill('E2E-Test-SRV-' + Date.now());
    await page.waitForTimeout(500);

    await createPom.drawerCloseButton().click({ timeout: 10000 });
    await page.waitForTimeout(1000);

    const url = page.url();
    expect(url).not.toContain('id=');
  });

  test('navigating to a different asset type opens its create form', async ({ page }) => {
    // Reset and navigate to Applications
    await page.goto('about:blank');
    await page.goto('https://e2e-test.uat.lexful.net/docs/d/all/applications', {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    });

    const appListingPom = new ServersListingPOM(page);
    await appListingPom.newButton().waitFor({ state: 'visible', timeout: 10000 });
    await appListingPom.newButton().click();
    await page.waitForTimeout(2000);

    const url = page.url();
    expect(url).toContain('drawer=');
    expect(url).toContain('new');

    const heading = page.getByRole('heading', { level: 2 });
    await expect(heading).toBeVisible({ timeout: 5000 });
  });
});
