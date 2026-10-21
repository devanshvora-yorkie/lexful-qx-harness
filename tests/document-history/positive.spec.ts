import { test, expect } from './fixtures';
import { SEEDED_DOC } from './document-history-pom';

test.describe('LEX-3371 Positive', () => {
  test.beforeEach(async ({ doc }) => {
    await doc.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
  });

  test('POS-01 reader renders rich content: links, list, code and table', async ({ doc }) => {
    const content = doc.documentContent();
    await expect(content.getByRole('link', { name: 'Amet Anim Vendor' })).toBeVisible();
    await expect(content.getByRole('list').first()).toBeVisible();
    await expect(content.locator('code').first()).toBeVisible();
    await expect(content.getByRole('table')).toBeVisible();
    await expect(content.getByRole('columnheader', { name: 'Qty' })).toBeVisible();
  });

  test('POS-02 reader shows a floating Edit button for editable documents', async ({ doc }) => {
    await expect(doc.editContentButton()).toBeEnabled();
  });

  test('POS-03 timeline entries show actor, action and time', async ({ doc }) => {
    await doc.openHistory();
    const first = doc.historyEntries().first();
    await expect(first.locator('strong')).not.toBeEmpty();
    await expect(first).toContainText(/(created|edited|updated) the record/);
    await expect(first.locator('time')).toHaveAttribute('datetime', /\d{4}-\d{2}-\d{2}T/);
  });

  test('POS-04 entries are grouped under a day heading', async ({ doc }) => {
    await doc.openHistory();
    expect(await doc.dayHeadings().count()).toBeGreaterThanOrEqual(1);
    await expect(doc.dayHeadings().first()).toContainText(/\d{4}/);
  });

  test('POS-05 field changes render as before → after diffs', async ({ doc }) => {
    await doc.openHistory();
    const expiresDiff = doc.historyPanel().getByRole('term').filter({ hasText: 'Expires On' }).first();
    await expect(expiresDiff).toBeVisible();
    const definition = doc.historyPanel().getByRole('definition').filter({ has: doc.page.locator('del') }).first();
    await expect(definition.locator('del')).toBeVisible();
    await expect(definition.locator('ins')).toBeVisible();
    await expect(definition).toContainText('→');
  });

  test('POS-06 Technical details reveal Revision ID and Record ID', async ({ doc }) => {
    await doc.openHistory();
    const revisionEntry = doc.historyEntries().filter({ has: doc.page.getByRole('button', { name: 'View revision' }) }).first();
    await revisionEntry.getByText('Technical details').click();
    await expect(revisionEntry.getByRole('term').filter({ hasText: 'Revision ID' })).toBeVisible();
    await expect(revisionEntry.getByRole('definition').filter({ hasText: SEEDED_DOC.id })).toBeVisible();
  });

  test('POS-07 People filter narrows the timeline to person-made entries', async ({ doc }) => {
    await doc.openHistory();
    const all = await doc.countOf(doc.filterButton('All'));
    const people = await doc.countOf(doc.filterButton('People'));
    expect(people).toBeLessThanOrEqual(all);
    await doc.filterButton('People').click();
    await expect(doc.filterButton('People')).toHaveAttribute('aria-pressed', 'true');
    await expect(doc.historyEntries()).toHaveCount(people);
  });

  test('POS-08 Who viewed reveals access entries', async ({ doc }) => {
    await doc.openHistory();
    await expect(doc.historyPanel().getByText('viewed the record')).toHaveCount(0);
    await doc.whoViewedButton().click();
    await expect(doc.whoViewedButton()).toHaveAttribute('aria-pressed', 'true');
    await expect(doc.historyPanel().getByText('viewed the record').first()).toBeVisible();
  });

  test('POS-09 View revision opens a read-only preview with the saved revisions list', async ({ doc }) => {
    await doc.openHistory();
    await doc.openPreviewFromHistory(0);
    await expect(doc.revisionPreview()).toContainText(/Viewing revision from \d{4}-\d{2}-\d{2} \d{2}:\d{2}/);
    await expect(doc.revisionPreview()).toContainText('Read-only snapshot of saved fields');
    await expect(doc.savedRevisionsList()).toContainText(/\d+ revisions?/);
    await expect(doc.savedRevisionsList().getByText('Latest')).toBeVisible();
  });

  test('POS-10 choosing another revision updates the preview banner', async ({ doc }) => {
    await doc.openHistory();
    await doc.openPreviewFromHistory(0);
    const items = doc.revisionItems();
    expect(await items.count()).toBeGreaterThan(2);
    const target = items.nth(2);
    const label = ((await target.locator('div').first().textContent()) ?? '').trim();
    await target.click();
    await expect(target).toHaveAttribute('aria-pressed', 'true');
    await expect(doc.revisionPreview()).toContainText(`Viewing revision from ${label}`);
  });

  test('POS-11 Exit history returns to the document view', async ({ doc }) => {
    await doc.openHistory();
    await doc.openPreviewFromHistory(0);
    await doc.exitHistoryButton().click();
    await expect(doc.revisionPreview()).toHaveCount(0);
    await expect(doc.documentContent()).toBeVisible();
    await expect(doc.drawerHeading(SEEDED_DOC.name)).toBeVisible();
  });

  test('POS-12 Markdown download produces a .md file', async ({ doc, page }) => {
    await doc.downloadButton().click();
    const [download] = await Promise.all([page.waitForEvent('download'), doc.downloadMenuItem('Markdown').click()]);
    expect(download.suggestedFilename()).toMatch(/\.md$/);
  });

  test('POS-13 HTML download produces a .html file', async ({ doc, page }) => {
    await doc.downloadButton().click();
    const [download] = await Promise.all([page.waitForEvent('download'), doc.downloadMenuItem('HTML').click()]);
    expect(download.suggestedFilename()).toMatch(/\.html$/);
  });
});
