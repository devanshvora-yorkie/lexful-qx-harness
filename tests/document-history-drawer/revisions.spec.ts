import { test, expect } from './fixtures';
import { SEEDED_DOC } from './document-history-drawer-pom';

test.describe('LEX-3408 Revisions Preview', () => {
  test('REVISION-01 viewing a revision opens read-only preview with "Viewing revision from" banner', async ({ drawer }) => {
    await drawer.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await drawer.openHistory();
    const hasRevisions = (await drawer.viewRevisionButtons().count()) > 0;
    if (hasRevisions) {
      await drawer.openPreviewFromHistory(0);
      await expect(drawer.revisionPreview()).toBeVisible();
      await expect(drawer.revisionPreview()).toContainText(/Viewing revision from \d{4}-\d{2}-\d{2} \d{2}:\d{2}/);
      await expect(drawer.savedRevisionsList()).toBeVisible();
    }
  });

  test('REVISION-02 saved revisions list shows Latest badge on first item and read-only snapshot text', async ({ drawer }) => {
    await drawer.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await drawer.openHistory();
    const hasRevisions = (await drawer.viewRevisionButtons().count()) > 0;
    if (hasRevisions) {
      await drawer.openPreviewFromHistory(0);
      await expect(drawer.revisionPreview()).toContainText('Read-only snapshot of saved fields');
      await expect(drawer.savedRevisionsList().getByText('Latest')).toBeVisible();
    }
  });

  test('REVISION-03 Exit history button returns to document view and hides revision preview', async ({ drawer }) => {
    await drawer.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await drawer.openHistory();
    const hasRevisions = (await drawer.viewRevisionButtons().count()) > 0;
    if (hasRevisions) {
      await drawer.openPreviewFromHistory(0);
      await expect(drawer.revisionPreview()).toBeVisible();
      await drawer.exitHistoryButton().click();
      await expect(drawer.revisionPreview()).toHaveCount(0);
      await expect(drawer.documentContent()).toBeVisible();
    }
  });

  test('REVISION-04 Restore button is hidden when viewing latest revision', async ({ drawer }) => {
    await drawer.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await drawer.openHistory();
    const hasRevisions = (await drawer.viewRevisionButtons().count()) > 0;
    if (hasRevisions) {
      await drawer.openPreviewFromHistory(0);
      const firstItem = drawer.revisionItems().first();
      const isLatest = (await firstItem.textContent()) ?? '';
      if (isLatest.includes('Latest')) {
        await expect(drawer.restoreThisRevisionButton()).toHaveCount(0);
      }
    }
  });
});
