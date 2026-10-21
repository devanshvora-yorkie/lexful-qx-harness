import { test, expect, type Request } from '@playwright/test';
import { CONFIG, CONTACT, RelatedItemsApi, RelatedItemsCommonPOM } from './related-items-common-pom';
import { RelationshipsPOM } from './related-items-pom';

// AC: removing a link asks for confirmation ("Remove related item?"), Cancel keeps it, confirm deletes (DELETE 204).
test.describe('Related items — remove with confirmation', () => {
  test.beforeEach(async ({ page }) => {
    await new RelatedItemsCommonPOM(page).authenticate();
    await new RelatedItemsApi(page.request).clear(CONTACT);
  });

  test.afterEach(async ({ page }) => {
    await new RelatedItemsApi(page.request).clear(CONTACT);
  });

  test('Remove opens the confirm dialog with the link explanation and Cancel / Remove buttons', async ({ page }) => {
    const common = new RelatedItemsCommonPOM(page);
    const rel = new RelationshipsPOM(page);
    await new RelatedItemsApi(page.request).seedLink();
    await common.openRelationshipsTab(CONTACT);

    await rel.rowRemoveButton().click();

    await expect(rel.removeConfirmDialog()).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Remove related item?', exact: true })).toBeVisible();
    await expect(rel.removeConfirmText(CONFIG.name)).toBeVisible();
    await expect(rel.removeConfirmCancel()).toBeVisible();
    await expect(rel.removeConfirmRemove()).toBeVisible();
  });

  test('Cancel in the confirm dialog keeps the link and issues no DELETE', async ({ page }) => {
    const common = new RelatedItemsCommonPOM(page);
    const rel = new RelationshipsPOM(page);
    const api = new RelatedItemsApi(page.request);
    await api.seedLink();
    await common.openRelationshipsTab(CONTACT);
    await rel.rowRemoveButton().click();
    await expect(rel.removeConfirmDialog()).toBeVisible();

    const deletes: string[] = [];
    const onRequest = (req: Request) => {
      if (req.method() === 'DELETE') deletes.push(req.url());
    };
    page.on('request', onRequest);

    await rel.removeConfirmCancel().click();

    await expect(rel.removeConfirmDialog()).toHaveCount(0);
    await expect(rel.rowLink(CONFIG.name)).toBeVisible();
    page.off('request', onRequest);
    expect(deletes).toEqual([]);
    expect(await api.items(CONTACT)).toHaveLength(1);
  });

  test('confirming Remove deletes the link (DELETE 204) and the group count returns to zero', async ({ page }) => {
    const common = new RelatedItemsCommonPOM(page);
    const rel = new RelationshipsPOM(page);
    const api = new RelatedItemsApi(page.request);
    await api.seedLink();
    await common.openRelationshipsTab(CONTACT);
    await rel.rowRemoveButton().click();
    await expect(rel.removeConfirmDialog()).toBeVisible();

    const deleted = await rel.confirmRemove(CONTACT);

    expect(deleted.status()).toBe(204);
    await expect(rel.rowLink(CONFIG.name)).toHaveCount(0);
    await expect(rel.groupHeading('Assets', 0)).toBeVisible();
    expect(await api.items(CONTACT)).toEqual([]);
  });

  test('API DELETE removes the link and a follow-up GET no longer lists it', async ({ page }) => {
    const api = new RelatedItemsApi(page.request);
    const link = await api.seedLink();
    expect(await api.items(CONTACT)).toHaveLength(1);

    const res = await api.del(CONTACT, [link.id]);

    expect(res.status()).toBe(204);
    const remaining = await api.items(CONTACT);
    expect(remaining.find((i) => i.id === link.id)).toBeUndefined();
    expect(remaining).toEqual([]);
  });
});
