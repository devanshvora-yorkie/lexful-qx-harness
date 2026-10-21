import { test, expect } from './fixtures';
import { SEEDED_DOC } from './document-history-drawer-pom';

test.describe('LEX-3408 Smoke', () => {
  test('SMOKE-01 drawer opens with Document and History tabs visible', async ({ drawer }) => {
    await drawer.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await expect(drawer.recordSectionsTabs()).toBeVisible();
    await expect(drawer.tab('Document')).toBeVisible();
    await expect(drawer.tab('History')).toBeVisible();
  });

  test('SMOKE-02 More actions menu shows 4 main items: Restore revision, Duplicate, Print, Archive', async ({ drawer }) => {
    await drawer.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await drawer.openMoreActionsMenu();
    await expect(drawer.moreActionsMenuItem('Restore revision…')).toBeVisible();
    await expect(drawer.moreActionsMenuItem('Duplicate…')).toBeVisible();
    await expect(drawer.moreActionsMenuItem('Print')).toBeVisible();
    await expect(drawer.moreActionsMenuItem('Archive…')).toBeVisible();
  });

  test('SMOKE-03 Download menu shows PDF, Markdown, and HTML format options', async ({ drawer }) => {
    await drawer.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await drawer.downloadButton().click();
    await expect(drawer.downloadMenuItem('PDF')).toBeVisible();
    await expect(drawer.downloadMenuItem('Markdown')).toBeVisible();
    await expect(drawer.downloadMenuItem('HTML')).toBeVisible();
  });
});
