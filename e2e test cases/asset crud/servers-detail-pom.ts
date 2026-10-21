import { Page, Locator } from '@playwright/test';
import { CommonPOM } from './common-pom';

/**
 * POM for the asset detail drawer (opened by clicking a row).
 */
export class ServersDetailPOM extends CommonPOM {
  constructor(page: Page) {
    super(page);
  }

  // ── Dialog header ──

  /** Organization button in breadcrumb, e.g. "Adipiscing Aliqua Academy" */
  drawerOrganizationButton(): Locator {
    return this.page.getByRole('button', { name: /Adipiscing/ }).first();
  }

  /** Asset type badge button, e.g. "Servers" */
  drawerAssetTypeBadge(): Locator {
    return this.page.getByRole('button', { name: 'Servers' });
  }

  moreActionsButton(): Locator {
    return this.page.getByRole('button', { name: 'More actions' });
  }

  copyLinkButton(): Locator {
    return this.page.getByRole('button', { name: 'Copy link' });
  }

  expandRecordButton(): Locator {
    return this.page.getByRole('button', { name: 'Expand record' });
  }

  /** Close button in dialog header */
  drawerCloseButton(): Locator {
    return this.page.getByRole('button', { name: 'Close' }).first();
  }

  // ── Heading (server name in h2) ──

  heading(level = 2): Locator {
    return this.page.getByRole('heading', { level });
  }

  /** The h2 heading showing the server name */
  serverNameHeading(): Locator {
    return this.page.getByRole('heading', { level: 2 });
  }

  // ── Edit Name button (inside the h2) ──

  editNameButton(): Locator {
    // The Edit Name button is inside the h2 element, text is "Edit Name" + server name
    return this.page.getByRole('heading', { level: 2 })
      .locator('button');
  }

  // ── Tabs ──

  tab(name: string): Locator {
    return this.page.getByRole('tab', { name });
  }

  overviewTab() {
    return this.tab('Overview');
  }

  detailsTab() {
    return this.tab('Details');
  }

  relationshipsTab() {
    return this.tab('Relationships');
  }

  attachmentsTab() {
    return this.tab('Attachments');
  }

  accessTab() {
    return this.tab('Access');
  }

  historyTab() {
    return this.tab('History');
  }

  sourcesTab() {
    return this.tab('Sources');
  }

  systemInfoTab() {
    return this.tab('System info');
  }

  // ── Details tab fields ──

  /** Get the edit/add button for a detail field by its label text */
  editFieldButton(label: string): Locator {
    return this.page.getByRole('button', { name: new RegExp('^Edit ' + label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$') }).first();
  }

  addFieldButton(label: string): Locator {
    return this.page.getByRole('button', { name: new RegExp('^Add ' + label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$') }).first();
  }

  editRoleButton(): Locator {
    return this.editFieldButton('Role');
  }

  addHostnameButton(): Locator {
    return this.addFieldButton('Hostname');
  }

  editIPAddressButton(): Locator {
    return this.editFieldButton('IP Address');
  }

  editOperatingSystemButton(): Locator {
    return this.editFieldButton('Operating System');
  }

  editPlatformButton(): Locator {
    return this.editFieldButton('Platform');
  }

  editWarrantyExpirationButton(): Locator {
    return this.editFieldButton('Warranty Expiration');
  }

  editConfigurationButton(): Locator {
    return this.editFieldButton('Configuration');
  }

  addParentHostButton(): Locator {
    return this.addFieldButton('Parent Host');
  }

  addHostedApplicationsButton(): Locator {
    return this.addFieldButton('Hosted Applications');
  }

  editBackupPlanButton(): Locator {
    return this.editFieldButton('Backup Plan');
  }

  // ── Overview tab ──

  overviewRelationshipsHeading(): Locator {
    return this.page.getByRole('heading', { name: 'Relationships', level: 3 });
  }

  viewAllRelationshipsButton(): Locator {
    return this.page.getByRole('button', { name: 'View all' }).first();
  }

  /** Get linked items in Overview */
  linkedItem(type: string): Locator {
    return this.page.locator(`[role=listitem] > * > text:${type}`).first();
  }
}
