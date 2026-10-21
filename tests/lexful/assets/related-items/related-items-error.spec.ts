import { test, expect, type Route } from '@playwright/test';
import { CONFIG, CONTACT, RelatedItemsApi, RelatedItemsCommonPOM, relatedResponse, relatedUrl } from './related-items-common-pom';
import { RelationshipsPOM } from './related-items-pom';

// AC: when the related GET fails, the tab shows the error text "Could not load relationships.".
test.describe('Related items — error state', () => {
  test.beforeEach(async ({ page }) => {
    await new RelatedItemsCommonPOM(page).authenticate();
    await new RelatedItemsApi(page.request).clear(CONTACT);
  });

  test.afterEach(async ({ page }) => {
    await new RelatedItemsApi(page.request).clear(CONTACT);
  });

  test('a 500 from the related GET shows "Could not load relationships."', async ({ page }) => {
    const common = new RelatedItemsCommonPOM(page);
    const rel = new RelationshipsPOM(page);
    const configRelatedUrl = relatedUrl(CONFIG);

    // Route-mock the reverse-side GET only (FEATURE.md section 2, route-mocked row).
    await page.route(
      (url) => url.toString() === configRelatedUrl,
      async (route: Route) => {
        if (route.request().method() !== 'GET') return route.fallback();
        return route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ status: 500, message: 'boom' }),
        });
      },
    );

    await common.gotoDrawer(CONFIG);
    const tab = common.relationshipsTab();
    await tab.waitFor({ state: 'visible', timeout: 15000 });
    const [failed] = await Promise.all([
      page.waitForResponse(relatedResponse(CONFIG, 'GET', 500)),
      tab.click(),
    ]);

    expect(failed.status()).toBe(500);
    await expect(rel.errorText()).toBeVisible();
    await expect(rel.groupHeading('Contacts', 0)).toBeVisible();

    await page.unroute((url) => url.toString() === configRelatedUrl);
  });
});
