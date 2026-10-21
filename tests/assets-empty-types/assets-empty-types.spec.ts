import { test, expect } from '@playwright/test';
import { injectAuthCookies } from '../../auth-helper';
import { AssetsEmptyTypesPOM } from './assets-empty-types-pom';

/**
 * LEX-3500 — the Assets overview must surface enabled asset types with zero records
 * behind a per-category "N available" disclosure, with a quick-add action, plus the
 * asset-type-aware empty states on a type's list page.
 *
 * Anchored on "Active Directory" (seeded, currently empty, sorts first in the disclosure).
 */

const EMPTY_TYPE = 'Active Directory';
const EMPTY_SLUG = 'active_directory';

test.describe('LEX-3500 — Assets overview: empty asset types with quick add', () => {
  let pom: AssetsEmptyTypesPOM;

  test.beforeEach(async ({ page }) => {
    await injectAuthCookies(page.context());
    pom = new AssetsEmptyTypesPOM(page);
    await pom.gotoOverview();
  });

  test('1. header summary shows the asset total and the count of all eligible types', async () => {
    const summary = pom.summaryText();
    await expect(summary).toContainText(/\d[\d,]*\s*assets/);
    await expect(summary).toContainText(/\d+\s*types/);

    const types = parseInt((await summary.innerText()).match(/(\d[\d,]*)\s*types/)![1].replace(/,/g, ''), 10);

    // "types" counts populated cards AND the empty types hidden behind the disclosure
    await pom.expandDisclosure();
    expect(types).toBe(await pom.typeCards().count());
  });

  test('2. empty asset types are hidden behind a collapsed disclosure by default', async () => {
    await expect(pom.disclosure()).toHaveAttribute('aria-expanded', 'false');
    await expect(pom.typeLink(EMPTY_TYPE)).toHaveCount(0);
  });

  test('3. disclosure is labelled "<N> available", starts collapsed and is keyboard-focusable', async () => {
    const disc = pom.disclosure();
    await expect(disc).toHaveText(/^\d+ available$/);
    await expect(disc).toHaveAttribute('aria-expanded', 'false');
    await disc.focus();
    await expect(disc).toBeFocused();
  });

  test('4. expanding reveals empty rows with a 0 count and the type list link', async () => {
    await pom.expandDisclosure();
    await expect(pom.disclosure()).toHaveAttribute('aria-expanded', 'true');

    const link = pom.typeLink(EMPTY_TYPE);
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute('href', `/docs/d/all/${EMPTY_SLUG}`);

    const row = pom.emptyRow(EMPTY_TYPE);
    await expect(row).toBeVisible();
    await expect(row).toContainText('0');
  });

  test('5. empty rows use muted styling while populated rows do not', async () => {
    await pom.expandDisclosure();
    await expect(pom.typeLink(EMPTY_TYPE)).toHaveClass(/text-muted-foreground/);
    await expect(pom.typeLink('Servers')).not.toHaveClass(/text-muted-foreground/);
  });

  test('6. disclosure count equals the number of empty rows and Add buttons', async () => {
    await pom.expandDisclosure();
    const n = await pom.disclosureNumber();
    expect(n).toBeGreaterThan(0);
    await expect(pom.emptyRows()).toHaveCount(n);
    await expect(pom.addButtons()).toHaveCount(n);
  });

  test('7. disclosure is keyboard-operable: Enter expands, Space collapses', async () => {
    const disc = pom.disclosure();
    await disc.focus();
    await pom.page.keyboard.press('Enter');
    await expect(disc).toHaveAttribute('aria-expanded', 'true');
    await pom.page.keyboard.press(' ');
    await expect(disc).toHaveAttribute('aria-expanded', 'false');
  });

  test('8. collapsing the disclosure hides the empty rows again', async () => {
    await pom.expandDisclosure();
    await expect(pom.typeLink(EMPTY_TYPE)).toBeVisible();

    await pom.collapseDisclosure();
    await expect(pom.disclosure()).toHaveAttribute('aria-expanded', 'false');
    await expect(pom.typeLink(EMPTY_TYPE)).toHaveCount(0);
  });

  test('9. hovering an empty row reveals the "+ Add <type>" button', async () => {
    await pom.expandDisclosure();
    const add = pom.addButton(EMPTY_TYPE);
    await expect(add).toBeAttached();
    expect(await pom.opacity(add)).toBe('0');

    await pom.typeLink(EMPTY_TYPE).hover();
    await expect.poll(() => pom.opacity(add)).toBe('1');
  });

  test('10. focusing an empty row reveals the "+ Add <type>" button', async () => {
    await pom.expandDisclosure();
    const add = pom.addButton(EMPTY_TYPE);
    expect(await pom.opacity(add)).toBe('0');

    await pom.typeLink(EMPTY_TYPE).focus();
    await expect.poll(() => pom.opacity(add)).toBe('1');
  });

  test('11. quick-add opens the creation drawer with the type preselected + org context', async () => {
    await pom.expandDisclosure();
    await pom.typeLink(EMPTY_TYPE).hover();

    const typeFetch = pom.page.waitForResponse(
      (r) => r.url().includes(`/v1/asset_types?name=${EMPTY_SLUG}`) && r.request().method() === 'GET',
    );
    await pom.addButton(EMPTY_TYPE).click();
    await typeFetch;

    await expect(pom.page).toHaveURL(
      new RegExp(`drawer=%5B%7B%22type%22%3A%22${EMPTY_SLUG}%22%2C%22id%22%3A%22new%22%7D%5D`),
    );
    await expect(pom.dialog()).toBeVisible();
    await expect(pom.createDrawerHeading()).toHaveText(`New ${EMPTY_TYPE}`);
    await expect(pom.drawerOrgCombobox()).toBeVisible();
    // autofocus follows the saved display layout (first displayed field)
    await expect(pom.drawerFirstField()).toBeFocused();
    await expect(pom.drawerCreateButton()).toBeDisabled();
  });

  test('12. Files and primary-navigation types are excluded from the cards', async () => {
    await pom.expandDisclosure();
    for (const href of [
      '/docs/d/all/system.file',
      '/docs/d/all/system.document',
      '/docs/d/all/system.password',
      '/docs/d/all/system.contact',
      '/docs/d/all/system.location',
    ]) {
      await expect(pom.page.locator(`main a[href="${href}"]`)).toHaveCount(0);
    }
  });

  test('13. an empty type link navigates to its list page', async () => {
    await pom.expandDisclosure();
    await pom.typeLink(EMPTY_TYPE).click();
    await expect(pom.page).toHaveURL(new RegExp(`/docs/d/all/${EMPTY_SLUG}(\\?|$)`));
    await expect(pom.page.getByRole('heading', { name: EMPTY_TYPE })).toBeVisible();
  });

  test('14. asset-list empty state uses capitalized type copy and an Add action', async () => {
    await pom.gotoType(EMPTY_SLUG);
    await expect(pom.emptyStateHeading()).toHaveText(`No ${EMPTY_TYPE} yet`);
    await expect(pom.page.getByText(`Add ${EMPTY_TYPE} to get started.`)).toBeVisible();
    await expect(pom.page.getByRole('button', { name: `Add ${EMPTY_TYPE}`, exact: true })).toBeVisible();
  });

  test('15. the empty-state Add action opens the create drawer with the type preselected', async () => {
    await pom.gotoType(EMPTY_SLUG);
    const add = pom.page.getByRole('button', { name: `Add ${EMPTY_TYPE}`, exact: true });
    await expect(add).toBeVisible();
    await add.click();
    await expect(pom.dialog()).toBeVisible();
    await expect(pom.createDrawerHeading()).toHaveText(`New ${EMPTY_TYPE}`);
    await expect(pom.drawerOrgCombobox()).toBeVisible();
    await expect(pom.drawerFirstField()).toBeFocused();
  });
});
