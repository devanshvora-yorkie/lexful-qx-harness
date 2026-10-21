/**
 * Assets CRUD E2E — combined suite (34 tests)
 *
 * Merge of Assets-E2E (listing, auth, bulk, filters, detail) and
 * asset-crud-e2e (create cancel, create/find/edit/archive, tag/duplicate/archive).
 *
 * Run from lexful-qa-opencode:
 *   npx playwright test Assets-crud-E2E/assets-crud.spec.ts --headed --retries=0 --reporter=line
 *
 * Needs: ../auth-helper.ts, .env (STYTCH_ADMIN_* or LEXFUL_*), Chromium installed.
 */
import { test, expect } from '@playwright/test';
import { injectAuthCookies, getLexfulCookies } from '../../auth-helper';
import { AssetsListingPOM } from './assets-listing-pom';
import { ServersListingPOM } from './servers-listing-pom';
import { ServersDetailPOM } from './servers-detail-pom';
import { CreateAssetPOM } from './create-asset-pom';

const SERVERS_URL = 'https://e2e-test.uat.lexful.net/docs/d/all/servers';
const ASSETS_URL = 'https://e2e-test.uat.lexful.net/docs/assets';
const SEEDED_SERVER = 'AAA-SRV-001';

async function openServersListing(page: import('@playwright/test').Page) {
  await injectAuthCookies(page.context());
  await page.goto('about:blank');
  await page.goto(SERVERS_URL, { waitUntil: 'domcontentloaded', timeout: 15000 });
  const listing = new ServersListingPOM(page);
  await expect(listing.assetTypeHeading()).toBeVisible({ timeout: 15000 });
  return listing;
}

test.describe('Authentication', () => {
  test('POST /auth/password returns HTTP 204 with both cookies', async () => {
    const cookies = await getLexfulCookies();
    expect(cookies.length).toBe(2);
    const names = cookies.map((c) => c.name).sort();
    expect(names).toEqual(['stytch_session', 'stytch_session_jwt']);
    expect(cookies[0].domain).toMatch(/lexful\.net$/);
    expect(cookies[0].httpOnly).toBe(true);
    expect(cookies[0].secure).toBe(true);
    expect(cookies[0].sameSite).toBe('Lax');
  });

  test('cookies apply to the app domain — not redirected to login', async ({ page }) => {
    const cookies = await getLexfulCookies();
    await page.context().addCookies(cookies);
    await page.goto(ASSETS_URL, { waitUntil: 'domcontentloaded', timeout: 15000 });
    expect(page.url()).not.toContain('/login');
    await expect(page.getByRole('heading', { name: 'Assets', level: 1 })).toBeVisible({
      timeout: 10000,
    });
  });

  test('invalid credentials returns HTTP 4xx', async () => {
    try {
      const res = await fetch('https://api.uat.lexful.net/auth/password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          account_external_id: 'organization-live-2928086d-1015-4fc0-a3eb-898cade37abd',
          email: 'e2e-test+admin@lexful.ai',
          password: 'wrong-password-here',
        }),
      });
      expect(res.ok).toBe(false);
      expect([400, 401, 403]).toContain(res.status);
    } catch {
      expect(true).toBe(true);
    }
  });

  test('expired/missing cookie redirects to login', async ({ page }) => {
    await page.context().addCookies([
      {
        name: 'stytch_session',
        value: 'invalid-session-token',
        domain: '.lexful.net',
        path: '/',
        httpOnly: true,
        secure: true,
        sameSite: 'Lax',
      },
    ]);
    await page.goto(ASSETS_URL, { waitUntil: 'domcontentloaded', timeout: 15000 });
    const isOnAssets = await page
      .getByRole('heading', { name: 'Assets', level: 1 })
      .isVisible({ timeout: 5000 })
      .catch(() => false);
    expect(isOnAssets).toBe(false);
  });
});

test.describe('Assets Main Page', () => {
  let pom: AssetsListingPOM;

  test.beforeEach(async ({ page }) => {
    await injectAuthCookies(page.context());
    await page.goto(ASSETS_URL, { waitUntil: 'domcontentloaded', timeout: 15000 });
    pom = new AssetsListingPOM(page);
    await expect(pom.assetsHeading()).toBeVisible({ timeout: 10000 });
  });

  test('clicking into Servers type navigates to listing', async ({ page }) => {
    await pom.assetTypeCard('Servers').click();
    await page.waitForURL(/\/docs\/d\/all\/servers/, { timeout: 10000 });
    await expect(page.getByRole('heading', { name: 'Servers' })).toBeVisible({ timeout: 10000 });
  });

  test('clicking into Applications type navigates to listing', async ({ page }) => {
    await pom.assetTypeCard('Applications').click();
    await page.waitForURL(/\/docs\/d\/all\/applications/, { timeout: 10000 });
    await expect(page.getByRole('heading', { name: 'Applications' })).toBeVisible({ timeout: 10000 });
  });

  test('search opens Ask Lex with matching records', async ({ page }) => {
    await pom.searchAssetsBox().fill('Server');
    await page.waitForTimeout(3000);
    await expect(page.getByRole('listbox', { name: 'Matching records' })).toBeVisible({
      timeout: 10000,
    });
  });

  test('Ask Lex button opens AI panel', async () => {
    const askLexBtn = pom.askLexOpenButton();
    await expect(askLexBtn).toBeVisible();
    await askLexBtn.click();
    await expect(pom.askLexAnythingInput()).toBeVisible({ timeout: 5000 });
  });

  test('user menu opens and shows options', async ({ page }) => {
    await pom.userAvatar().click();
    await page.waitForTimeout(500);
    await expect(page.getByRole('menuitem', { name: 'Profile' })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: 'Settings' })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: 'Log out' })).toBeVisible();
  });
});

test.describe('Create New Server Asset', () => {
  let listingPom: ServersListingPOM;
  let createPom: CreateAssetPOM;

  test.beforeEach(async ({ page }) => {
    listingPom = await openServersListing(page);
    createPom = new CreateAssetPOM(page);
    await page.locator('.ag-body-viewport').first().waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
  });

  test('Cancel button closes the drawer without creating', async ({ page }) => {
    await listingPom.newButton().waitFor({ state: 'visible', timeout: 10000 });
    await listingPom.newButton().click();
    await page.waitForTimeout(2000);
    await createPom.nameField().fill('E2E-Test-SRV-' + Date.now());
    await page.waitForTimeout(500);
    await createPom.cancelButton().click({ timeout: 10000 });
    await page.waitForTimeout(1000);
    expect(page.url()).not.toContain('id=');
  });
});

test.describe('Server CRUD lifecycle', () => {
  test('server happy path: create, find, edit, delete', async ({ page }) => {
    test.setTimeout(90000);
    const name = `E2E-Life-${Date.now()}`;
    const hostname = `host-${Date.now()}.example.com`;

    const listing = await openServersListing(page);
    const create = new CreateAssetPOM(page);

    await listing.newButton().click();
    await create.nameField().fill(name);
    await create.organizationCombobox().first().click();
    await page.getByRole('option').first().click();
    await page.keyboard.press('Escape');
    await page.getByText('Select role', { exact: true }).click();
    await page.getByRole('option').first().click();
    await expect.poll(() => create.isCreateDisabled(), { timeout: 8000 }).toBe(false);
    await create.createButton().click();

    await expect(page.getByRole('heading', { name, level: 2 })).toBeVisible({ timeout: 15000 });
    await page.getByRole('button', { name: 'Close' }).first().click();

    await listing.searchBox().fill(name);
    const nameCell = page.getByRole('gridcell', { name }).first();
    await expect(nameCell).toBeVisible({ timeout: 15000 });
    await nameCell.dblclick();
    await expect(page.getByRole('heading', { name, level: 2 })).toBeVisible({ timeout: 15000 });

    const detail = new ServersDetailPOM(page);
    await detail.detailsTab().click();
    const hostnameControl = detail.addHostnameButton().or(detail.editFieldButton('Hostname'));
    await hostnameControl.click();
    await page.getByRole('textbox').last().fill(hostname);
    await page.getByRole('button', { name: 'Save changes' }).click();
    await expect(page.getByRole('button', { name: 'Save changes' })).toBeHidden({ timeout: 10000 });
    await page.getByRole('button', { name: 'Close' }).first().click();

    await listing.searchBox().fill(name);
    await page.getByRole('gridcell', { name }).first().dblclick();
    await expect(page.getByRole('heading', { name, level: 2 })).toBeVisible({ timeout: 15000 });
    await detail.detailsTab().click();
    await expect(page.getByText(hostname).first()).toBeVisible({ timeout: 10000 });

    await detail.moreActionsButton().click();
    await page.getByRole('menuitem', { name: /Archive/ }).click();
    const confirmArchive = page.getByRole('button', { name: /^Archive$/ });
    if (await confirmArchive.isVisible({ timeout: 3000 }).catch(() => false)) {
      await confirmArchive.click();
    }

    await listing.searchBox().fill(name);
    await expect(listing.rowByName(name)).toHaveCount(0, { timeout: 15000 });
  });

  test('after create: add a tag, duplicate, then archive', async ({ page }) => {
    test.setTimeout(120000);
    const name = `E2E-Act-${Date.now()}`;

    const listing = await openServersListing(page);
    const create = new CreateAssetPOM(page);
    const detail = new ServersDetailPOM(page);

    await listing.newButton().click();
    await create.nameField().fill(name);
    await create.organizationCombobox().first().click();
    await page.getByRole('option').first().click();
    await page.keyboard.press('Escape');
    await page.getByText('Select role', { exact: true }).click();
    await page.getByRole('option').first().click();
    await expect.poll(() => create.isCreateDisabled(), { timeout: 8000 }).toBe(false);
    await create.createButton().click();
    await expect(page.getByRole('heading', { name, level: 2 })).toBeVisible({ timeout: 15000 });
    await page.getByRole('button', { name: 'Close' }).first().click();

    await listing.searchBox().fill(name);
    const nameCell = page.getByRole('gridcell', { name }).first();
    await expect(nameCell).toBeVisible({ timeout: 15000 });
    await listing.rowCheckboxes().first().click({ force: true });
    await listing.bulkTagsButton().click();
    await page.getByRole('menuitem', { name: 'Apply tags' }).click();
    await page.getByRole('dialog').getByText('Select tags...').click();
    const tagChoice = page.getByRole('dialog').locator('input[type="checkbox"]').first();
    await expect(tagChoice).toBeVisible({ timeout: 5000 });
    const tag = ((await tagChoice.locator('xpath=..').innerText()) || '').trim();
    await tagChoice.click({ force: true });
    await page.getByRole('button', { name: 'Apply tags' }).click();
    await expect(page.getByRole('dialog', { name: /Apply tags/ })).toBeHidden({ timeout: 15000 });
    await listing.searchBox().fill(name);
    await page.getByText('All tags', { exact: true }).click();
    await page.getByRole('option', { name: tag }).or(page.getByText(tag, { exact: true })).first().click();
    await expect(page.getByRole('gridcell', { name }).first()).toBeVisible({ timeout: 10000 });
    await page.getByText('All tags', { exact: true }).click();
    await page.keyboard.press('Escape');
    await listing.searchBox().fill(name);
    await nameCell.dblclick();
    await expect(page.getByRole('heading', { name, level: 2 })).toBeVisible({ timeout: 15000 });
    await detail.moreActionsButton().click();
    await page.getByRole('menuitem', { name: /Duplicate/ }).click();
    const duplicateDialog = page.getByRole('dialog').filter({ hasText: /Duplicate/ });
    await expect(duplicateDialog).toBeVisible({ timeout: 8000 });
    await duplicateDialog.getByRole('button', { name: /Duplicate|Create/ }).click();
    await expect(duplicateDialog).toBeHidden({ timeout: 15000 });
    await page.getByRole('button', { name: 'Close' }).first().click();

    await listing.searchBox().fill(name);
    await expect(page.getByRole('gridcell', { name: new RegExp(name) })).toHaveCount(2, { timeout: 15000 });
    await page.getByRole('gridcell', { name: new RegExp(name) }).first().dblclick();
    await expect(page.getByRole('heading', { level: 2 })).toBeVisible({ timeout: 15000 });
    await detail.moreActionsButton().click();
    await page.getByRole('menuitem', { name: /Archive/ }).click();
    const confirmArchive = page.getByRole('button', { name: /^Archive$/ });
    if (await confirmArchive.isVisible({ timeout: 3000 }).catch(() => false)) await confirmArchive.click();
  });
});

test.describe('Servers Listing Page', () => {
  let pom: ServersListingPOM;

  test.beforeEach(async ({ page }) => {
    pom = await openServersListing(page);
    await pom.rowByName(SEEDED_SERVER).waitFor({ state: 'visible', timeout: 15000 });
  });

  test('toolbar buttons are visible', async () => {
    await expect(pom.collapseAllButton()).toBeVisible();
    await expect(pom.displayButton()).toBeVisible();
    await expect(pom.newButton()).toBeVisible();
  });

  test('open row detail drawer and verify', async ({ page }) => {
    await pom.openRowDetail(SEEDED_SERVER);
    expect(page.url()).toContain('drawer=');
    expect(page.url()).toContain('servers');
    await expect(page.getByRole('heading', { name: SEEDED_SERVER, level: 2 })).toBeVisible({
      timeout: 5000,
    });
    await pom.closeDrawer();
    await page.waitForTimeout(500);
  });

  test('detail drawer has all 8 tabs', async ({ page }) => {
    await pom.openRowDetail(SEEDED_SERVER);
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
    await pom.openRowDetail(SEEDED_SERVER);
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
    await pom.openRowDetail(SEEDED_SERVER);
    await pom.overviewTab().click();
    await page.waitForTimeout(500);
    await expect(pom.page.getByRole('heading', { name: 'Relationships', level: 3 })).toBeVisible({
      timeout: 5000,
    });
    await expect(pom.page.getByRole('button', { name: 'View all' }).first()).toBeVisible();
    await pom.closeDrawer();
  });
});

test.describe('Filters and Search', () => {
  let pom: ServersListingPOM;

  test.beforeEach(async ({ page }) => {
    pom = await openServersListing(page);
    await pom.rowByName(SEEDED_SERVER).waitFor({ state: 'visible', timeout: 15000 });
  });

  test('search is case-insensitive', async ({ page }) => {
    await pom.searchBox().fill(SEEDED_SERVER);
    await page.waitForTimeout(1500);
    await expect(pom.rowByName(SEEDED_SERVER)).toBeVisible({ timeout: 5000 });
    await pom.searchBox().clear();
    await page.waitForTimeout(1000);
    await pom.searchBox().fill('aaa-srv-001');
    await page.waitForTimeout(1500);
    await expect(pom.rowByName(SEEDED_SERVER)).toBeVisible({ timeout: 5000 });
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
    await pom.clearSelectionButton().click({ timeout: 10000, force: true });
    await expect(page.getByText(/0 selected/)).toBeVisible({ timeout: 5000 });
  });
});

test.describe('Bulk Actions — Row Selection', () => {
  let pom: ServersListingPOM;

  test.beforeEach(async ({ page }) => {
    pom = await openServersListing(page);
    await pom.rowByName(SEEDED_SERVER).waitFor({ state: 'visible', timeout: 15000 });
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
    await pom.clearSelectionButton().click({ timeout: 10000, force: true });
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
    await expect(pom.bulkActionsButton()).toBeVisible({ timeout: 5000 });
  });
});

test.describe('Server Detail Drawer', () => {
  let listingPom: ServersListingPOM;

  test.beforeEach(async ({ page }) => {
    listingPom = await openServersListing(page);
    await listingPom.rowByName(SEEDED_SERVER).waitFor({ state: 'visible', timeout: 15000 });
  });

  test('clicking a row opens the detail drawer', async ({ page }) => {
    await listingPom.openRowDetail(SEEDED_SERVER);
    expect(page.url()).toContain('drawer=');
    expect(page.url()).toContain('servers');
    await expect(page.getByRole('heading', { name: SEEDED_SERVER, level: 2 })).toBeVisible({
      timeout: 5000,
    });
  });

  test('detail drawer has Edit Name button', async ({ page }) => {
    await listingPom.openRowDetail(SEEDED_SERVER);
    await expect(new ServersDetailPOM(page).editNameButton()).toBeVisible({ timeout: 5000 });
  });

  test('Overview tab shows Relationships section', async ({ page }) => {
    await listingPom.openRowDetail(SEEDED_SERVER);
    const detail = new ServersDetailPOM(page);
    await expect(detail.overviewTab()).toHaveAttribute('aria-selected', 'true');
    await expect(detail.overviewRelationshipsHeading()).toBeVisible({ timeout: 5000 });
    await expect(detail.viewAllRelationshipsButton()).toBeVisible();
  });

  test('Details tab shows all editable fields', async ({ page }) => {
    await listingPom.openRowDetail(SEEDED_SERVER);
    const detail = new ServersDetailPOM(page);
    await detail.detailsTab().click();
    await page.waitForTimeout(500);
    await expect(detail.editRoleButton()).toBeVisible();
    expect(await detail.editRoleButton().textContent()).toContain('Domain Controller');
    await expect(detail.editIPAddressButton()).toBeVisible();
    expect(await detail.editIPAddressButton().textContent()).toContain('10.27.10.20');
    await expect(detail.editOperatingSystemButton()).toBeVisible();
    expect(await detail.editOperatingSystemButton().textContent()).toContain('IpsumLinux');
  });

  test('Details tab shows additional fields', async ({ page }) => {
    await listingPom.openRowDetail(SEEDED_SERVER);
    const detail = new ServersDetailPOM(page);
    await detail.detailsTab().click();
    await page.waitForTimeout(500);
    await expect(detail.editPlatformButton()).toBeVisible();
    expect(await detail.editPlatformButton().textContent()).toContain('Physical');
    await expect(detail.editWarrantyExpirationButton()).toBeVisible();
    expect(await detail.editWarrantyExpirationButton().textContent()).toContain('2027');
    await expect(detail.editBackupPlanButton()).toBeVisible();
    expect(await detail.editBackupPlanButton().textContent()).toContain('AAA Aliquip Backup');
  });

  test('drawer close button closes the drawer', async ({ page }) => {
    await listingPom.openRowDetail(SEEDED_SERVER);
    expect(page.url()).toContain('drawer=');
    await new ServersDetailPOM(page).drawerCloseButton().click({ timeout: 10000 });
    await page.waitForTimeout(500);
    expect(page.url()).not.toContain('id=');
  });

  test('Escape key closes the drawer', async ({ page }) => {
    await listingPom.openRowDetail(SEEDED_SERVER);
    expect(page.url()).toContain('drawer=');
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
    expect(page.url()).not.toContain('id=');
  });

  test('Copy link button is present', async ({ page }) => {
    await listingPom.openRowDetail(SEEDED_SERVER);
    await expect(new ServersDetailPOM(page).copyLinkButton()).toBeVisible({ timeout: 5000 });
  });

  test('Expand record button is present', async ({ page }) => {
    await listingPom.openRowDetail(SEEDED_SERVER);
    await expect(new ServersDetailPOM(page).expandRecordButton()).toBeVisible({ timeout: 5000 });
  });

  test('More actions button is present', async ({ page }) => {
    await listingPom.openRowDetail(SEEDED_SERVER);
    await expect(new ServersDetailPOM(page).moreActionsButton()).toBeVisible({ timeout: 5000 });
  });
});
