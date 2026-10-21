import { test, expect } from './fixtures';
import { SEEDED_DOC } from './document-history-drawer-pom';

test.describe('LEX-3408 Lex Integration', () => {
  test('LEX-01 Lex button is visible in read mode next to Download button', async ({ drawer }) => {
    await drawer.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    const lexBtn = drawer.lexButton();
    await expect(lexBtn).toBeVisible();
  });

  test('LEX-02 entering edit mode keeps Lex visible in toolbar or header', async ({ drawer }) => {
    await drawer.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await drawer.editContentButton().click();
    await expect(drawer.editor()).toBeVisible();
    const lexBtn = drawer.lexButton();
    await expect(lexBtn).toBeVisible({ timeout: 5000 });
  });

  test('LEX-03 Lex button is enabled and clickable when text is selected in editor', async ({ drawer, page }) => {
    await drawer.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await drawer.editContentButton().click();
    const editor = drawer.editor();
    await editor.click();
    await page.keyboard.press('ControlOrMeta+a');
    const lexBtn = drawer.lexButton();
    await expect(lexBtn).toBeVisible();
    await expect(lexBtn).toBeEnabled();
  });
});
