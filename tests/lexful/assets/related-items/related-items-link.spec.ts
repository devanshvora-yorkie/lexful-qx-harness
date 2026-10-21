import { test, expect, type Response } from '@playwright/test';
import { API_BASE, CONFIG, CONTACT, RelatedItemsApi, RelatedItemsCommonPOM } from './related-items-common-pom';
import { RelationshipsPOM } from './related-items-pom';

// AC: "Link assets" dialog (search, filters), create a link (with and without description), search narrows results.
test.describe('Related items — link assets dialog and create', () => {
  test.beforeEach(async ({ page }) => {
    await new RelatedItemsCommonPOM(page).authenticate();
    await new RelatedItemsApi(page.request).clear(CONTACT);
  });

  test.afterEach(async ({ page }) => {
    await new RelatedItemsApi(page.request).clear(CONTACT);
  });

  test('Link assets dialog opens with search box, organization and record type filters, and results', async ({ page }) => {
    const common = new RelatedItemsCommonPOM(page);
    const rel = new RelationshipsPOM(page);
    await common.openRelationshipsTab(CONTACT);

    await rel.openLinkDialog();

    await expect(rel.searchInput()).toBeVisible();
    await expect(rel.organizationCombobox()).toBeVisible();
    await expect(rel.recordTypeCombobox()).toContainText('Configurations');
    await expect(rel.resultButton(CONFIG.name)).toBeVisible();
  });

  test('typing in Search records to link narrows the result list, and a matching term restores it', async ({ page }) => {
    const common = new RelatedItemsCommonPOM(page);
    const rel = new RelationshipsPOM(page);
    await common.openRelationshipsTab(CONTACT);
    await rel.openLinkDialog();
    await expect(rel.resultButton(CONFIG.name)).toBeVisible();

    const assetSearch = (r: Response): boolean =>
      r.request().method() === 'GET' &&
      r.url().startsWith(`${API_BASE}/v1/assets/`) &&
      !r.url().includes('/related') &&
      r.status() === 200;

    const noMatch = page.waitForResponse(assetSearch);
    await rel.searchInput().fill('zz-no-such-asset-lex2293');
    await noMatch;
    await expect(rel.resultButton(CONFIG.name)).toHaveCount(0);

    const match = page.waitForResponse(assetSearch);
    await rel.searchInput().fill(CONFIG.name);
    await match;
    await expect(rel.resultButton(CONFIG.name)).toBeVisible();
  });

  test('linking an asset without a description creates the relationship (PUT 201) and lists it', async ({ page }) => {
    const common = new RelatedItemsCommonPOM(page);
    const rel = new RelationshipsPOM(page);
    await common.openRelationshipsTab(CONTACT);
    await rel.openLinkDialog();

    const put = await rel.linkAsset(CONTACT, CONFIG.name);

    expect(put.status()).toBe(201);
    const row = (await put.json()).items.find((i: { asset_id: string }) => i.asset_id === CONFIG.id);
    expect(row.description).toBeNull();
    await expect(rel.groupHeading('Assets', 1)).toBeVisible();
    await expect(rel.rowLink(CONFIG.name)).toBeVisible();
  });

  test('a relationship created with a description via PUT shows that description in the tab', async ({ page }) => {
    const common = new RelatedItemsCommonPOM(page);
    const rel = new RelationshipsPOM(page);
    const description = `LEX2293 link description ${Date.now()}`;

    const created = await new RelatedItemsApi(page.request).seedLink(description);
    expect(created.description).toBe(description);

    await common.openRelationshipsTab(CONTACT);
    await expect(rel.groupHeading('Assets', 1)).toBeVisible();
    await expect(page.getByText(description, { exact: true })).toBeVisible();
  });
});
