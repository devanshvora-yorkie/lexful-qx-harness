import { test, expect, type Route } from '@playwright/test';
import { CONFIG, CONTACT, RelatedItemsApi, RelatedItemsCommonPOM, relatedResponse, relatedUrl } from './related-items-common-pom';
import { RelationshipsPOM } from './related-items-pom';

// AC: GET related loads the Relationships tab; empty state; skeleton while loading; type badges.
test.describe('Related items — view, empty state, loading', () => {
  test.beforeEach(async ({ page }) => {
    await new RelatedItemsCommonPOM(page).authenticate();
    await new RelatedItemsApi(page.request).clear(CONTACT);
  });

  test.afterEach(async ({ page }) => {
    await new RelatedItemsApi(page.request).clear(CONTACT);
  });

  test('opening the contact Relationships tab loads related items with GET 200', async ({ page }) => {
    const common = new RelatedItemsCommonPOM(page);
    const rel = new RelationshipsPOM(page);

    const response = await common.openRelationshipsTab(CONTACT);

    expect(response.status()).toBe(200);
    expect((await response.json()).items).toEqual([]);
    await expect(rel.groupHeading('Assets', 0)).toBeVisible();
  });

  test('empty relationships show zero counts for every group and no error', async ({ page }) => {
    const common = new RelatedItemsCommonPOM(page);
    const rel = new RelationshipsPOM(page);

    await common.openRelationshipsTab(CONTACT);

    for (const label of ['Assets', 'Contacts', 'Documents', 'Passwords'] as const) {
      await expect(rel.groupHeading(label, 0)).toBeVisible();
    }
    await expect(rel.errorText()).toHaveCount(0);
    await expect(rel.rowLink(CONFIG.name)).toHaveCount(0);
  });

  test('skeleton is shown while the related GET is pending, then the loaded state replaces it', async ({ page }) => {
    const common = new RelatedItemsCommonPOM(page);
    const rel = new RelationshipsPOM(page);

    // Hold the GET open until the test has asserted the skeleton. No timers.
    let releaseGet!: () => void;
    const gate = new Promise<void>((resolve) => {
      releaseGet = resolve;
    });
    await page.route(
      (url) => url.toString() === relatedUrl(CONTACT),
      async (route: Route) => {
        if (route.request().method() !== 'GET') return route.fallback();
        await gate;
        return route.continue();
      },
    );

    await common.gotoDrawer(CONTACT);
    const tab = common.relationshipsTab();
    await tab.waitFor({ state: 'visible', timeout: 15000 });
    await tab.click();

    await expect(rel.skeleton().first()).toBeVisible();

    const loaded = page.waitForResponse(relatedResponse(CONTACT, 'GET', 200));
    releaseGet();
    await loaded;

    await expect(rel.groupHeading('Assets', 0)).toBeVisible();
    await expect(rel.skeleton()).toHaveCount(0);
    await page.unroute((url) => url.toString() === relatedUrl(CONTACT));
  });

  test('a linked asset row shows its asset type badge under the Assets group', async ({ page }) => {
    const common = new RelatedItemsCommonPOM(page);
    const rel = new RelationshipsPOM(page);
    await new RelatedItemsApi(page.request).seedLink();

    await common.openRelationshipsTab(CONTACT);

    await expect(rel.groupHeading('Assets', 1)).toBeVisible();
    await expect(rel.typeBadge('Configurations')).toBeVisible();
    await expect(rel.rowLink(CONFIG.name)).toBeVisible();
  });
});
