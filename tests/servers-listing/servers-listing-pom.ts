import { Page, Locator } from '@playwright/test';
import { CommonPOM } from '../common-pom';

/**
 * POM for an asset type listing page (e.g., /docs/d/all/servers).
 */
export class ServersListingPOM extends CommonPOM {
  constructor(page: Page) {
    super(page);
  }

  // ── Page header ──

  assetTypeHeading(level = 1): Locator {
    return this.page.getByRole('heading', { name: 'Servers', level });
  }

  totalCount() {
    return this.page.locator('text=servers·').first();
  }

  // ── Toolbar buttons ──

  collapseAllButton() {
    return this.page.getByRole('button', { name: 'Collapse all' });
  }

  displayButton() {
    return this.page.getByRole('button', { name: 'Display' });
  }

  newButton(): Locator {
    return this.page.getByRole('button', { name: 'New' }).first();
  }

  // ── Filter bar ──

  searchBox() {
    return this.page.getByRole('textbox', { name: 'Search Servers...' });
  }

  assetStatusFilter() {
    return this.page.getByRole('button', { name: /Asset status:/ });
  }

  filtersButton() {
    return this.page.getByRole('button', { name: 'Filters' });
  }

  organizationCombobox() {
    return this.page.locator('combobox').filter({ hasText: 'All organizations' }).first();
  }

  tagsCombobox() {
    return this.page.getByRole('combobox', { name: 'Tags' });
  }

  // ── Treegrid ──

  treegrid() {
    return this.page.locator('[role=treegrid]');
  }

  /** Select-all checkbox in header — AG Grid uses input[type=checkbox], NOT role=checkbox */
  selectAllCheckbox(): Locator {
    return this.page.locator('input.ag-checkbox-input[aria-label="Select loaded rows"]');
  }

  /** Get all row checkboxes — AG Grid inputs have aria-label with "Press Space to toggle" */
  rowCheckboxes(): Locator {
    return this.page.locator('input[type=checkbox][aria-label*="Press Space"]');
  }

  /** Find a data row by its visible text (e.g., server name in a gridcell) */
  rowByName(name: string): Locator {
    return this.page.getByRole('gridcell', { name }).first().locator('..');
  }

  /** Get row checkbox by name */
  rowCheckboxByName(name: string): Locator {
    return this.rowByName(name).locator('input[type=checkbox]').first();
  }

  // ── Bulk action buttons (visible when rows selected) ──

  bulkAccessButton(): Locator {
    return this.page.getByRole('button', { name: 'Access' });
  }

  bulkTagsButton(): Locator {
    return this.page.getByRole('button', { name: 'Tags' });
  }

  bulkActionsButton(): Locator {
    return this.page.getByRole('button', { name: 'Actions' });
  }

  clearSelectionButton(): Locator {
    return this.page.getByRole('button', { name: 'Clear selection' });
  }

  /** Selection count text, e.g. "0 selected" */
  selectionCount(): Locator {
    return this.page.locator('text=selected');
  }

  // ── Column headers (NO aria-label — match by exact text content) ──

  columnHeader(name: string): Locator {
    return this.page.getByRole('columnheader', { name, exact: true });
  }

  // ── Row cell content ──

  cellByNameAndColumn(rowName: string, columnName: string): Locator {
    return this.rowByName(rowName).locator(`[role=gridcell]:has-text("${columnName}")`).first();
  }

  // ── Tabs (available in detail drawer) ──

  overviewTab(): Locator {
    return this.page.getByRole('tab', { name: 'Overview' });
  }

  detailsTab(): Locator {
    return this.page.getByRole('tab', { name: 'Details' });
  }

  relationshipsTab(): Locator {
    return this.page.getByRole('tab', { name: 'Relationships' });
  }

  attachmentsTab(): Locator {
    return this.page.getByRole('tab', { name: 'Attachments' });
  }

  accessTab(): Locator {
    return this.page.getByRole('tab', { name: 'Access' });
  }

  historyTab(): Locator {
    return this.page.getByRole('tab', { name: 'History' });
  }

  sourcesTab(): Locator {
    return this.page.getByRole('tab', { name: 'Sources' });
  }

  systemInfoTab(): Locator {
    return this.page.getByRole('tab', { name: 'System info' });
  }

  // ── Navigation to detail drawer ──

  async openRowDetail(name: string) {
    const row = this.rowByName(name);
    await row.click();
    await this.waitForDrawer(10000);
  }
}
