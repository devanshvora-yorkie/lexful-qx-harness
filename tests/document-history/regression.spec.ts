import { test, expect } from './fixtures';
import { DocumentHistoryPOM, uniqueDoc } from './document-history-pom';
import { injectAuthCookies } from '../../auth-helper';
import * as fs from 'fs';
import { Page, BrowserContext } from '@playwright/test';

const data = uniqueDoc('reg');

test.describe.serial('LEX-3371 Regression — create → edit → history → restore', () => {
  let ctx: BrowserContext;
  let page: Page;
  let doc: DocumentHistoryPOM;
  let id = '';

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(90000);
    ctx = await browser.newContext();
    await injectAuthCookies(ctx);
    page = await ctx.newPage();
    doc = new DocumentHistoryPOM(page);
    id = await doc.createDocument(data);
  });

  test.afterAll(async () => {
    test.setTimeout(90000);
    try {
      await doc.openDrawerByUrl(id, data.name);
      await doc.archiveCurrent();
    } catch { /* best-effort cleanup */ }
    await ctx.close();
  });

  test('REG-01 new document has History entries attributed to the creator', async () => {
    await doc.openHistory();
    await expect(doc.historyEntries().first()).toContainText('Admin E2E-Test');
  });

  test('REG-02 saving an edit updates the reader content', async () => {
    await doc.tab('Document').click();
    await doc.editAndSave(data.secondBody);
    await expect(doc.documentContent()).toContainText(data.secondBody);
  });

  test('REG-03 the edit appears in History with a content diff', async () => {
    await doc.openHistory();
    const entry = doc.historyEntries().filter({ hasText: 'edited the record' }).first();
    await expect(entry).toContainText('Content');
    await doc.viewChangesSummary().first().click();
    await expect(doc.historyPanel().getByLabel('Removed passage')).toBeVisible();
    await expect(doc.historyPanel().getByLabel('Added passage')).toBeVisible();
  });

  test('REG-04 View full versions shows Before and After content', async () => {
    await doc.historyPanel().getByText('View full versions').first().click();
    await expect(doc.historyPanel().getByLabel('Before content')).toContainText(data.firstBody);
    await expect(doc.historyPanel().getByLabel('After content')).toContainText(data.secondBody);
  });

  test('REG-05 the first revision previews the original body and is restorable', async () => {
    await doc.viewRevisionButtons().last().click();
    await expect(doc.revisionPreview()).toBeVisible();
    await expect(doc.documentContent()).toContainText(data.firstBody);
    await expect(doc.restoreThisRevisionButton()).toBeVisible();
  });

  test('REG-06 restore dialog explains a new revision is created', async () => {
    await doc.restoreThisRevisionButton().click();
    await expect(doc.restoreDialogHeading()).toBeVisible();
    await expect(page.getByText(/creates a new revision and preserves the existing history/)).toBeVisible();
    await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  });

  test('REG-07 confirming restore returns the original content', async () => {
    await doc.restoreThisRevisionButton().click();
    const res = await doc.confirmRestore();
    expect(res.status()).toBe(200);
    await expect(doc.documentContent()).toContainText(data.firstBody, { timeout: 15000 });
    await expect(doc.documentContent()).not.toContainText(data.secondBody);
  });

  test('REG-08 restore preserves history and adds a new revision', async () => {
    await doc.openHistory();
    expect(await doc.viewRevisionButtons().count()).toBeGreaterThanOrEqual(3);
    await expect(doc.historyEntries().filter({ hasText: 'created the record' })).toHaveCount(1);
  });

  test('REG-09 More actions → Restore revision opens the revision picker', async () => {
    await doc.openDrawerByUrl(id, data.name);
    await doc.moreActionsButton().click();
    await page.getByRole('menuitem', { name: 'Restore revision…' }).click();
    await expect(page.getByRole('heading', { name: 'Restore revision', level: 3 })).toBeVisible();
    await expect(page.getByLabel('Current version')).toBeVisible();
    await expect(page.getByRole('button', { name: /Previous revision|Saved revision/ }).first()).toBeVisible();
    await page.keyboard.press('Escape');
  });

  test('REG-10 picking a revision from the picker opens its read-only preview', async () => {
    await doc.openDrawerByUrl(id, data.name);
    await doc.moreActionsButton().click();
    await page.getByRole('menuitem', { name: 'Restore revision…' }).click();
    await page.getByRole('button', { name: /Previous revision|Saved revision/ }).first().click();
    await expect(doc.revisionPreview()).toBeVisible();
    await expect(doc.restoreThisRevisionButton()).toBeVisible();
    await doc.exitHistoryButton().click();
    await expect(doc.revisionPreview()).toHaveCount(0);
  });

  test('REG-11 Markdown download contains the document text', async () => {
    await doc.tab('Document').click();
    await doc.downloadButton().click();
    const [download] = await Promise.all([page.waitForEvent('download'), doc.downloadMenuItem('Markdown').click()]);
    const text = fs.readFileSync((await download.path())!, 'utf-8');
    expect(text).toContain(data.firstBody);
  });

  test('REG-12 HTML download contains the document text', async () => {
    await doc.downloadButton().click();
    const [download] = await Promise.all([page.waitForEvent('download'), doc.downloadMenuItem('HTML').click()]);
    const text = fs.readFileSync((await download.path())!, 'utf-8');
    expect(text).toContain(data.firstBody);
    expect(text.toLowerCase()).toContain('<html');
  });
});
