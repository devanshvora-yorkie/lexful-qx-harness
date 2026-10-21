import { test, Browser } from '@playwright/test';
import * as fs from 'fs';

const runDir = '/Users/devansh.v/Workspace/lexful-ai/lexful-qa-opencode/runs/LEX-3408-20261019T094547Z-ce01';
const exploreDir = `${runDir}/explore`;

if (!fs.existsSync(exploreDir)) {
  fs.mkdirSync(exploreDir, { recursive: true });
}

test.use({
  storageState: `${runDir}/auth-state.json`
});

test('LEX-3408: With auth - Navigate to documents', async ({ page }) => {
  try {
    console.log('1. Checking current auth...');
    await page.goto('https://e2e-test.uat.lexful.net/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1000);

    // Check if we're logged in
    const url = page.url();
    console.log(`Current URL: ${url}`);
    const bodyText = await page.evaluate(() => document.body.innerText.substring(0, 300));
    console.log(`Page text: ${bodyText}`);

    // Take screenshot
    await page.screenshot({ path: `${exploreDir}/01-auth-check.png`, fullPage: true });

    // Try navigating to documents
    console.log('2. Navigating to /docs/assets/document...');
    await page.goto('https://e2e-test.uat.lexful.net/docs/assets/document', { 
      waitUntil: 'domcontentloaded',
      timeout: 10000
    });
    await page.waitForTimeout(2000);

    const docUrl = page.url();
    console.log(`After navigation: ${docUrl}`);

    // Screenshot
    await page.screenshot({ path: `${exploreDir}/02-documents-page.png`, fullPage: true });
    console.log('✓ Screenshot: 02-documents-page.png');

    // Check for grid
    const rows = await page.locator('[role="row"]').count();
    console.log(`Found ${rows} rows`);

    // Look for ag-grid viewport
    const gridViewport = page.locator('.ag-root, [role="grid"], [class*="grid"]');
    if (await gridViewport.first().isVisible()) {
      console.log('✓ Found grid');
    }

    // Look for any document rows by text content
    const cellsWithText = await page.locator('[role="gridcell"]').count();
    console.log(`Found ${cellsWithText} grid cells`);

  } catch (e) {
    console.error('Error:', e);
    throw e;
  }
});

test('LEX-3408: Explore drawer with document', async ({ page }) => {
  try {
    console.log('1. Setting auth and navigating...');
    await page.goto('https://e2e-test.uat.lexful.net/docs/assets/document', { 
      waitUntil: 'domcontentloaded',
      timeout: 10000
    });
    await page.waitForTimeout(3000);

    // Get URL
    const url = page.url();
    console.log(`URL: ${url}`);

    // Look for rows
    const firstRow = page.locator('[role="row"]').nth(1);
    if (await firstRow.isVisible({ timeout: 5000 })) {
      console.log('2. Found row, clicking to open drawer...');
      const rowText = await firstRow.textContent();
      console.log(`Row text: ${rowText?.substring(0, 100)}`);

      // Click the row
      await firstRow.click();
      await page.waitForTimeout(2000);

      // Screenshot drawer
      await page.screenshot({ path: `${exploreDir}/03-drawer.png`, fullPage: true });
      console.log('✓ Screenshot: 03-drawer.png');

      // Get drawer URL
      const drawerUrl = page.url();
      console.log(`Drawer URL: ${drawerUrl}`);

      // Explore drawer structure
      console.log('3. Exploring drawer...');
      
      // Find header with actions
      const header = page.locator('[data-asset-drawer] header, [data-asset-drawer] > div:first-child').first();
      if (await header.isVisible()) {
        const headerText = await header.textContent();
        console.log(`Header: ${headerText?.substring(0, 100)}`);
        
        // Screenshot header
        await header.screenshot({ path: `${exploreDir}/04-drawer-header.png` });
      }

      // Find actions menu
      const menuBtn = page.locator('button[aria-label*="more"], button[aria-label*="action"], [data-testid*="action"]').first();
      if (await menuBtn.isVisible()) {
        console.log('✓ Found menu button');
        await menuBtn.screenshot({ path: `${exploreDir}/05-menu-button.png` });
      }

      // Find revision history section
      const revisionBtn = page.locator('button:has-text("View revision"), button:has-text("revision")').first();
      if (await revisionBtn.isVisible()) {
        console.log('✓ Found revision button');
      }

      // Find Lex menu
      const lexMenu = page.locator('[aria-label*="Lex"]').first();
      if (await lexMenu.isVisible()) {
        console.log('✓ Found Lex menu');
      }

    } else {
      console.log('Could not find row');
    }

  } catch (e) {
    console.error('Error:', e);
    throw e;
  }
});
