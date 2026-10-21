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

test('LEX-3408: Explore docs home and organization', async ({ page }) => {
  try {
    // Start at docs root
    console.log('1. Going to /docs/');
    await page.goto('https://e2e-test.uat.lexful.net/docs/', { 
      waitUntil: 'domcontentloaded',
      timeout: 10000
    });
    await page.waitForTimeout(2000);

    await page.screenshot({ path: `${exploreDir}/01-docs-home.png`, fullPage: true });

    const text = await page.evaluate(() => document.body.innerText.substring(0, 500));
    console.log('Docs home text:', text);

    // Look for organization links
    const orgLinks = await page.locator('a[href*="/d/"], button').all();
    console.log(`Found ${orgLinks.length} potential organization links`);

    for (let i = 0; i < Math.min(orgLinks.length, 10); i++) {
      const href = await orgLinks[i].getAttribute('href');
      const text = await orgLinks[i].textContent();
      console.log(`  ${i}: ${text} -> ${href}`);
    }

    // Try clicking an organization link
    const firstOrgLink = await page.locator('a[href*="/d/"]').first();
    if (await firstOrgLink.isVisible()) {
      const href = await firstOrgLink.getAttribute('href');
      console.log(`\n2. Clicking org link: ${href}`);
      await firstOrgLink.click();
      await page.waitForTimeout(2000);

      await page.screenshot({ path: `${exploreDir}/02-org-page.png`, fullPage: true });

      const orgPageText = await page.evaluate(() => document.body.innerText.substring(0, 500));
      console.log('Org page text:', orgPageText);
    }

  } catch (e) {
    console.error('Error:', e);
  }
});

test('LEX-3408: Navigate through sidebar', async ({ page }) => {
  try {
    await page.goto('https://e2e-test.uat.lexful.net/docs/', { 
      waitUntil: 'domcontentloaded',
      timeout: 10000
    });
    await page.waitForTimeout(2000);

    // Look for sidebar navigation
    const sidebarItems = await page.locator('nav a, nav button').all();
    console.log(`Found ${sidebarItems.length} sidebar items`);

    for (const item of sidebarItems) {
      const text = await item.textContent();
      const href = await item.getAttribute('href');
      console.log(`  - ${text} (${href})`);

      if (text?.toLowerCase().includes('asset') || text?.toLowerCase().includes('document')) {
        console.log(`\nClicking: ${text}`);
        await item.click();
        await page.waitForTimeout(2000);

        await page.screenshot({ path: `${exploreDir}/03-sidebar-${text?.toLowerCase().replace(/\s+/g, '-')}.png`, fullPage: true });
        break;
      }
    }

  } catch (e) {
    console.error('Error:', e);
  }
});

test('LEX-3408: Try direct document asset type navigation', async ({ page }) => {
  try {
    // Common pattern: /docs/d/{orgSlug}/{assetType}
    const routes = [
      '/docs/d/e2e-test', // e2e-test is the organization slug from the token
      '/docs/d/e2e-test/document',
      '/docs/d/all/assets',
      '/docs/d/all/assets/document',
    ];

    for (const route of routes) {
      console.log(`\nTrying: ${route}`);
      try {
        await page.goto(`https://e2e-test.uat.lexful.net${route}`, { 
          waitUntil: 'domcontentloaded',
          timeout: 8000
        });
        await page.waitForTimeout(2000);

        const url = page.url();
        const rows = await page.locator('[role="row"]').count();
        const text = await page.evaluate(() => document.body.innerText.substring(0, 200));

        console.log(`  URL: ${url}`);
        console.log(`  Rows: ${rows}`);
        console.log(`  Text: ${text}`);

        if (rows > 1 || text.length > 100) {
          const screenshotName = route.replace(/\//g, '_').substring(1);
          await page.screenshot({ path: `${exploreDir}/04-route_${screenshotName}.png`, fullPage: true });
          console.log(`  ✓ Saved screenshot`);
        }
      } catch (e: any) {
        console.log(`  Error: ${e.message}`);
      }
    }

  } catch (e) {
    console.error('Error:', e);
  }
});
