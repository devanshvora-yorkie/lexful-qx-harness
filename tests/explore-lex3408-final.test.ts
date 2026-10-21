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

test('LEX-3408: Wait for dynamic content and explore', async ({ page }) => {
  try {
    // Navigate to assets - might have empty initial state
    console.log('1. Navigating to /docs/assets...');
    await page.goto('https://e2e-test.uat.lexful.net/docs/assets', { 
      waitUntil: 'domcontentloaded',
      timeout: 10000
    });

    // Wait for grid to appear - look for ag-grid or any row
    console.log('2. Waiting for content to load...');
    await page.waitForTimeout(4000); // Wait for React render and data fetch

    // Check if we have rows now
    const rows = await page.locator('[role="row"]').count();
    console.log(`Found ${rows} rows after waiting`);

    // Take screenshot
    await page.screenshot({ path: `${exploreDir}/01-assets-loaded.png`, fullPage: true });
    console.log('✓ Screenshot: 01-assets-loaded.png');

    if (rows > 1) {
      // Click first data row
      console.log('3. Clicking first row...');
      const firstDataRow = page.locator('[role="row"]').nth(1);
      await firstDataRow.click();
      await page.waitForTimeout(2000);

      // Take drawer screenshot
      await page.screenshot({ path: `${exploreDir}/02-drawer.png`, fullPage: true });
      console.log('✓ Screenshot: 02-drawer.png');

      const drawerUrl = page.url();
      console.log(`Drawer URL: ${drawerUrl}`);

      // Explore drawer
      console.log('4. Exploring drawer components...');
      
      // Find all buttons
      const buttons = await page.locator('[data-asset-drawer] button, [role="dialog"] button').all();
      console.log(`Found ${buttons.length} buttons in drawer region`);

      // Take focused screenshot of header area
      const headerArea = page.locator('[data-asset-drawer] header, [role="dialog"] > div:first-child').first();
      if (await headerArea.isVisible()) {
        await headerArea.screenshot({ path: `${exploreDir}/03-drawer-header.png` });
        console.log('✓ Screenshot: 03-drawer-header.png');
      }

      // Look for specific elements in drawer
      const elements = await page.evaluate(() => {
        const drawer = document.querySelector('[data-asset-drawer]') || document.querySelector('[role="dialog"]');
        if (!drawer) return null;

        return {
          hasRevisionButton: !!drawer.querySelector('button:has-text("View revision"), button:contains("View revision")'),
          hasLexButton: !!Array.from(drawer.querySelectorAll('button')).some(btn => 
            btn.getAttribute('aria-label')?.includes('Lex')
          ),
          hasEllipsis: !!Array.from(drawer.querySelectorAll('button')).some(btn => {
            const label = btn.getAttribute('aria-label') || '';
            const text = btn.textContent || '';
            return label.toLowerCase().includes('action') || label.toLowerCase().includes('more') || text.includes('⋯');
          }),
          buttonLabels: Array.from(drawer.querySelectorAll('button')).map(btn => ({
            label: btn.getAttribute('aria-label'),
            text: btn.textContent?.substring(0, 30),
            title: btn.getAttribute('title')
          })).slice(0, 10)
        };
      });

      console.log('Drawer elements:', JSON.stringify(elements, null, 2));

      // Try clicking actions/more menu if found
      const moreBtn = page.locator('button[aria-label*="action"], button[aria-label*="more"]').first();
      if (await moreBtn.isVisible()) {
        console.log('5. Clicking more/actions button...');
        await moreBtn.click();
        await page.waitForTimeout(1000);

        await page.screenshot({ path: `${exploreDir}/04-actions-menu.png`, fullPage: true });
        console.log('✓ Screenshot: 04-actions-menu.png');

        // Get menu options
        const menuItems = await page.locator('[role="menuitem"]').allTextContents();
        console.log('Menu items:', menuItems);
      }

      // Look for revision panel
      const revisionPanel = page.locator('[aria-label*="Revision"], [aria-label*="revision"]').first();
      if (await revisionPanel.isVisible()) {
        console.log('✓ Found revision panel');
        await revisionPanel.screenshot({ path: `${exploreDir}/05-revision-panel.png` });
      }

      // Look for Lex menu
      const lexMenu = page.locator('[aria-label*="Lex"]').first();
      if (await lexMenu.isVisible()) {
        console.log('✓ Found Lex menu/button');
        await lexMenu.screenshot({ path: `${exploreDir}/06-lex-menu.png` });
      }
    } else {
      console.log('No rows found - checking if assets exist...');
      const bodyText = await page.evaluate(() => document.body.innerText);
      console.log('Page text:', bodyText.substring(0, 500));
    }

  } catch (e) {
    console.error('Error:', e);
    throw e;
  }
});

test('LEX-3408: Test legacy detail route redirect', async ({ page }) => {
  try {
    // According to the ticket, legacy /_/d/<org>/<assetType>/<assetId> should redirect into drawer
    // First, get an asset ID from the assets page
    await page.goto('https://e2e-test.uat.lexful.net/docs/assets', { 
      waitUntil: 'domcontentloaded',
      timeout: 10000
    });
    await page.waitForTimeout(3000);

    // Try clicking a row to get the drawer URL
    const firstRow = page.locator('[role="row"]').nth(1);
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForTimeout(1000);

      // Get current URL with drawer
      const drawerUrl = page.url();
      console.log(`Drawer URL: ${drawerUrl}`);

      // Parse it to extract IDs
      const params = new URLSearchParams(new URL(drawerUrl).search);
      const dParam = params.get('d');
      console.log(`d parameter: ${dParam?.substring(0, 100)}`);

      // Now try the legacy route format
      // /_/d/<org>/<assetType>/<assetId>
      console.log('Testing legacy route redirect...');
      await page.goto('https://e2e-test.uat.lexful.net/_/d/all/document/test-asset-id', { 
        waitUntil: 'domcontentloaded',
        timeout: 10000
      });
      await page.waitForTimeout(2000);

      const finalUrl = page.url();
      console.log(`After legacy route navigation: ${finalUrl}`);

      // Take screenshot
      await page.screenshot({ path: `${exploreDir}/07-legacy-redirect.png`, fullPage: true });
    }

  } catch (e) {
    console.error('Error:', e);
    // Don't fail test
  }
});
