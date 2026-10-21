import { expect, type Page, type Response } from '@playwright/test';
import { RelatedItemsCommonPOM, relatedResponse, type AssetRef, type GroupLabel } from './related-items-common-pom';

/**
 * Module POM for the drawer "Relationships" tab (LEX-2293).
 * Labels are the observed UI labels from FEATURE.md, not the PR text ("Related", "Add", "Remove related item" icons).
 */
export class RelationshipsPOM {
  readonly common: RelatedItemsCommonPOM;

  constructor(readonly page: Page) {
    this.common = new RelatedItemsCommonPOM(page);
  }

  // ── Tab and groups ──

  relationshipsTab() {
    return this.common.relationshipsTab();
  }

  /** Group heading such as "Assets 0" or "Contacts 1". */
  groupHeading(label: GroupLabel, count: number) {
    return this.page.getByRole('heading', { name: new RegExp(`^${label} ${count}$`) });
  }

  /** Loading placeholder shown inside the active tab panel while the GET is pending. */
  skeleton() {
    return this.page.getByRole('tabpanel').locator('[data-slot="skeleton"], .animate-pulse');
  }

  errorText() {
    return this.page.getByText('Could not load relationships.', { exact: true });
  }

  /** Asset type badge text in a row, e.g. "Configurations". */
  typeBadge(text: string) {
    return this.page.getByText(text, { exact: true });
  }

  /** Row name link. Clicking it opens the related asset in a stacked drawer. */
  rowLink(name: string) {
    return this.page.getByRole('link', { name, exact: true });
  }

  // ── Link assets dialog ──

  linkAssetsButton() {
    return this.page.getByRole('button', { name: 'Link assets', exact: true });
  }

  searchInput() {
    return this.page.getByRole('textbox', { name: 'Search records to link', exact: true });
  }

  linkDialog() {
    return this.page.getByRole('dialog').filter({ has: this.searchInput() });
  }

  organizationCombobox() {
    return this.page.getByRole('combobox', { name: /Organization/ });
  }

  recordTypeCombobox() {
    return this.page.getByRole('combobox', { name: /Record type/ });
  }

  /** A result in the dialog. Clicking it links the asset immediately (no Add button). */
  resultButton(name: string) {
    return this.page.getByRole('button', { name: `Link ${name}`, exact: true });
  }

  async openLinkDialog(): Promise<void> {
    await this.linkAssetsButton().click();
    await expect(this.linkDialog()).toBeVisible();
  }

  /** Clicks a result and waits for the PUT 201 that creates the link. */
  async linkAsset(owner: AssetRef, name: string): Promise<Response> {
    await expect(this.resultButton(name)).toBeVisible();
    const [response] = await Promise.all([
      this.page.waitForResponse(relatedResponse(owner, 'PUT', 201)),
      this.resultButton(name).click(),
    ]);
    return response;
  }

  // ── Row actions: describe / edit description ──

  /** "Describe relationship with <name>" or "Describe relationship…" when empty. */
  describeButton() {
    return this.page.getByRole('button', { name: /^Describe relationship/ });
  }

  descriptionEditor() {
    return this.page.getByRole('textbox', { name: 'Relationship description', exact: true });
  }

  saveDescriptionButton() {
    return this.page.getByRole('button', { name: 'Save description', exact: true });
  }

  cancelEditingButton() {
    return this.page.getByRole('button', { name: 'Cancel editing', exact: true });
  }

  /** Clicks Save description and waits for the PATCH (default 200). */
  async saveDescription(owner: AssetRef, status = 200): Promise<Response> {
    const [response] = await Promise.all([
      this.page.waitForResponse(relatedResponse(owner, 'PATCH', status)),
      this.saveDescriptionButton().click(),
    ]);
    return response;
  }

  // ── Row actions: remove ──

  /** Row-level Remove. Opens the confirm dialog; it does not delete on its own. */
  rowRemoveButton() {
    return this.page.getByRole('button', { name: 'Remove', exact: true });
  }

  /** The "Remove related item?" dialog, resolved from its heading to the enclosing dialog. */
  removeConfirmDialog() {
    return this.page
      .getByRole('heading', { name: 'Remove related item?', exact: true })
      .locator('xpath=ancestor::*[@role="dialog" or @role="alertdialog"][1]');
  }

  removeConfirmText(name: string) {
    return this.removeConfirmDialog().getByText(
      `This will remove the link between this asset and ${name}. The assets themselves will not be deleted.`,
      { exact: true },
    );
  }

  removeConfirmCancel() {
    return this.removeConfirmDialog().getByRole('button', { name: 'Cancel', exact: true });
  }

  removeConfirmRemove() {
    return this.removeConfirmDialog().getByRole('button', { name: 'Remove', exact: true });
  }

  /** Confirms removal and waits for the DELETE 204. */
  async confirmRemove(owner: AssetRef): Promise<Response> {
    await expect(this.removeConfirmRemove()).toBeVisible();
    const [response] = await Promise.all([
      this.page.waitForResponse(relatedResponse(owner, 'DELETE', 204)),
      this.removeConfirmRemove().click(),
    ]);
    return response;
  }
}
