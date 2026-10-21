import { Page, Locator, expect } from '@playwright/test';
import { CommonPOM } from '../common-pom';

export const BASE = 'https://e2e-test.uat.lexful.net';
export const DOC_LIST_URL = `${BASE}/docs/d/all/system.document`;
export const SEEDED_DOC = { id: '01a0ee77-599d-74b9-b87a-f8fe5c48b56f', name: 'Amet duis' };
export const ORG_NAME = 'Adipiscing Aliqua Academy';

export interface NewDocument {
  name: string;
  firstBody: string;
  secondBody: string;
}

export function drawerUrl(id: string): string {
  const drawer = encodeURIComponent(JSON.stringify([{ type: 'system.document', id }]));
  return `${DOC_LIST_URL}?drawer=${drawer}`;
}

export function uniqueDoc(prefix: string): NewDocument {
  const stamp = Date.now().toString(36);
  return {
    name: `PW-LEX3371-${prefix}-${stamp}`,
    firstBody: `First version body ${stamp}`,
    secondBody: `Second version body ${stamp}`,
  };
}

/**
 * POM for the document drawer: reader, editor, download menu, History tab,
 * revision preview and restore flows (LEX-3371).
 */
export class DocumentHistoryPOM extends CommonPOM {
  constructor(page: Page) {
    super(page);
  }

  // ── Navigation ──

  /** Navigate and wait for `ready`; retries with back-off to absorb sporadic CloudFront 403s. */
  async gotoUntilReady(url: string, ready: Locator, attempts = 4) {
    for (let i = 1; i <= attempts; i++) {
      try {
        await this.page.goto('about:blank');
        await this.page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15000 });
        await ready.waitFor({ state: 'visible', timeout: 15000 });
        return;
      } catch (e) {
        if (i === attempts) throw e;
        await this.page.waitForTimeout(3000 * i);
      }
    }
  }

  async openDrawerByUrl(id: string, name: string) {
    await this.gotoUntilReady(drawerUrl(id), this.drawerHeading(name));
  }

  async openListing() {
    await this.gotoUntilReady(DOC_LIST_URL, this.page.getByRole('gridcell', { name: SEEDED_DOC.name, exact: true }));
  }

  // ── Drawer shell ──

  drawer(): Locator {
    return this.page.getByRole('dialog').first();
  }

  drawerHeading(name: string): Locator {
    return this.page.getByRole('heading', { name, level: 2 });
  }

  recordSectionsTabs(): Locator {
    return this.page.getByRole('tablist', { name: 'Record sections' });
  }

  tab(name: string): Locator {
    return this.page.getByRole('tab', { name, exact: true });
  }

  moreActionsButton(): Locator {
    return this.page.getByRole('button', { name: 'More actions' });
  }

  closeButton(): Locator {
    return this.page.getByRole('button', { name: 'Close', exact: true }).first();
  }

  expandButton(): Locator {
    return this.page.getByRole('button', { name: /^(Expand|Collapse) record$/ });
  }

  // ── Reader / editor ──

  documentContent(): Locator {
    return this.page.getByRole('article', { name: 'Document content' });
  }

  editContentButton(): Locator {
    return this.page.getByRole('button', { name: 'Edit content' });
  }

  editor(): Locator {
    return this.page.getByRole('tabpanel').locator('.ProseMirror').first();
  }

  saveChangesButton(): Locator {
    return this.page.getByRole('button', { name: 'Save changes' });
  }

  cancelEditButton(): Locator {
    return this.page.getByRole('button', { name: 'Cancel', exact: true });
  }

  async replaceEditorText(text: string) {
    await this.editor().click();
    await this.page.keyboard.press('ControlOrMeta+a');
    await this.page.keyboard.type(text);
  }

  async editAndSave(text: string) {
    await this.editContentButton().click();
    await this.editor().waitFor({ state: 'visible' });
    await this.replaceEditorText(text);
    const saved = this.page.waitForResponse(
      r => r.request().method() === 'PATCH' && /\/v1\/assets\/system\.document\//.test(r.url()),
    );
    await this.saveChangesButton().click();
    const res = await saved;
    expect(res.status()).toBe(200);
  }

  // ── Download ──

  downloadButton(): Locator {
    return this.page.getByRole('button', { name: /Download document|Preparing download/ });
  }

  downloadMenuItem(label: 'PDF' | 'Markdown' | 'HTML'): Locator {
    return this.page.getByRole('menuitem', { name: new RegExp(`^${label}`) });
  }

  // ── History tab ──

  historyPanel(): Locator {
    return this.page.getByRole('tabpanel', { name: 'History' });
  }

  async openHistory() {
    const revisions = this.page.waitForResponse(
      r => /\/revisions\?limit=\d+&offset=0/.test(r.url()) && r.request().method() === 'GET',
    );
    await this.tab('History').click();
    await revisions;
    await expect(this.historyPanel()).toBeVisible();
    await expect(this.historyEntries().first()).toBeVisible({ timeout: 15000 });
  }

  historyEntries(): Locator {
    return this.historyPanel().getByRole('article');
  }

  filterButton(name: 'All' | 'People' | 'Sync'): Locator {
    return this.historyPanel().getByRole('button', { name: new RegExp(`^${name} \\d+`) });
  }

  whoViewedButton(): Locator {
    return this.historyPanel().getByRole('button', { name: /Who viewed/ });
  }

  async countOf(btn: Locator): Promise<number> {
    const text = (await btn.textContent()) ?? '';
    const m = text.match(/(\d+)\s*$/);
    return m ? Number(m[1]) : NaN;
  }

  viewRevisionButtons(): Locator {
    return this.historyPanel().getByRole('button', { name: 'View revision' });
  }

  technicalDetails(): Locator {
    return this.historyPanel().getByText('Technical details');
  }

  viewChangesSummary(): Locator {
    return this.historyPanel().getByText('Content updated · View changes');
  }

  emptyFilterMessage(): Locator {
    return this.historyPanel().getByText('No matching activity in the loaded history.');
  }

  dayHeadings(): Locator {
    return this.historyPanel().getByRole('heading', { level: 3 });
  }

  // ── Revision preview ──

  revisionPreview(): Locator {
    return this.page.getByRole('region', { name: 'Revision preview' });
  }

  savedRevisionsList(): Locator {
    return this.page.getByRole('complementary', { name: 'Saved revisions' });
  }

  revisionItems(): Locator {
    return this.savedRevisionsList().getByRole('button');
  }

  exitHistoryButton(): Locator {
    return this.page.getByRole('button', { name: 'Exit history' });
  }

  restoreThisRevisionButton(): Locator {
    return this.page.getByRole('button', { name: 'Restore this revision…' });
  }

  async openPreviewFromHistory(index: number) {
    await this.viewRevisionButtons().nth(index).click();
    await expect(this.revisionPreview()).toBeVisible({ timeout: 15000 });
  }

  // ── Restore dialog ──

  restoreDialogHeading(): Locator {
    return this.page.getByRole('heading', { name: 'Restore this record?' });
  }

  confirmRestoreButton(): Locator {
    return this.page.getByRole('button', { name: 'Restore record' });
  }

  async confirmRestore() {
    const restored = this.page.waitForResponse(
      r => r.request().method() === 'POST' && /\/revisions\/[^/]+\/restore$/.test(r.url()),
    );
    await this.confirmRestoreButton().click();
    return restored;
  }

  // ── Create / archive helpers ──

  async createDocument(doc: NewDocument): Promise<string> {
    await this.openListing();
    await this.page.getByRole('button', { name: 'New', exact: true }).click();
    await this.page.getByRole('textbox', { name: 'Name' }).fill(doc.name);
    await this.page.getByRole('dialog').getByRole('combobox').click();
    await this.page.getByRole('option', { name: ORG_NAME, exact: true }).click();
    await this.page.getByRole('dialog').locator('.ProseMirror').first().click();
    await this.page.keyboard.type(doc.firstBody);
    const created = this.page.waitForResponse(
      r => r.request().method() === 'POST' && /\/v1\/assets\/system\.document$/.test(r.url()),
    );
    await this.page.getByRole('button', { name: 'Create', exact: true }).click();
    const res = await created;
    expect(res.status()).toBe(201);
    await expect(this.drawerHeading(doc.name)).toBeVisible({ timeout: 15000 });
    const id = new URL(this.page.url()).searchParams.get('drawer');
    return JSON.parse(id!)[0].id as string;
  }

  async archiveCurrent() {
    await this.moreActionsButton().click();
    await this.page.getByRole('menuitem', { name: 'Archive…' }).click();
    const archived = this.page.waitForResponse(r => ['PATCH', 'DELETE', 'POST'].includes(r.request().method()) && /system\.document/.test(r.url()));
    await this.page.getByRole('button', { name: 'Archive asset' }).click();
    await archived;
  }
}
