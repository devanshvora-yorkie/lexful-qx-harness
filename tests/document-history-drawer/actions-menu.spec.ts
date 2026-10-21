import { test, expect } from './fixtures';
import { SEEDED_DOC } from './document-history-drawer-pom';

test.describe('LEX-3408 Actions Menu', () => {
  test('ACTIONS-01 Archive menu item opens a confirmation dialog and can be cancelled', async ({ drawer, page }) => {
    await drawer.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await drawer.openMoreActionsMenu();
    await drawer.archiveMenuItem().click();
    const confirmBtn = page.getByRole('button', { name: /Archive asset|Archive record/ });
    await expect(confirmBtn).toBeVisible({ timeout: 5000 });
    await page.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(confirmBtn).toHaveCount(0);
  });
});
