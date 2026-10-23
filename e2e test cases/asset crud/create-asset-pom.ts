import { Page, Locator } from '@playwright/test';
import { CommonPOM } from './common-pom';

/**
 * POM for the "New Asset" create drawer.
 */
export class CreateAssetPOM extends CommonPOM {
  constructor(page: Page) {
    super(page);
  }

  // ── Drawer heading (h2) ──

  createHeading(): Locator {
    return this.page.getByRole('heading', { name: /New Servers/, level: 2 });
  }

  // ── Form fields — use placeholder-based selectors (most have no aria-label) ──

  nameField(): Locator {
    // Only input with placeholder "Untitled" and aria-label "Name"
    return this.page.getByRole('textbox', { name: 'Name' }).first();
  }

  roleCombobox(): Locator {
    return this.page.getByRole('combobox', { name: 'Select role' });
  }

  hostnameField(): Locator {
    return this.page.getByPlaceholder('Enter hostname');
  }

  ipAddressField(): Locator {
    return this.page.getByPlaceholder('Enter ip address');
  }

  osCombobox(): Locator {
    return this.page.getByRole('combobox', { name: 'Select operating system' });
  }

  platformCombobox(): Locator {
    return this.page.getByRole('combobox', { name: 'Select platform' });
  }

  warrantyExpirationField(): Locator {
    return this.page.getByPlaceholder('Select warranty expiration');
  }

  configurationField(): Locator {
    return this.page.getByPlaceholder('Enter configuration').first();
  }

  parentHostCombobox(): Locator {
    return this.page.getByRole('combobox', { name: 'Select' }).nth(0);
  }

  hostedAppsCombobox(): Locator {
    return this.page.getByRole('combobox', { name: 'Select' }).nth(1);
  }

  backupPlanCombobox(): Locator {
    return this.page.getByRole('combobox', { name: 'Select' });
  }

  // ── Tabs in create form ──

  detailsTab(): Locator {
    return this.page.getByRole('tab', { name: 'Details' });
  }

  accessTab(): Locator {
    return this.page.getByRole('tab', { name: 'Access' });
  }

  // ── Action buttons in footer ──

  cancelButton(): Locator {
    return this.page.getByRole('button', { name: 'Cancel' });
  }

  createButton(): Locator {
    return this.page.getByRole('button', { name: 'Create', exact: true });
  }

  /** Check if Create button is disabled */
  async isCreateDisabled(): Promise<boolean> {
    return this.createButton().isDisabled();
  }

  // ── Drawer close (X) button in header ──

  drawerCloseButton(): Locator {
    return this.page.getByRole('button', { name: 'Close' }).first();
  }

  /** Organization combobox in the create form */
  organizationCombobox(): Locator {
    return this.page.getByRole('combobox').filter({ hasText: 'Choose an organization' });
  }
}
