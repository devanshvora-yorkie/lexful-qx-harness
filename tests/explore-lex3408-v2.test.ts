import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';

const runDir = '/Users/devansh.v/Workspace/lexful-ai/lexful-qa-opencode/runs/LEX-3408-20261019T094547Z-ce01';
const exploreDir = `${runDir}/explore`;

// Ensure explore directory exists
if (!fs.existsSync(exploreDir)) {
  fs.mkdirSync(exploreDir, { recursive: true });
}

test('LEX-3408: Explore document actions and revisions', async ({ page }) => {
  try {
    // Navigate to documents page
    console.log('1. Navigating to documents page...');
    await page.goto('https://e2e-test.uat.lexful.net/d', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    
    // Wait for grid to load - look for any row
    console.log('2. Waiting for grid rows to load...');
    await page.waitForSelector('[role="row"]', { timeout: 10000 }).catch(() => {
      console.log('No rows found with role="row"');
    });
    
    // Screenshot documents page
    await page.screenshot({ path: `${exploreDir}/01-documents-grid.png`, fullPage: true });
    console.log('✓ Screenshot: 01-documents-grid.png');

    // Look for document rows
    console.log('3. Inspecting page content...');
    const bodyText = await page.evaluate(() => document.body.innerText.substring(0, 500));
    console.log('Page body (first 500 chars):', bodyText);

    // Try to find any clickable row in ag-grid
    const agRows = page.locator('[role="row"]');
    const rowCount = await agRows.count();
    console.log(`Found ${rowCount} rows`);

    // Try clicking on first row if it exists
    if (rowCount > 0) {
      const firstRow = agRows.nth(1); // Skip header row
      const firstRowText = await firstRow.textContent();
      console.log(`First row content: ${firstRowText}`);

      // Try clicking the row to open drawer
      console.log('4. Clicking first row to open drawer...');
      await firstRow.click({ force: true });
      await page.waitForTimeout(2000);

      // Screenshot drawer
      await page.screenshot({ path: `${exploreDir}/02-drawer-opened.png`, fullPage: true });
      console.log('✓ Screenshot: 02-drawer-opened.png');

      // Look for drawer content
      console.log('5. Exploring drawer elements...');
      
      // Look for actions button (ellipsis in header)
      const actionButtons = await page.locator('button[aria-label*="action"], button[aria-label*="Action"], [data-asset-drawer] button').all();
      console.log(`Found ${actionButtons.length} buttons in drawer`);
      
      // Look for specific drawer elements
      const drawer = page.locator('[data-asset-drawer]');
      if (await drawer.isVisible()) {
        console.log('✓ Found drawer element [data-asset-drawer]');
        
        // Look for revision section
        const revisionSection = page.locator('[aria-label*="Revision"]');
        if (await revisionSection.isVisible()) {
          console.log('✓ Found revision section');
        }
        
        // Look for Lex button
        const lexButton = page.locator('[aria-label*="Lex"]').first();
        if (await lexButton.isVisible()) {
          console.log('✓ Found Lex button');
        }
        
        // Look for actions/ellipsis menu
        const ellipsisBtn = page.locator('button[aria-label*="action"]').first();
        if (await ellipsisBtn.isVisible()) {
          console.log('✓ Found actions ellipsis button');
          await ellipsisBtn.screenshot({ path: `${exploreDir}/03-actions-ellipsis.png` });
        }

        // Screenshot to capture drawer structure
        await drawer.screenshot({ path: `${exploreDir}/04-drawer-structure.png` });
      }
    }

    // Take final screenshot
    await page.screenshot({ path: `${exploreDir}/05-final-state.png`, fullPage: true });
    console.log('✓ Screenshot: 05-final-state.png');

  } catch (e) {
    console.error('Error during exploration:', e);
    throw e;
  }
});

test('LEX-3408: Navigate via direct drawer URL', async ({ page }) => {
  try {
    // Try navigating directly to a drawer - we need to find a document ID first
    console.log('1. Getting all documents...');
    await page.goto('https://e2e-test.uat.lexful.net/d', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);

    // Look for drawer query param pattern in page
    const pageHTML = await page.content();
    
    // Try navigating to drawer with query parameters (common pattern: ?d=document)
    console.log('2. Trying drawer navigation patterns...');
    
    // Pattern 1: ?d=...&stack=...
    await page.goto('https://e2e-test.uat.lexful.net/?d=[%7B"type":"document"%7D]', 
      { waitUntil: 'domcontentloaded' }).catch(() => {
        console.log('Pattern 1 failed');
      });

    await page.waitForTimeout(1000);
    
    // Screenshot
    await page.screenshot({ path: `${exploreDir}/06-drawer-url-attempt.png`, fullPage: true });
    console.log('✓ Screenshot: 06-drawer-url-attempt.png');

  } catch (e) {
    console.error('Error during URL navigation:', e);
    // Don't fail on this one
  }
});
