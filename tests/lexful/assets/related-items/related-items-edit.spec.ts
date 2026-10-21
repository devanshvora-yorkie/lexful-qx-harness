import { test, expect, type Request } from '@playwright/test';
import { CONTACT, RelatedItemsApi, RelatedItemsCommonPOM, relatedResponse } from './related-items-common-pom';
import { RelationshipsPOM } from './related-items-pom';

// AC: inline description edit — open editor (prefilled), save (PATCH 200 + refetch), cancel discards, 1001 chars rejected.
test.describe('Related items — describe, save, cancel, max length', () => {
  test.beforeEach(async ({ page }) => {
    await new RelatedItemsCommonPOM(page).authenticate();
    await new RelatedItemsApi(page.request).clear(CONTACT);
  });

  test.afterEach(async ({ page }) => {
    await new RelatedItemsApi(page.request).clear(CONTACT);
  });

  test('Describe relationship opens the inline editor prefilled with the current description', async ({ page }) => {
    const common = new RelatedItemsCommonPOM(page);
    const rel = new RelationshipsPOM(page);
    const prefill = `LEX2293 prefill ${Date.now()}`;
    await new RelatedItemsApi(page.request).seedLink(prefill);
    await common.openRelationshipsTab(CONTACT);

    await rel.describeButton().click();

    await expect(rel.descriptionEditor()).toHaveValue(prefill);
    await expect(rel.saveDescriptionButton()).toBeVisible();
    await expect(rel.cancelEditingButton()).toBeVisible();
  });

  test('Save description persists the new text (PATCH 200) and the tab refetches it', async ({ page }) => {
    const common = new RelatedItemsCommonPOM(page);
    const rel = new RelationshipsPOM(page);
    const api = new RelatedItemsApi(page.request);
    const ts = Date.now();
    const before = `LEX2293 before ${ts}`;
    const after = `LEX2293 after ${ts}`;
    await api.seedLink(before);
    await common.openRelationshipsTab(CONTACT);
    await rel.describeButton().click();
    await rel.descriptionEditor().fill(after);

    const refetch = page.waitForResponse(relatedResponse(CONTACT, 'GET', 200));
    const patch = await rel.saveDescription(CONTACT, 200);
    expect(patch.status()).toBe(200);
    await refetch;

    await expect(rel.descriptionEditor()).toHaveCount(0);
    await expect(page.getByText(after, { exact: true })).toBeVisible();
    const items = await api.items(CONTACT);
    expect(items[0].description).toBe(after);
  });

  test('Cancel editing discards the typed text and issues no PATCH', async ({ page }) => {
    const common = new RelatedItemsCommonPOM(page);
    const rel = new RelationshipsPOM(page);
    const api = new RelatedItemsApi(page.request);
    const before = `LEX2293 kept ${Date.now()}`;
    await api.seedLink(before);
    await common.openRelationshipsTab(CONTACT);
    await rel.describeButton().click();
    await rel.descriptionEditor().fill('LEX2293 discarded text');

    const patches: string[] = [];
    const onRequest = (req: Request) => {
      if (req.method() === 'PATCH') patches.push(req.url());
    };
    page.on('request', onRequest);

    await rel.cancelEditingButton().click();

    await expect(rel.descriptionEditor()).toHaveCount(0);
    await expect(page.getByText(before, { exact: true })).toBeVisible();
    page.off('request', onRequest);
    expect(patches).toEqual([]);
    expect((await api.items(CONTACT))[0].description).toBe(before);
  });

  test('a 1001-character description is rejected by Save description (PATCH 400) and not stored', async ({ page }) => {
    const common = new RelatedItemsCommonPOM(page);
    const rel = new RelationshipsPOM(page);
    const api = new RelatedItemsApi(page.request);
    const before = `LEX2293 stored ${Date.now()}`;
    await api.seedLink(before);
    await common.openRelationshipsTab(CONTACT);
    await rel.describeButton().click();
    const tooLong = 'x'.repeat(1001);
    await rel.descriptionEditor().fill(tooLong);

    const rejected = page.waitForResponse(relatedResponse(CONTACT, 'PATCH', 400));
    await rel.saveDescriptionButton().click();
    const response = await rejected;

    expect(response.status()).toBe(400);
    expect((await response.json()).error_code).toBe('VALIDATION_ERROR');
    await expect(rel.descriptionEditor()).toHaveValue(tooLong);
    expect((await api.items(CONTACT))[0].description).toBe(before);
  });
});
