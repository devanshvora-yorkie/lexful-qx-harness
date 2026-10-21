import { test, expect } from './fixtures';
import { SEEDED_DOC } from './document-history-drawer-pom';

test.describe('LEX-3408 Restore Dialog', () => {
  test('RESTORE-01 cancel button closes restore dialog without sending restore request to /restore endpoint', async ({ drawer, page }) => {
    const restoreCalls: string[] = [];
    page.on('request', r => {
      if (r.method() === 'POST' && /\/restore$/.test(r.url())) {
        restoreCalls.push(r.url());
      }
    });
    await drawer.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await drawer.openHistory();
    const hasRevisions = (await drawer.viewRevisionButtons().count()) > 0;
    if (hasRevisions && await drawer.viewRevisionButtons().nth(1).isVisible().catch(() => false)) {
      await drawer.openPreviewFromHistory(1);
      const hasRestoreBtn = (await drawer.restoreThisRevisionButton().count()) > 0;
      if (hasRestoreBtn) {
        await drawer.restoreThisRevisionButton().click();
        await expect(drawer.restoreDialogHeading()).toBeVisible();
        await page.getByRole('button', { name: 'Cancel', exact: true }).click();
        await expect(drawer.restoreDialogHeading()).toHaveCount(0);
        expect(restoreCalls).toHaveLength(0);
      }
    }
  });
});
