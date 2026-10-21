import { test, expect } from './fixtures';
import { SEEDED_DOC } from './document-history-pom';

test.describe('LEX-3371 Sanity', () => {
  test('SAN-01 opening History requests the revision list and audit log', async ({ doc, page }) => {
    await doc.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    const revisions = page.waitForResponse(r => /\/revisions\?limit=\d+&offset=0/.test(r.url()));
    const audit = page.waitForResponse(r => /\/v1\/audit_logs\?resource_id=/.test(r.url()));
    await doc.tab('History').click();
    expect((await revisions).status()).toBe(200);
    expect((await audit).status()).toBe(200);
  });

  test('SAN-02 revision-by-id requests made for the timeline all succeed', async ({ doc, page }) => {
    const statuses: number[] = [];
    const re = new RegExp(`/system\\.document/${SEEDED_DOC.id}/revisions/[^/?]+$`);
    page.on('response', r => { if (re.test(r.url())) statuses.push(r.status()); });
    await doc.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await doc.openHistory();
    await expect.poll(() => statuses.length, { timeout: 15000 }).toBeGreaterThan(0);
    await doc.viewRevisionButtons().first().click();
    await expect(doc.revisionPreview()).toBeVisible();
    expect(statuses.every(s => s === 200)).toBe(true);
  });

  test('SAN-03 History timestamps are real <time> elements with a title', async ({ doc }) => {
    await doc.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await doc.openHistory();
    const times = doc.historyPanel().locator('time');
    expect(await times.count()).toBeGreaterThan(0);
    await expect(times.first()).toHaveAttribute('title', /.+/);
  });

  test('SAN-04 switching Document and History tabs raises no page errors', async ({ doc, page }) => {
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await doc.openDrawerByUrl(SEEDED_DOC.id, SEEDED_DOC.name);
    await doc.openHistory();
    await doc.tab('Document').click();
    await expect(doc.documentContent()).toBeVisible();
    await doc.tab('History').click();
    await expect(doc.historyEntries().first()).toBeVisible();
    expect(errors).toEqual([]);
  });
});
