import { Page, Locator, expect } from '@playwright/test';
import { CommonPOM } from '../common-pom';

/**
 * POM for the Assets overview (/docs/assets) empty-type behaviour added in LEX-3500.
 * All locators verified against the live UAT DOM on 2026-10-16.
 */
export class AssetsEmptyTypesPOM extends CommonPOM {
  constructor(page: Page) {
    super(page);
  }

  // ── Navigation ──

  /** Load the overview and wait until the type data (incl. the disclosure) has rendered. */
  async gotoOverview(path = '/docs/assets') {
    await this.page.goto(path, { waitUntil: 'domcontentloaded', timeout: 20000 });
    await this.assetsHeading().waitFor({ timeout: 15000 });
    await this.disclosure().waitFor({ timeout: 15000 });
    await this.page.waitForTimeout(800);
  }

  /** Load a specific asset type's list page (e.g. the empty Active Directory list). */
  async gotoType(slug: string) {
    await this.page.goto(`/docs/d/all/${slug}`, { waitUntil: 'domcontentloaded', timeout: 20000 });
    await this.page.waitForTimeout(2500);
  }

  // ── Overview header ──

  assetsHeading() {
    return this.page.getByRole('heading', { name: 'Assets', level: 1 });
  }

  /** The "1,038 assets · 52 types" summary paragraph. */
  summaryText() {
    return this.page.locator('main p').first();
  }

  categoryHeading(name: string) {
    return this.page.getByRole('heading', { name, level: 2 });
  }

  /** All type cards (populated + expanded empty) on the overview. */
  typeCards() {
    return this.page.locator('main a[href^="/docs/d/all/"]');
  }

  // ── "N available" disclosure ──

  /** The independent empty-type disclosure button, e.g. "21 available". */
  disclosure() {
    return this.page.getByRole('button', { name: /^\d+ available$/ }).first();
  }

  /** The collapsible root element that owns the disclosure button + its content. */
  disclosureRoot() {
    return this.disclosure().locator('xpath=..');
  }

  /** Empty-type rows rendered inside the expanded disclosure. */
  emptyRows() {
    return this.disclosureRoot().locator('div.group');
  }

  /** Add buttons inside the disclosure (one per empty row). */
  addButtons() {
    return this.disclosureRoot().getByRole('button', { name: /^Add / });
  }

  async disclosureNumber(): Promise<number> {
    const label = await this.disclosure().innerText();
    return parseInt(label.replace(/[^\d]/g, ''), 10);
  }

  async expandDisclosure() {
    if ((await this.disclosure().getAttribute('aria-expanded')) !== 'true') {
      await this.disclosure().click();
      await expect(this.disclosure()).toHaveAttribute('aria-expanded', 'true');
    }
  }

  async collapseDisclosure() {
    if ((await this.disclosure().getAttribute('aria-expanded')) !== 'false') {
      await this.disclosure().click();
      await expect(this.disclosure()).toHaveAttribute('aria-expanded', 'false');
    }
  }

  // ── Empty type rows ──

  /** The link for a named type card, e.g. "Active Directory". */
  typeLink(name: string) {
    return this.page.getByRole('link', { name, exact: true });
  }

  /** The empty row (group container) for a named type. */
  emptyRow(name: string): Locator {
    return this.disclosureRoot()
      .locator('div.group')
      .filter({ has: this.page.getByRole('link', { name, exact: true }) })
      .filter({ has: this.page.getByRole('button', { name: `Add ${name}`, exact: true }) });
  }

  /** The "+ Add <type>" button for a named empty type. */
  addButton(name: string) {
    return this.page.getByRole('button', { name: `Add ${name}`, exact: true });
  }

  // ── Drawer ──

  dialog() {
    return this.page.getByRole('dialog');
  }

  createDrawerHeading() {
    return this.dialog().getByRole('heading', { level: 2 }).first();
  }

  drawerOrgCombobox() {
    return this.dialog().getByRole('combobox');
  }

  drawerCreateButton() {
    return this.dialog().getByRole('button', { name: 'Create', exact: true });
  }

  drawerFirstField() {
    return this.dialog().getByRole('textbox').first();
  }

  // ── Asset-list empty state ──

  emptyStateHeading() {
    return this.page.getByRole('heading', { name: /^No .+ yet$/ }).first();
  }

  // ── Utilities ──

  /** Computed opacity — used to verify hover/focus reveal of the Add button. */
  async opacity(loc: Locator): Promise<string> {
    return loc.evaluate((el) => getComputedStyle(el as HTMLElement).opacity);
  }
}
