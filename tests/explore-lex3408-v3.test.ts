import { test, expect } from '@playwright/test';
import * as fs from 'fs';

const runDir = '/Users/devansh.v/Workspace/lexful-ai/lexful-qa-opencode/runs/LEX-3408-20261019T094547Z-ce01';
const exploreDir = `${runDir}/explore`;

if (!fs.existsSync(exploreDir)) {
  fs.mkdirSync(exploreDir, { recursive: true });
}

test('LEX-3408: Explore root and find documents', async ({ page }) => {
  try {
    // Navigate to app root
    console.log('1. Navigating to app root...');
    await page.goto('https://e2e-test.uat.lexful.net/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    
    // Screenshot root
    await page.screenshot({ path: `${exploreDir}/01-app-root.png`, fullPage: true });
    console.log('✓ Screenshot: 01-app-root.png');

    // Check page text
    const bodyText = await page.evaluate(() => document.body.innerText.substring(0, 1000));
    console.log('Page content:', bodyText);

    // Look for navigation links
    const allLinks = await page.locator('a').all();
    console.log(`Found ${allLinks.length} links`);
    
    for (let i = 0; i < Math.min(allLinks.length, 10); i++) {
      const href = await allLinks[i].getAttribute('href');
      const text = await allLinks[i].textContent();
      console.log(`  Link ${i}: ${text} -> ${href}`);
    }

  } catch (e) {
    console.error('Error:', e);
    throw e;
  }
});

test('LEX-3408: Look for documents in all possible routes', async ({ page }) => {
  try {
    const routes = [
      '/',
      '/assets',
      '/assets/document',
      '/?type=document',
      '/assets?type=document',
      '/all/document',
      '/documents',
    ];

    for (const route of routes) {
      console.log(`\nTrying route: ${route}`);
      try {
        await page.goto(`https://e2e-test.uat.lexful.net${route}`, 
          { waitUntil: 'domcontentloaded', timeout: 5000 });
        await page.waitForTimeout(1000);
        
        const title = await page.title();
        const bodyText = await page.evaluate(() => document.body.innerText.substring(0, 200));
        
        console.log(`  Title: ${title}`);
        console.log(`  Content: ${bodyText}`);
        
        // Look for rows
        const rows = await page.locator('[role="row"]').count();
        console.log(`  Found ${rows} rows`);
        
        // If we found rows, take screenshot
        if (rows > 1) {
          const screenshotName = route.replace(/\//g, '-').substring(1) || 'root';
          await page.screenshot({ path: `${exploreDir}/route-${screenshotName}.png`, fullPage: true });
          console.log(`  ✓ Screenshot saved for route: ${route}`);
          
          // Look for document rows
          const firstRow = page.locator('[role="row"]').nth(1);
          if (await firstRow.isVisible()) {
            const rowText = await firstRow.textContent();
            console.log(`  First row: ${rowText?.substring(0, 100)}`);
          }
        }
      } catch (e: any) {
        console.log(`  Route failed: ${e.message}`);
      }
    }

  } catch (e) {
    console.error('Error:', e);
  }
});
