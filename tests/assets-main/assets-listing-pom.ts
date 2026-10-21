import { Page, Locator } from '@playwright/test';
import { CommonPOM } from '../common-pom';

/**
 * POM for the main Assets listing page (/docs/assets).
 */
export class AssetsListingPOM extends CommonPOM {
  constructor(page: Page) {
    super(page);
  }

  // ── Page header ──

  assetsHeading() {
    return this.page.getByRole('heading', { name: 'Assets', level: 1 });
  }

  assetCount() {
    return this.page.locator('text=assets·').first();
  }

  typeCount() {
    return this.page.locator('text=types').first();
  }

  // ── Action buttons ──

  displayOptionsButton() {
    return this.page.getByRole('button', { name: 'Display options' });
  }

  newButton() {
    return this.page.getByRole('button', { name: 'New' });
  }

  // ── Search & filters ──

  searchAssetsBox() {
    return this.page.getByRole('combobox', { name: 'Search assets' });
  }

  organizationFilterButton() {
    return this.page.getByRole('button', { name: '@ Organization' });
  }

  assetTypeFilterButton() {
    return this.page.getByRole('button', { name: 'Asset type' });
  }

  passwordsFilterButton() {
    return this.page.getByRole('button', { name: 'Passwords' });
  }

  documentsFilterButton() {
    return this.page.getByRole('button', { name: 'Documents' });
  }

  shortcutsFilterButton() {
    return this.page.getByRole('button', { name: '/ Shortcuts' });
  }

  // ── Asset type cards ──

  assetTypeCard(name: string): Locator {
    // Cards are links — match by the card title text (no exact to handle search re-rendering)
    return this.page.getByRole('link', { name }).first();
  }

  /** Get all visible asset type card links */
  allAssetTypeCards(): Locator {
    return this.page.locator('[ref*="e"] > a, [role="link"]').filter({
      has: this.page.locator('text=/Access Points|Applications|Backups|Cameras|Computers|Configurations|Contracts|Domains|Email Services|Firewalls|Internet Circuits|Licenses|Microsoft 365|Mobile Devices|Nas Storage|Networks|Phone Systems|Policies|Printers|Remote Access|Server Hardware|Servers|Service Accounts|Software Inventory|Ssl Certificates|Switches|Ups Devices|Vendors|Virtual Machines|Wireless/'),
    });
  }

  /** Check if a specific asset type card is visible */
  async isAssetTypeVisible(name: string): Promise<boolean> {
    return this.assetTypeCard(name).isVisible({ timeout: 3000 }).catch(() => false);
  }

  // ── Ask Lex shortcut buttons on main page ──

  askLexOpenButton() {
    return this.page.getByRole('button', { name: 'Ask Lex' }).last();
  }

  /** Ask Lex panel input — it's a contenteditable div, not a native input */
  askLexAnythingInput(): Locator {
    // Use partial match since the ellipsis character may vary
    return this.page.getByText(/Ask Lex anything/).first();
  }

  // ── Quick action buttons in Ask Lex panel ──

  askLexFindPassword() {
    return this.page.getByRole('button', { name: 'Find a password' });
  }

  askLexLookUpContact() {
    return this.page.getByRole('button', { name: 'Look up a contact' });
  }

  askLexDraftPlaybook() {
    return this.page.getByRole('button', { name: 'Draft a playbook' });
  }
}
