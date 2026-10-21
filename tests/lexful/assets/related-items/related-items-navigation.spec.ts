import { test, expect, type Response } from '@playwright/test';
import { API_BASE, CONFIG, CONTACT, RelatedItemsApi, RelatedItemsCommonPOM } from './related-items-common-pom';
import { RelationshipsPOM } from './related-items-pom';

// AC: related rows link to the related asset (stacked drawer); reverse side shows is_source true.
test.describe('Related items — navigation and bidirectional view', () => {
  test.beforeEach(async ({ page }) => {
    await new RelatedItemsCommonPOM(page).authenticate();
    await new RelatedItemsApi(page.request).clear(CONTACT);
  });

  test.afterEach(async ({ page }) => {
    await new RelatedItemsApi(page.request).clear(CONTACT);
  });

  test('clicking a related row opens the related asset as a second stacked drawer', async ({ page }) => {
    const common = new RelatedItemsCommonPOM(page);
    const rel = new RelationshipsPOM(page);
    await new RelatedItemsApi(page.request).seedLink();
    await common.openRelationshipsTab(CONTACT);

    const configDrawer = page.waitForResponse(
      (r: Response) =>
        r.request().method() === 'GET' &&
        r.url().startsWith(`${API_BASE}/v1/assets/${CONFIG.type}/${CONFIG.id}`) &&
        r.status() === 200,
    );
    await rel.rowLink(CONFIG.name).click();
    await configDrawer;

    await expect(page).toHaveURL((url) => {
      const drawers = JSON.parse(url.searchParams.get('drawer') ?? '[]') as { type: string; id: string }[];
      return (
        drawers.length === 2 &&
        drawers[0].id === CONTACT.id &&
        drawers[1].type === CONFIG.type &&
        drawers[1].id === CONFIG.id
      );
    });
  });

  test('the configuration side lists the contact with is_source true and a Contacts 1 group', async ({ page }) => {
    const common = new RelatedItemsCommonPOM(page);
    const rel = new RelationshipsPOM(page);
    await new RelatedItemsApi(page.request).seedLink();

    const reverse = await common.openRelationshipsTab(CONFIG);

    expect(reverse.status()).toBe(200);
    const items = (await reverse.json()).items as { asset_id: string; asset_name: string; is_source: boolean }[];
    expect(items).toHaveLength(1);
    expect(items[0].asset_id).toBe(CONTACT.id);
    expect(items[0].asset_name).toBe(CONTACT.name);
    expect(items[0].is_source).toBe(true);
    await expect(rel.groupHeading('Contacts', 1)).toBeVisible();
    await expect(rel.rowLink(CONTACT.name)).toBeVisible();
  });
});
