import { randomUUID } from 'crypto';
import { test, expect } from '@playwright/test';
import { CONFIG, CONTACT, RelatedItemsApi, RelatedItemsCommonPOM } from './related-items-common-pom';

// AC: API contract for /v1/assets/{type}/{id}/related — payload validation (400), unknown asset (404),
// created_at/created_by on each link, and the 1000-character description limit (PATCH).
test.describe('Related items — API contract', () => {
  test.beforeEach(async ({ page }) => {
    await new RelatedItemsCommonPOM(page).authenticate();
    await new RelatedItemsApi(page.request).clear(CONTACT);
  });

  test.afterEach(async ({ page }) => {
    await new RelatedItemsApi(page.request).clear(CONTACT);
  });

  test('PUT with an empty array is rejected with 400 (at least one item required)', async ({ page }) => {
    const api = new RelatedItemsApi(page.request);

    const res = await api.put(CONTACT, []);

    expect(res.status()).toBe(400);
    expect(await api.items(CONTACT)).toEqual([]);
  });

  test('PUT with a non-uuid asset_id is rejected with 400 and creates no link', async ({ page }) => {
    const api = new RelatedItemsApi(page.request);

    const res = await api.put(CONTACT, [{ asset_id: 'not-a-uuid' }]);

    expect(res.status()).toBe(400);
    expect(await api.items(CONTACT)).toEqual([]);
  });

  test('PUT with more than 50 items is rejected with 400', async ({ page }) => {
    const api = new RelatedItemsApi(page.request);
    const body = Array.from({ length: 51 }, () => ({ asset_id: randomUUID() }));

    const res = await api.put(CONTACT, body);

    expect(res.status()).toBe(400);
    expect(await api.items(CONTACT)).toEqual([]);
  });

  test('GET related for an unknown asset id returns 404', async ({ page }) => {
    const api = new RelatedItemsApi(page.request);
    const unknown = { ...CONTACT, id: randomUUID() };

    const res = await api.get(unknown);

    expect(res.status()).toBe(404);
  });

  test('each relationship carries created_at (ISO timestamp), created_by and is_source', async ({ page }) => {
    const api = new RelatedItemsApi(page.request);

    const created = await api.seedLink();

    expect(created.created_at).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/);
    expect(Number.isNaN(Date.parse(created.created_at))).toBe(false);
    expect(created.created_by).toBeTruthy();
    expect(created.is_source).toBe(true);
    expect(created.asset_name).toBe(CONFIG.name);
  });

  test('PATCH description: 1000 characters is accepted, 1001 characters is rejected with 400', async ({ page }) => {
    const api = new RelatedItemsApi(page.request);
    const link = await api.seedLink('before');

    // Reverse side (configuration) PATCH, as observed in FEATURE.md (PATCH 200 at 1000 / 400 at 1001).
    const ok = await api.patch(CONFIG, [{ id: link.id, description: 'a'.repeat(1000) }]);
    expect(ok.status()).toBe(200);
    expect((await ok.json()).items[0].description).toHaveLength(1000);

    const tooLong = await api.patch(CONFIG, [{ id: link.id, description: 'a'.repeat(1001) }]);
    expect(tooLong.status()).toBe(400);
    expect((await tooLong.json()).error_code).toBe('VALIDATION_ERROR');
  });
});
