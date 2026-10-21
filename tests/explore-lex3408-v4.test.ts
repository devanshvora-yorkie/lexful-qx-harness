import { test } from '@playwright/test';
import * as fs from 'fs';

const runDir = '/Users/devansh.v/Workspace/lexful-ai/lexful-qa-opencode/runs/LEX-3408-20261019T094547Z-ce01';
const exploreDir = `${runDir}/explore`;

if (!fs.existsSync(exploreDir)) {
  fs.mkdirSync(exploreDir, { recursive: true });
}

test('LEX-3408: Navigate to documents and find drawer', async ({ page }) => {
  try {
    // Navigate to assets/document and let redirects settle
    console.log('1. Navigating to documents (allowing redirects)...');
    await page.goto('https://e2e-test.uat.lexful.net/assets/document', { 
      waitUntil: 'networkidle' 
    });
    
    // Wait for page to stabilize
    await page.waitForTimeout(3000);
    
    const currentUrl = page.url();
    console.log(`Current URL: ${currentUrl}`);
    
    // Screenshot documents page
    await page.screenshot({ path: `${exploreDir}/01-documents-list.png`, fullPage: true });
    console.log('✓ Screenshot: 01-documents-list.png');

    // Look for grid/table
    const rows = await page.locator('[role="row"]').count();
    console.log(`Found ${rows} rows`);
    
    if (rows > 1) {
      // Click on first data row (skip header)
      const firstRow = page.locator('[role="row"]').nth(1);
      const rowText = await firstRow.textContent();
      console.log(`First row: ${rowText?.substring(0, 100)}`);

      console.log('2. Clicking first row to open document...');
      await firstRow.click();
      await page.waitForTimeout(2000);

      // Screenshot with drawer open
      await page.screenshot({ path: `${exploreDir}/02-drawer-open.png`, fullPage: true });
      console.log('✓ Screenshot: 02-drawer-open.png');

      const drawerUrl = page.url();
      console.log(`Drawer URL: ${drawerUrl}`);

      // Now explore drawer elements
      console.log('3. Exploring drawer elements...');
      
      // Look for drawer element
      const drawer = page.locator('[data-asset-drawer]');
      if (await drawer.isVisible()) {
        console.log('✓ Found drawer [data-asset-drawer]');
        
        // Look for actions button (ellipsis)
        const ellipsisBtn = page.locator('[data-asset-drawer] button[aria-label*="action"]').first();
        if (await ellipsisBtn.isVisible()) {
          console.log('✓ Found actions button');
        } else {
          // Try other selectors
          const allButtons = await page.locator('[data-asset-drawer] button').all();
          console.log(`Found ${allButtons.length} buttons in drawer`);
          for (let i = 0; i < Math.min(allButtons.length, 5); i++) {
            const label = await allButtons[i].getAttribute('aria-label');
            const title = await allButtons[i].getAttribute('title');
            console.log(`  Button ${i}: aria-label="${label}", title="${title}"`);
          }
        }

        // Look for revision section
        const revisionSection = page.locator('[data-asset-drawer] [aria-label*="revision"], [data-asset-drawer] [aria-label*="Revision"]');
        if (await revisionSection.isVisible()) {
          console.log('✓ Found revision section');
        }

        // Look for Lex button
        const lexButton = page.locator('[data-asset-drawer] [aria-label*="Lex"]').first();
        if (await lexButton.isVisible()) {
          console.log('✓ Found Lex button');
        }

        // Look for download button
        const downloadBtn = page.locator('[data-asset-drawer] button:has-text("Download"), [data-asset-drawer] [aria-label*="Download"]').first();
        if (await downloadBtn.isVisible()) {
          console.log('✓ Found download button');
        }

        // Inspect drawer HTML
        const drawerHTML = await drawer.evaluate(el => el.innerHTML.substring(0, 500));
        console.log(`Drawer HTML snippet: ${drawerHTML}`);
      }

    } else {
      console.log('No rows found to click');
    }

    await page.screenshot({ path: `${exploreDir}/03-final-state.png`, fullPage: true });

  } catch (e) {
    console.error('Error:', e);
    throw e;
  }
});

test('LEX-3408: Explore drawer query parameters', async ({ page }) => {
  try {
    // First get to the documents page
    console.log('1. Getting document list...');
    await page.goto('https://e2e-test.uat.lexful.net/assets/document', { 
      waitUntil: 'networkidle' 
    });
    await page.waitForTimeout(2000);

    // Get the first document row's click target
    const firstRow = page.locator('[role="row"]').nth(1);
    if (await firstRow.isVisible()) {
      const rowText = await firstRow.textContent();
      console.log(`Document: ${rowText?.substring(0, 80)}`);

      // Click to open in drawer
      await firstRow.click();
      await page.waitForTimeout(2000);

      // Get the URL - it should show the drawer query parameter
      const drawerUrl = page.url();
      console.log(`Drawer URL: ${drawerUrl}`);

      // Parse the URL to extract drawer stack
      const urlObj = new URL(drawerUrl);
      const queryParams = new URLSearchParams(urlObj.search);
      for (const [key, value] of queryParams.entries()) {
        console.log(`  Param: ${key}=${value.substring(0, 100)}${value.length > 100 ? '...' : ''}`);
      }

      // Screenshot showing the drawer with URL visible
      await page.screenshot({ path: `${exploreDir}/04-drawer-url.png`, fullPage: true });
      console.log('✓ Screenshot: 04-drawer-url.png');
    }

  } catch (e) {
    console.error('Error:', e);
  }
});
