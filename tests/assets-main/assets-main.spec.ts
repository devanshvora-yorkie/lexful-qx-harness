import { test, expect } from '@playwright/test';
import { injectAuthCookies } from '../../auth-helper';
import { AssetsListingPOM } from './assets-listing-pom';

test.describe('Assets Main Page', () => {
  let pom: AssetsListingPOM;

  test.beforeEach(async ({ page }) => {
    await injectAuthCookies(page.context());
    await page.goto('https://e2e-test.uat.lexful.net/docs/assets', {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    });
    pom = new AssetsListingPOM(page);
    // Wait for the main heading to be visible (SPA rendered)
    await expect(pom.assetsHeading()).toBeVisible({ timeout: 10000 });
  });

  test('page loads with Assets heading and counts', async () => {
    await expect(pom.assetsHeading()).toBeVisible();
    await expect(pom.assetCount()).toBeVisible();
    await expect(pom.typeCount()).toBeVisible();
  });

  test('displays asset type cards with counts', async () => {
    // Check a few known asset types are visible
    await expect(pom.assetTypeCard('Servers')).toBeVisible();
    await expect(pom.assetTypeCard('Applications')).toBeVisible();
    await expect(pom.assetTypeCard('Computers')).toBeVisible();
  });

  test('clicking into Servers type navigates to listing', async ({ page }) => {
    await pom.assetTypeCard('Servers').click();
    await page.waitForURL(/\/docs\/d\/all\/servers/, { timeout: 10000 });
    await expect(page.getByRole('heading', { name: 'Servers' })).toBeVisible({
      timeout: 10000,
    });
  });

  test('clicking into Applications type navigates to listing', async ({ page }) => {
    await pom.assetTypeCard('Applications').click();
    await page.waitForURL(/\/docs\/d\/all\/applications/, { timeout: 10000 });
    await expect(page.getByRole('heading', { name: 'Applications' })).toBeVisible({
      timeout: 10000,
    });
  });

  test('search opens Ask Lex with matching records', async ({ page }) => {
    // Type in search — triggers Ask AI panel with results
    await pom.searchAssetsBox().fill('Server');
    await page.waitForTimeout(3000); // allow AI to respond

    // Matching records listbox should appear
    const matchingRecords = page.getByRole('listbox', { name: 'Matching records' });
    await expect(matchingRecords).toBeVisible({ timeout: 10000 });
  });

  test('search shows browse buttons for asset types', async ({ page }) => {
    await pom.searchAssetsBox().fill('Server');
    await page.waitForTimeout(3000);

    // Buttons like "Browse Servers" should appear in the results area
    const browseBtn = page.getByRole('button', { name: 'Browse Servers' });
    await expect(browseBtn).toBeVisible({ timeout: 10000 });
  });

  test('Ask Lex button opens AI panel', async ({ page }) => {
    const askLexBtn = pom.askLexOpenButton();
    await expect(askLexBtn).toBeVisible();
    await askLexBtn.click();
    await page.waitForTimeout(1000);

    // Ask Lex panel should appear with input (contenteditable div)
    const input = pom.askLexAnythingInput();
    await expect(input).toBeVisible({ timeout: 5000 });
  });

  test('top bar elements are visible', async () => {
    await expect(pom.logo()).toBeVisible();
    await expect(pom.askLexButton()).toBeVisible();
    await expect(pom.globalSearch()).toBeVisible();
    await expect(pom.userAvatar()).toBeVisible();
  });

  test('sidebar navigation links are present', async () => {
    // Use locator count — some sidebar links may be positioned outside viewport
    const assets = pom.sidebarAssetsLink();
    const orgs = pom.sidebarOrganizationsLink();
    const passwords = pom.sidebarPasswordsLink();
    const documents = pom.sidebarDocumentsLink();
    
    await expect(assets).toHaveCount(1);
    await expect(orgs).toHaveCount(1);
    await expect(passwords).toHaveCount(1);
    await expect(documents).toHaveCount(1);
  });

  test('user menu opens and shows options', async ({ page }) => {
    await pom.userAvatar().click();
    await page.waitForTimeout(500);

    // User menu has: Profile, Settings, Log out (as menuitems)
    const profile = page.getByRole('menuitem', { name: 'Profile' });
    const settings = page.getByRole('menuitem', { name: 'Settings' });
    const logout = page.getByRole('menuitem', { name: 'Log out' });
    await expect(profile).toBeVisible();
    await expect(settings).toBeVisible();
    await expect(logout).toBeVisible();
  });
});
