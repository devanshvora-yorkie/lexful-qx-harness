import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';

const runDir = '/Users/devansh.v/Workspace/lexful-ai/lexful-qa-opencode/runs/LEX-3408-20261019T094547Z-ce01';
const exploreDir = `${runDir}/explore`;

// Ensure explore directory exists
if (!fs.existsSync(exploreDir)) {
  fs.mkdirSync(exploreDir, { recursive: true });
}

test('LEX-3408: Navigate to documents and explore drawer', async ({ page }) => {
  try {
    // Test 1: Navigate to documents page
    console.log('1. Navigating to documents page...');
    await page.goto('https://e2e-test.uat.lexful.net/d', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    
    // Screenshot documents page
    await page.screenshot({ path: `${exploreDir}/01-documents-grid.png`, fullPage: true });
    console.log('✓ Screenshot: 01-documents-grid.png');

    // Look for a document to open
    const docLinks = page.locator('a[href*="/d/"]');
    const linkCount = await docLinks.count();
    console.log(`Found ${linkCount} document links`);

    if (linkCount > 0) {
      // Get the first document link's href
      const firstLink = docLinks.first();
      const href = await firstLink.getAttribute('href');
      console.log(`First document link: ${href}`);

      // Click to open the document drawer
      console.log('2. Clicking on first document...');
      await firstLink.click();
      await page.waitForTimeout(2000);
      
      // Screenshot drawer
      await page.screenshot({ path: `${exploreDir}/02-drawer-opened.png`, fullPage: true });
      console.log('✓ Screenshot: 02-drawer-opened.png');

      // Look for drawer actions button (ellipsis)
      console.log('3. Looking for actions menu...');
      const ellipsis = page.locator('[aria-label*="Action"], [aria-label*="More"], button:has-text("⋯")').first();
      if (await ellipsis.isVisible()) {
        console.log('Found ellipsis button');
        await ellipsis.screenshot({ path: `${exploreDir}/03-ellipsis-button.png` });
      }

      // Look for revision history button
      console.log('4. Looking for revision history...');
      const revisionBtn = page.locator('button:has-text("View revision"), button:has-text("revision")').first();
      if (await revisionBtn.isVisible()) {
        console.log('Found revision button');
      }

      // Look for Lex menu/button
      console.log('5. Looking for Lex menu...');
      const lexBtn = page.locator('[aria-label*="Lex"], button:has-text("Lex")').first();
      if (await lexBtn.isVisible()) {
        console.log('Found Lex button');
      }

      // Look for download button
      console.log('6. Looking for download button...');
      const downloadBtn = page.locator('button:has-text("Download"), [aria-label*="Download"]').first();
      if (await downloadBtn.isVisible()) {
        console.log('Found download button');
      }
    }

    // Screenshot to show current state
    await page.screenshot({ path: `${exploreDir}/04-final-state.png`, fullPage: true });
    console.log('✓ Screenshot: 04-final-state.png');

  } catch (e) {
    console.error('Error during exploration:', e);
    throw e;
  }
});
