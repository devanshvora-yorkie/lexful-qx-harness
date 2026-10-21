import { test, expect } from './fixtures';
import { SEEDED_DOC } from './document-history-pom';

test.describe('LEX-3371 Edge cases', () => {
  test.beforeEach(async ({ doc }) => {
    await doc.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await doc.openHistory();
  });

  test('EDGE-01 All count equals the number of rendered entries', async ({ doc }) => {
    const all = await doc.countOf(doc.filterButton('All'));
    await expect(doc.historyEntries()).toHaveCount(all);
  });

  test('EDGE-02 Who viewed adds access entries and updates the All count', async ({ doc }) => {
    const before = await doc.countOf(doc.filterButton('All'));
    await doc.whoViewedButton().click();
    await expect.poll(() => doc.countOf(doc.filterButton('All'))).toBeGreaterThan(before);
    const after = await doc.countOf(doc.filterButton('All'));
    await expect(doc.historyEntries()).toHaveCount(after);
  });

  test('EDGE-03 toggling Who viewed off restores the original entry count', async ({ doc }) => {
    const before = await doc.countOf(doc.filterButton('All'));
    await doc.whoViewedButton().click();
    await doc.whoViewedButton().click();
    await expect(doc.whoViewedButton()).toHaveAttribute('aria-pressed', 'false');
    await expect(doc.historyEntries()).toHaveCount(before);
  });

  test('EDGE-04 switching Sync → All restores the full timeline', async ({ doc }) => {
    const all = await doc.countOf(doc.filterButton('All'));
    await doc.filterButton('Sync').click();
    await expect(doc.emptyFilterMessage()).toBeVisible();
    await doc.filterButton('All').click();
    await expect(doc.emptyFilterMessage()).toHaveCount(0);
    await expect(doc.historyEntries()).toHaveCount(all);
  });

  test('EDGE-05 rapid filter switching ends in a consistent state', async ({ doc }) => {
    const all = await doc.countOf(doc.filterButton('All'));
    for (let i = 0; i < 3; i++) {
      await doc.filterButton('People').click();
      await doc.filterButton('Sync').click();
      await doc.filterButton('All').click();
    }
    await expect(doc.filterButton('All')).toHaveAttribute('aria-pressed', 'true');
    await expect(doc.filterButton('People')).toHaveAttribute('aria-pressed', 'false');
    await expect(doc.historyEntries()).toHaveCount(all);
  });

  test('EDGE-06 oldest revision still previews its content and is restorable', async ({ doc }) => {
    await doc.viewRevisionButtons().last().click();
    await expect(doc.revisionPreview()).toBeVisible();
    const items = doc.revisionItems();
    await items.last().click();
    await expect(items.last()).toHaveAttribute('aria-pressed', 'true');
    await expect(doc.documentContent()).toBeVisible();
    await expect(doc.restoreThisRevisionButton()).toBeVisible();
  });

  test('EDGE-07 revision count label matches the number of listed revisions', async ({ doc }) => {
    await doc.openPreviewFromHistory(0);
    const label = (await doc.savedRevisionsList().locator('p').first().textContent()) ?? '';
    const n = Number(label.match(/(\d+) revisions?/)?.[1]);
    expect(n).toBeGreaterThan(0);
    await expect(doc.revisionItems()).toHaveCount(n);
  });

  test('EDGE-08 revision preview disables More actions and keeps the heading', async ({ doc }) => {
    await doc.openPreviewFromHistory(0);
    await expect(doc.moreActionsButton()).toBeDisabled();
    await expect(doc.drawerHeading(SEEDED_DOC.name)).toBeVisible();
  });

  test('EDGE-09 expand and collapse record toggles the drawer control', async ({ doc, page }) => {
    await page.getByRole('button', { name: 'Expand record' }).click();
    await expect(page.getByRole('button', { name: 'Collapse record' })).toBeVisible();
    await page.getByRole('button', { name: 'Collapse record' }).click();
    await expect(page.getByRole('button', { name: 'Expand record' })).toBeVisible();
  });

  test('EDGE-10 browser back closes the drawer opened from the listing', async ({ doc, page }) => {
    await doc.openListing();
    await page.getByRole('gridcell', { name: SEEDED_DOC.name, exact: true }).click();
    await expect(doc.drawerHeading(SEEDED_DOC.name)).toBeVisible();
    await page.goBack();
    await expect(page).not.toHaveURL(/drawer=/);
    await expect(doc.drawerHeading(SEEDED_DOC.name)).toHaveCount(0);
  });
});
