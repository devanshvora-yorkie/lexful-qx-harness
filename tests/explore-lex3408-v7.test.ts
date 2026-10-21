import { test } from '@playwright/test';
import * as fs from 'fs';

const runDir = '/Users/devansh.v/Workspace/lexful-ai/lexful-qa-opencode/runs/LEX-3408-20261019T094547Z-ce01';
const exploreDir = `${runDir}/explore`;

if (!fs.existsSync(exploreDir)) {
  fs.mkdirSync(exploreDir, { recursive: true });
}

test.use({
  storageState: `${runDir}/auth-state.json`
});

test('LEX-3408: Navigate to assets and find documents', async ({ page }) => {
  try {
    // Navigate to assets
    console.log('1. Navigating to /docs/assets...');
    await page.goto('https://e2e-test.uat.lexful.net/docs/assets', { 
      waitUntil: 'domcontentloaded',
      timeout: 10000
    });
    await page.waitForTimeout(3000);

    // Take screenshot
    await page.screenshot({ path: `${exploreDir}/01-assets-page.png`, fullPage: true });
    console.log('✓ Screenshot: 01-assets-page.png');

    // Check URL
    console.log(`URL: ${page.url()}`);

    // Look for filters or type selector
    const typeFilters = await page.locator('[role="button"]:has-text("document"), [role="button"]:has-text("Document"), button:has-text("document")').all();
    console.log(`Found ${typeFilters.length} potential document filters`);

    if (typeFilters.length > 0) {
      console.log('2. Clicking document filter...');
      await typeFilters[0].click();
      await page.waitForTimeout(2000);

      // Take screenshot after filter
      await page.screenshot({ path: `${exploreDir}/02-documents-filtered.png`, fullPage: true });
      console.log('✓ Screenshot: 02-documents-filtered.png');
    }

    // Look for grid/rows
    const rows = await page.locator('[role="row"]').all();
    console.log(`Found ${rows.length} rows`);

    if (rows.length > 1) {
      // Get first data row
      const firstDataRow = rows[1];
      const rowText = await firstDataRow.textContent();
      console.log(`First row: ${rowText?.substring(0, 100)}`);

      // Click to open
      console.log('3. Clicking first row to open drawer...');
      await firstDataRow.click();
      await page.waitForTimeout(2000);

      // Screenshot drawer
      await page.screenshot({ path: `${exploreDir}/03-drawer-opened.png`, fullPage: true });
      console.log('✓ Screenshot: 03-drawer-opened.png');

      // Check URL has drawer params
      const drawerUrl = page.url();
      console.log(`Drawer URL: ${drawerUrl}`);

      // Now explore the drawer
      console.log('4. Exploring drawer elements...');
      
      // Look for header
      const header = page.locator('[data-asset-drawer] header, [data-asset-drawer] [class*="header"]').first();
      if (await header.isVisible()) {
        await header.screenshot({ path: `${exploreDir}/04-drawer-header.png` });
        console.log('✓ Screenshot: 04-drawer-header.png');
      }

      // Find the actions menu button
      const allButtons = await page.locator('[data-asset-drawer] button').all();
      console.log(`Found ${allButtons.length} buttons in drawer`);

      for (let i = 0; i < Math.min(allButtons.length, 5); i++) {
        const label = await allButtons[i].getAttribute('aria-label');
        const title = await allButtons[i].getAttribute('title');
        const text = await allButtons[i].textContent();
        console.log(`  Button ${i}: label="${label}", title="${title}", text="${text?.substring(0, 30)}"`);
      }

      // Find ellipsis button specifically
      const ellipsisBtn = await page.locator('[data-asset-drawer] button').filter({
        has: page.locator('svg [*|href*="ellipsis"], .lucide-ellipsis')
      }).first();

      if (await ellipsisBtn.isVisible()) {
        console.log('✓ Found ellipsis actions button');
        await ellipsisBtn.screenshot({ path: `${exploreDir}/05-ellipsis-button.png` });

        // Click to open menu
        console.log('5. Clicking ellipsis to open menu...');
        await ellipsisBtn.click();
        await page.waitForTimeout(1000);

        // Screenshot menu
        await page.screenshot({ path: `${exploreDir}/06-actions-menu.png`, fullPage: true });
        console.log('✓ Screenshot: 06-actions-menu.png');

        // Get menu items
        const menuItems = await page.locator('[role="menuitem"]').all();
        console.log(`Menu items: ${menuItems.length}`);
        for (let i = 0; i < menuItems.length; i++) {
          const text = await menuItems[i].textContent();
          console.log(`  - ${text?.trim()}`);
        }
      }

      // Look for revision section
      const revisionSection = page.locator('[aria-label*="revision"], [aria-label*="Revision"], [aria-label*="history"]');
      if (await revisionSection.first().isVisible()) {
        console.log('✓ Found revision section');
        await revisionSection.first().screenshot({ path: `${exploreDir}/07-revision-section.png` });
      }

      // Look for Lex menu
      const lexBtn = page.locator('[aria-label*="Lex"]').first();
      if (await lexBtn.isVisible()) {
        console.log('✓ Found Lex button');
        await lexBtn.screenshot({ path: `${exploreDir}/08-lex-button.png` });
      }
    }

  } catch (e) {
    console.error('Error:', e);
    throw e;
  }
});
