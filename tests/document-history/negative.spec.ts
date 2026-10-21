import { test, expect } from './fixtures';
import { SEEDED_DOC, drawerUrl } from './document-history-pom';

test.describe('LEX-3371 Negative', () => {
  test('NEG-01 cancelling the restore dialog sends no restore request', async ({ doc, page }) => {
    const restoreCalls: string[] = [];
    page.on('request', r => { if (/\/restore$/.test(r.url())) restoreCalls.push(r.url()); });
    await doc.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await doc.openHistory();
    await doc.openPreviewFromHistory(1);
    await doc.restoreThisRevisionButton().click();
    await expect(doc.restoreDialogHeading()).toBeVisible();
    await page.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(doc.restoreDialogHeading()).toHaveCount(0);
    expect(restoreCalls).toHaveLength(0);
  });

  test('NEG-02 dismissing the restore dialog with Escape sends no restore request', async ({ doc, page }) => {
    const restoreCalls: string[] = [];
    page.on('request', r => { if (/\/restore$/.test(r.url())) restoreCalls.push(r.url()); });
    await doc.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await doc.openHistory();
    await doc.openPreviewFromHistory(1);
    await doc.restoreThisRevisionButton().click();
    await expect(doc.restoreDialogHeading()).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(doc.restoreDialogHeading()).toHaveCount(0);
    expect(restoreCalls).toHaveLength(0);
  });

  test('NEG-03 the latest revision cannot be restored', async ({ doc }) => {
    await doc.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await doc.openHistory();
    await doc.openPreviewFromHistory(0);
    await expect(doc.revisionItems().first()).toContainText('Latest');
    await expect(doc.restoreThisRevisionButton()).toHaveCount(0);
  });

  test('NEG-04 Download is disabled while the document is being edited', async ({ doc }) => {
    await doc.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await doc.editContentButton().click();
    await expect(doc.editor()).toBeVisible();
    await expect(doc.downloadButton()).toBeDisabled();
    await doc.cancelEditButton().click();
    await expect(doc.downloadButton()).toBeEnabled();
  });

  test('NEG-05 Save changes is disabled until the content is modified', async ({ doc }) => {
    await doc.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await doc.editContentButton().click();
    await expect(doc.editor()).toBeVisible();
    await expect(doc.saveChangesButton()).toBeDisabled();
    await doc.cancelEditButton().click();
  });

  test('NEG-06 cancelling an edit without saving sends no update', async ({ doc, page }) => {
    const patches: string[] = [];
    page.on('request', r => { if (r.method() === 'PATCH') patches.push(r.url()); });
    await doc.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await doc.editContentButton().click();
    await doc.cancelEditButton().click();
    await expect(doc.editContentButton()).toBeVisible();
    expect(patches).toHaveLength(0);
  });

  test('NEG-07 Sync filter shows the empty-state message when there is no sync activity', async ({ doc }) => {
    await doc.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await doc.openHistory();
    expect(await doc.countOf(doc.filterButton('Sync'))).toBe(0);
    await doc.filterButton('Sync').click();
    await expect(doc.emptyFilterMessage()).toBeVisible();
    await expect(doc.historyEntries()).toHaveCount(0);
  });

  test('NEG-08 opening a non-existent document shows an unavailable alert and disabled tabs', async ({ doc, page }) => {
    await doc.gotoUntilReady(drawerUrl('00000000-0000-7000-8000-000000000000'), page.getByRole('alert').filter({ hasText: 'This record is unavailable or you do not have access.' }));
    await expect(doc.tab('History')).toBeDisabled();
    await expect(doc.tab('Document')).toBeDisabled();
    await expect(doc.documentContent()).toHaveCount(0);
  });
});
