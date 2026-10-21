import { test, expect } from './fixtures';
import { SEEDED_DOC } from './document-history-drawer-pom';

test.describe('LEX-3408 Edit Mode', () => {
  test('EDIT-01 Edit button opens ProseMirror editor and Save button is initially disabled', async ({ drawer }) => {
    await drawer.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await expect(drawer.editContentButton()).toBeEnabled();
    await drawer.editContentButton().click();
    await expect(drawer.editor()).toBeVisible();
    await expect(drawer.saveChangesButton()).toBeDisabled();
  });

  test('EDIT-02 Download button is disabled while in edit mode', async ({ drawer }) => {
    await drawer.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await expect(drawer.downloadButton()).toBeEnabled();
    await drawer.editContentButton().click();
    await expect(drawer.downloadButton()).toBeDisabled();
  });

  test('EDIT-03 cancelling edit without changes sends no PATCH request and re-enables Download', async ({ drawer, page }) => {
    const patchCalls: string[] = [];
    page.on('request', r => {
      if (r.method() === 'PATCH' && /\/v1\/assets\/system\.document/.test(r.url())) {
        patchCalls.push(r.url());
      }
    });
    await drawer.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await drawer.editContentButton().click();
    await expect(drawer.downloadButton()).toBeDisabled();
    await drawer.cancelEditButton().click();
    await expect(drawer.downloadButton()).toBeEnabled();
    expect(patchCalls).toHaveLength(0);
  });
});
