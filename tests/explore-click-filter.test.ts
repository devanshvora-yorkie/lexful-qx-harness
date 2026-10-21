import { test } from '@playwright/test';
import * as fs from 'fs';

const runDir = '/Users/devansh.v/Workspace/lexful-ai/lexful-qa-opencode/runs/LEX-3408-20261019T094547Z-ce01';
const exploreDir = `${runDir}/explore`;

test.use({
  storageState: `${runDir}/auth-state.json`
});

test('click-documents-category', async ({ page }) => {
  await page.goto('https://e2e-test.uat.lexful.net/docs/d/all/assets', { 
    waitUntil: 'domcontentloaded'
  });
  await page.waitForTimeout(2000);

  // Look for "Documents" text and click on parent area
  console.log('Looking for Documents label/button...');
  
  // Search for element containing "Documents"
  const elementsWithDocs = await page.evaluate(() => {
    const elements = Array.from(document.querySelectorAll('*')).filter(el => 
      el.textContent?.includes('Documents') && el.textContent.length < 100
    );
    return elements.map(el => ({
      tag: el.tagName,
      text: el.textContent,
      className: el.className,
      isButton: el.getAttribute('role') === 'button' || el.tagName === 'BUTTON'
    }));
  });

  console.log('Elements with "Documents":', JSON.stringify(elementsWithDocs, null, 2));

  // Try clicking something that has Documents
  const docLink = page.locator('text=Documents').first();
  if (await docLink.isVisible()) {
    console.log('Found Documents text, looking for parent clickable...');
    
    // Try to find parent button/link
    const parent = docLink.locator('..');
    if (await parent.isVisible()) {
      console.log('Clicking Documents...');
      await parent.click();
      await page.waitForTimeout(2000);

      // Check for rows
      const rows = await page.locator('[role="row"]').count();
      console.log(`After clicking Documents: ${rows} rows`);

      if (rows > 0) {
        console.log('✓ Grid loaded with rows!');
        await page.screenshot({ path: `${exploreDir}/docs-grid-loaded.png`, fullPage: true });
      }
    }
  }
});

test('navigate-docs-asset-type', async ({ page }) => {
  // Try direct navigation to document asset type
  await page.goto('https://e2e-test.uat.lexful.net/docs/d/all/assets?assetType=document', { 
    waitUntil: 'domcontentloaded'
  });
  await page.waitForTimeout(3000);

  const rows = await page.locator('[role="row"]').count();
  console.log(`With assetType=document: ${rows} rows`);

  if (rows > 0) {
    console.log('✓ Found rows with assetType parameter!');
    
    // Click first row
    const firstRow = page.locator('[role="row"]').nth(1);
    await firstRow.click();
    await page.waitForTimeout(2000);

    const url = page.url();
    console.log(`Drawer URL: ${url}`);

    // Check drawer
    const drawer = page.locator('[data-asset-drawer]');
    if (await drawer.isVisible()) {
      console.log('✓ Drawer opened');
      
      // Get document name and drawer info
      const info = await drawer.evaluate(el => {
        const name = el.querySelector('h1, h2, [class*="title"]')?.textContent?.trim();
        const buttons = Array.from(el.querySelectorAll('button')).map(b => ({
          label: b.getAttribute('aria-label'),
          text: b.textContent?.trim()
        }));
        return { name, buttonCount: buttons.length, buttons: buttons.slice(0, 10) };
      });

      console.log('=== DRAWER INFO ===');
      console.log(JSON.stringify(info, null, 2));

      await page.screenshot({ path: `${exploreDir}/drawer-with-query-param.png`, fullPage: true });
    }
  }
});
