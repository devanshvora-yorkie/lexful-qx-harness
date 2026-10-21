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

test('LEX-3408: Inspect assets page structure', async ({ page }) => {
  try {
    // Navigate to assets
    await page.goto('https://e2e-test.uat.lexful.net/docs/assets', { 
      waitUntil: 'domcontentloaded',
      timeout: 10000
    });
    await page.waitForTimeout(2000);

    // Get full page structure
    const structure = await page.evaluate(() => {
      const info = {
        title: document.title,
        url: window.location.href,
        text: document.body.innerText.substring(0, 1000),
        mainDivs: Array.from(document.querySelectorAll('div[class*="container"], main, [role="main"]')).map(el => ({
          tag: el.tagName,
          class: el.className.substring(0, 100),
          text: el.innerText?.substring(0, 50) || ''
        })),
        allButtons: Array.from(document.querySelectorAll('button, a[role="button"]')).map((el: any) => ({
          text: el.textContent?.substring(0, 50) || '',
          ariaLabel: el.getAttribute('aria-label') || '',
          href: el.getAttribute('href') || '',
          className: el.className.substring(0, 50)
        })).slice(0, 15)
      };
      return info;
    });

    console.log('Page structure:');
    console.log(JSON.stringify(structure, null, 2));

    // Take screenshot
    await page.screenshot({ path: `${exploreDir}/01-assets-structure.png`, fullPage: true });

  } catch (e) {
    console.error('Error:', e);
    throw e;
  }
});

test('LEX-3408: Try navigating with query parameters', async ({ page }) => {
  try {
    // Try with query parameter for document type
    console.log('Trying /docs/assets?type=document');
    await page.goto('https://e2e-test.uat.lexful.net/docs/assets?type=document', { 
      waitUntil: 'domcontentloaded',
      timeout: 10000
    });
    await page.waitForTimeout(2000);

    await page.screenshot({ path: `${exploreDir}/02-with-query.png`, fullPage: true });

    const text = await page.evaluate(() => document.body.innerText.substring(0, 500));
    console.log('Page text:', text);

    // Try clicking on Assets menu
    console.log('Looking for Assets menu option...');
    const assetsLink = page.locator('a:has-text("Assets")');
    if (await assetsLink.isVisible()) {
      console.log('Found Assets link, clicking...');
      await assetsLink.click();
      await page.waitForTimeout(2000);
      await page.screenshot({ path: `${exploreDir}/03-after-assets-click.png`, fullPage: true });
    }

  } catch (e) {
    console.error('Error:', e);
  }
});

test('LEX-3408: Try direct navigation with organization slug', async ({ page }) => {
  try {
    // Try with common patterns
    const routes = [
      '/docs/d/all/assets',
      '/docs/d/all',
      '/docs/assets/all',
      '/docs/assets/all/document',
    ];

    for (const route of routes) {
      console.log(`\nTrying: ${route}`);
      try {
        await page.goto(`https://e2e-test.uat.lexful.net${route}`, { 
          waitUntil: 'domcontentloaded',
          timeout: 8000
        });
        await page.waitForTimeout(1000);

        const url = page.url();
        const text = await page.evaluate(() => document.body.innerText.substring(0, 200));
        console.log(`  URL: ${url}`);
        console.log(`  Text: ${text}`);

        const rows = await page.locator('[role="row"]').count();
        console.log(`  Rows found: ${rows}`);

        if (rows > 0) {
          const screenshotName = route.replace(/\//g, '_').substring(1);
          await page.screenshot({ path: `${exploreDir}/route_${screenshotName}.png`, fullPage: true });
          console.log(`  ✓ Saved screenshot`);
          break;
        }
      } catch (e: any) {
        console.log(`  Failed: ${e.message}`);
      }
    }

  } catch (e) {
    console.error('Error:', e);
  }
});
