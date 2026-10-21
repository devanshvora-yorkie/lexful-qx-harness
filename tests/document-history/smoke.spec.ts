import { test, expect } from './fixtures';
import { SEEDED_DOC, DOC_LIST_URL } from './document-history-pom';

test.describe('LEX-3371 Smoke', () => {
  test('SMOKE-01 documents listing loads with the seeded document', async ({ doc, page }) => {
    await doc.openListing();
    await expect(page).toHaveURL(new RegExp(DOC_LIST_URL.replace(/\./g, '\\.')));
    await expect(page.getByRole('heading', { name: 'Documents', level: 1 })).toBeVisible();
  });

  test('SMOKE-02 clicking a row opens the document drawer with its content', async ({ doc, page }) => {
    await doc.openListing();
    await page.getByRole('gridcell', { name: SEEDED_DOC.name, exact: true }).click();
    await expect(doc.drawerHeading(SEEDED_DOC.name)).toBeVisible({ timeout: 15000 });
    expect(page.url()).toContain('drawer=');
    await expect(doc.documentContent()).toBeVisible();
  });

  test('SMOKE-03 drawer shows the record section tabs including History', async ({ doc }) => {
    await doc.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    for (const name of ['Document', 'Relationships', 'Attachments', 'Access', 'History', 'Sources', 'System info']) {
      await expect(doc.recordSectionsTabs().getByRole('tab', { name: new RegExp(`^${name}`) })).toBeVisible();
    }
    await expect(doc.tab('Document')).toHaveAttribute('aria-selected', 'true');
  });

  test('SMOKE-04 History tab loads a timeline of entries', async ({ doc }) => {
    await doc.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await doc.openHistory();
    expect(await doc.historyEntries().count()).toBeGreaterThan(1);
    await expect(doc.filterButton('All')).toHaveAttribute('aria-pressed', 'true');
  });

  test('SMOKE-05 Download menu offers PDF, Markdown and HTML', async ({ doc }) => {
    await doc.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await doc.downloadButton().click();
    for (const label of ['PDF', 'Markdown', 'HTML'] as const) {
      await expect(doc.downloadMenuItem(label)).toBeVisible();
    }
  });
});
