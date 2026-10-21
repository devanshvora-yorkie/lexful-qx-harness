import { Page, Locator } from '@playwright/test';

/**
 * Common Page Object Model — shared locators for the Lexful app shell.
 */
export class CommonPOM {
  constructor(public page: Page) {}

  // ── Top bar ──

  logo() {
    return this.page.getByRole('img', { name: 'Logo' });
  }

  askLexButton() {
    // Top bar has "Ask Lex" button — use header element to scope (not sidebar)
    return this.page.locator('header').first().getByRole('button', { name: 'Ask Lex' }).first();
  }

  globalSearch() {
    return this.page.getByRole('button', { name: 'Search... ⌘ K' });
  }

  userAvatar() {
    return this.page.getByRole('button', { name: 'AE' });
  }

  // ── User menu (opened by clicking avatar) ──

  userMenuSettings() {
    return this.page.getByRole('menuitem', { name: 'Settings' });
  }

  userMenuAccount() {
    return this.page.getByRole('menuitem', { name: 'Account' });
  }

  userMenuPlatform() {
    return this.page.getByRole('menuitem', { name: 'Platform' });
  }

  userMenuFeedback() {
    return this.page.getByRole('menuitem', { name: 'Feedback' });
  }

  userMenuSupport() {
    return this.page.getByRole('button', { name: 'Support' });
  }

  // ── Sidebar navigation ──

  sidebarCollapse() {
    return this.page.getByRole('button', { name: 'Collapse navigation' });
  }

  sidebarOrgSelector() {
    return this.page.getByRole('combobox');
  }

  sidebarAssetsLink() {
    return this.page.getByRole('link', { name: /Assets/ });
  }

  sidebarOrganizationsLink() {
    return this.page.getByRole('link', { name: /Organizations/ });
  }

  sidebarExpirationsLink() {
    return this.page.getByRole('link', { name: /Expirations/ });
  }

  sidebarDocumentsLink() {
    return this.page.getByRole('link', { name: /Documents/ });
  }

  sidebarPasswordsLink() {
    return this.page.getByRole('link', { name: /Passwords/ });
  }

  sidebarContactsLink() {
    return this.page.getByRole('link', { name: /Contacts/ });
  }

  sidebarLocationsLink() {
    return this.page.getByRole('link', { name: /Locations/ });
  }

  // ── Drawer utilities ──

  /** Close any open drawer — tries multiple strategies */
  async closeDrawer() {
    // Strategy 1: "Close" button in drawer
    const closeBtn = this.page.getByRole('button', { name: 'Close' });
    if (await closeBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await closeBtn.click();
      await this.page.waitForTimeout(500);
      return;
    }
    // Strategy 2: Escape key
    await this.page.keyboard.press('Escape');
    await this.page.waitForTimeout(500);
  }

  /** Wait for a drawer to open (URL contains ?drawer=) */
  async waitForDrawer(timeout = 10000) {
    await this.page.waitForURL(/drawer=/, { timeout });
  }

  // ── Ask Lex AI panel ──

  askLexPanel() {
    return this.page.getByRole('region').filter({ has: this.page.getByText('Ask Lex anything') });
  }

  askLexInput() {
    return this.page.getByPlaceholder('Ask Lex anything…');
  }

  askLexSubmit() {
    return this.page.getByRole('button', { name: 'Submit' });
  }

  askLexClose() {
    return this.page.getByRole('button', { name: 'Close Ask Lex' });
  }

  askLexFindPassword() {
    return this.page.getByRole('button', { name: 'Find a password' });
  }

  askLexLookUpContact() {
    return this.page.getByRole('button', { name: 'Look up a contact' });
  }

  askLexDraftPlaybook() {
    return this.page.getByRole('button', { name: 'Draft a playbook' });
  }

  // ── Toast / notification helpers ──

  async getToastMessage(timeout = 5000): Promise<string | null> {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const toast = this.page.locator('.Toastify__toast').first();
      if (await toast.isVisible({ timeout: 500 }).catch(() => false)) {
        return toast.textContent();
      }
      await this.page.waitForTimeout(200);
    }
    return null;
  }

  // ── Navigation helpers ──

  async navigateTo(path: string) {
    await this.page.goto(path, { waitUntil: 'networkidle' });
  }

  /** Wait for the SPA to fully render (network idle + no loading overlays) */
  async waitForPageReady(timeout = 15000) {
    await this.page.waitForLoadState('networkidle');
    // Wait for any loading spinners/overlays to disappear
    const loadingSelectors = [
      '[role="progressbar"]',
      '.loading-overlay',
      '.skeleton',
    ];
    for (const sel of loadingSelectors) {
      await this.page.locator(sel).first().waitFor({ state: 'hidden', timeout: 3000 }).catch(() => {});
    }
  }
}
