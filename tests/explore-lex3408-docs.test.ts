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

test('LEX-3408: Navigate to document assets and explore drawer', async ({ page }) => {
  try {
    // Go to assets overview
    console.log('1. Navigating to /docs/d/all/assets...');
    await page.goto('https://e2e-test.uat.lexful.net/docs/d/all/assets', { 
      waitUntil: 'domcontentloaded',
      timeout: 10000
    });
    await page.waitForTimeout(2000);

    await page.screenshot({ path: `${exploreDir}/01-assets-overview.png`, fullPage: true });
    console.log('✓ Screenshot: 01-assets-overview.png');

    // Click on Documents category
    console.log('2. Looking for Documents section...');
    const docsLink = page.locator('button, a', { hasText: 'Documents' }).first();
    if (await docsLink.isVisible()) {
      console.log('Found Documents link, clicking...');
      await docsLink.click();
      await page.waitForTimeout(2000);

      await page.screenshot({ path: `${exploreDir}/02-documents-section.png`, fullPage: true });
      console.log('✓ Screenshot: 02-documents-section.png');
    }

    // Look for document rows in grid
    console.log('3. Waiting for document rows...');
    await page.waitForTimeout(2000);

    const rows = await page.locator('[role="row"]').count();
    console.log(`Found ${rows} rows`);

    if (rows > 1) {
      // Get first data row
      const firstDataRow = page.locator('[role="row"]').nth(1);
      const rowText = await firstDataRow.textContent();
      console.log(`First row: ${rowText?.substring(0, 150)}`);

      // Click to open document in drawer
      console.log('4. Clicking first document row to open drawer...');
      await firstDataRow.click();
      await page.waitForTimeout(2000);

      await page.screenshot({ path: `${exploreDir}/03-document-drawer.png`, fullPage: true });
      console.log('✓ Screenshot: 03-document-drawer.png');

      // Get drawer URL
      const drawerUrl = page.url();
      console.log(`Drawer URL: ${drawerUrl}`);

      // Now explore drawer elements
      console.log('5. Exploring drawer structure...');

      // Look for drawer
      const drawer = page.locator('[data-asset-drawer]');
      if (await drawer.isVisible()) {
        console.log('✓ Found drawer [data-asset-drawer]');

        // Get drawer content snippet
        const drawerHTML = await drawer.evaluate(el => {
          const allButtons = el.querySelectorAll('button');
          const allSections = el.querySelectorAll('[aria-label*="revision"], [aria-label*="Revision"], [aria-label*="history"]');
          return {
            buttonCount: allButtons.length,
            hasRevisionSection: allSections.length > 0,
            buttonLabels: Array.from(allButtons).map(btn => ({
              label: btn.getAttribute('aria-label'),
              title: btn.getAttribute('title'),
              text: btn.textContent?.substring(0, 30)
            }))
          };
        });

        console.log('Drawer structure:', JSON.stringify(drawerHTML, null, 2));

        // Take drawer header screenshot
        const header = drawer.locator('header').first();
        if (await header.isVisible()) {
          await header.screenshot({ path: `${exploreDir}/04-drawer-header.png` });
          console.log('✓ Screenshot: 04-drawer-header.png');
        }

        // Find actions/ellipsis button
        console.log('6. Looking for actions menu...');
        const actionBtn = drawer.locator('button[aria-label*="action"], button[aria-label*="Action"]').first();
        if (await actionBtn.isVisible()) {
          console.log('✓ Found actions button');
          await actionBtn.screenshot({ path: `${exploreDir}/05-actions-button.png` });

          // Click to open menu
          await actionBtn.click();
          await page.waitForTimeout(1000);

          await page.screenshot({ path: `${exploreDir}/06-actions-menu.png`, fullPage: true });
          console.log('✓ Screenshot: 06-actions-menu.png');

          // Get menu items
          const menuItems = await page.locator('[role="menuitem"]').allTextContents();
          console.log('Menu items:', menuItems);
        }

        // Look for Lex menu
        console.log('7. Looking for Lex menu...');
        const lexBtn = drawer.locator('[aria-label*="Lex"]').first();
        if (await lexBtn.isVisible()) {
          console.log('✓ Found Lex button');
          await lexBtn.screenshot({ path: `${exploreDir}/07-lex-button.png` });
        }

        // Look for revision section
        console.log('8. Looking for revision preview section...');
        const revisionSection = drawer.locator('[aria-label*="revision"], [aria-label*="Revision"]').first();
        if (await revisionSection.isVisible()) {
          console.log('✓ Found revision section');
          await revisionSection.screenshot({ path: `${exploreDir}/08-revision-section.png` });
        }

        // Look for download button
        console.log('9. Looking for download button...');
        const downloadBtn = drawer.locator('button:has-text("Download"), [aria-label*="Download"]').first();
        if (await downloadBtn.isVisible()) {
          console.log('✓ Found download button');
        }
      }

    } else {
      console.log('No rows found in grid');
    }

    await page.screenshot({ path: `${exploreDir}/09-final-state.png`, fullPage: true });

  } catch (e) {
    console.error('Error:', e);
    throw e;
  }
});

test('LEX-3408: Test revision actions and Lex handoff', async ({ page }) => {
  try {
    // Navigate to documents
    await page.goto('https://e2e-test.uat.lexful.net/docs/d/all/assets', { 
      waitUntil: 'domcontentloaded',
      timeout: 10000
    });
    await page.waitForTimeout(3000);

    // Find and click a document
    const firstRow = page.locator('[role="row"]').nth(1);
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForTimeout(2000);

      const drawer = page.locator('[data-asset-drawer]');
      if (await drawer.isVisible()) {
        // Look for "View revision" button
        console.log('Looking for revision history...');
        const viewRevBtn = drawer.locator('button:has-text("View revision")').first();
        if (await viewRevBtn.isVisible()) {
          console.log('✓ Found "View revision" button');
          await viewRevBtn.screenshot({ path: `${exploreDir}/10-view-revision-btn.png` });

          // Click to see revision preview
          await viewRevBtn.click();
          await page.waitForTimeout(1000);

          await page.screenshot({ path: `${exploreDir}/11-revision-preview.png`, fullPage: true });
          console.log('✓ Screenshot: 11-revision-preview.png');

          // Look for "Exit history" button
          const exitBtn = drawer.locator('button:has-text("Exit history")').first();
          if (await exitBtn.isVisible()) {
            console.log('✓ Found "Exit history" button');
            await exitBtn.click();
            await page.waitForTimeout(1000);
          }
        }

        // Test Lex/Ask Lex
        console.log('\nTesting Lex handoff...');
        const lexBtn = drawer.locator('[aria-label*="Lex"]').first();
        if (await lexBtn.isVisible()) {
          // Check if there's a menu
          const lexMenu = drawer.locator('[aria-label*="Lex Actions"]');
          if (await lexMenu.isVisible()) {
            console.log('✓ Found Lex Actions menu');
            await lexMenu.click();
            await page.waitForTimeout(1000);

            await page.screenshot({ path: `${exploreDir}/12-lex-menu-open.png`, fullPage: true });
          }
        }

        // Look for document content/editor
        console.log('\nLooking for document content...');
        const richText = drawer.locator('[role="textbox"], [class*="editor"], [class*="content"]').first();
        if (await richText.isVisible()) {
          console.log('✓ Found document content area');
        }
      }
    }

  } catch (e) {
    console.error('Error:', e);
  }
});

test('LEX-3408: Explore drawer URL pattern and query params', async ({ page }) => {
  try {
    // Get to a document in drawer
    await page.goto('https://e2e-test.uat.lexful.net/docs/d/all/assets', { 
      waitUntil: 'domcontentloaded',
      timeout: 10000
    });
    await page.waitForTimeout(2000);

    const firstRow = page.locator('[role="row"]').nth(1);
    if (await firstRow.isVisible()) {
      await firstRow.click();
      await page.waitForTimeout(2000);

      // Get the drawer URL
      const drawerUrl = page.url();
      console.log('Drawer URL:', drawerUrl);

      // Parse query parameters
      const urlObj = new URL(drawerUrl);
      const params = urlObj.searchParams;
      
      console.log('\nQuery parameters:');
      for (const [key, value] of params.entries()) {
        console.log(`  ${key}=${value.substring(0, 150)}${value.length > 150 ? '...' : ''}`);
        
        // Try to parse JSON values
        try {
          const parsed = JSON.parse(decodeURIComponent(value));
          console.log(`    (parsed): ${JSON.stringify(parsed, null, 6).substring(0, 200)}`);
        } catch {}
      }

      // Screenshot showing URL
      await page.screenshot({ path: `${exploreDir}/13-drawer-url.png`, fullPage: true });
    }

  } catch (e) {
    console.error('Error:', e);
  }
});
