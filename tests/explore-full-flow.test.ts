import { test } from '@playwright/test';

const runDir = '/Users/devansh.v/Workspace/lexful-ai/lexful-qa-opencode/runs/LEX-3408-20261019T094547Z-ce01';

test.use({ storageState: `${runDir}/auth-state.json` });

test('full-navigation-flow', async ({ page }) => {
  // Start at root
  await page.goto('https://e2e-test.uat.lexful.net/docs/', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);

  // Click Assets link
  const assetsLink = page.locator('a:has-text("Assets")').first();
  if (await assetsLink.isVisible()) {
    console.log('Clicking Assets...');
    await assetsLink.click();
    await page.waitForTimeout(3000);

    let rows = await page.locator('[role="row"]').count();
    console.log(`After Assets link: ${rows} rows`);

    // Wait more and retry
    if (rows === 0) {
      await page.waitForTimeout(3000);
      rows = await page.locator('[role="row"]').count();
      console.log(`After extra wait: ${rows} rows`);
    }

    if (rows > 0) {
      console.log(`✓ Found ${rows} rows!`);
      const firstRow = page.locator('[role="row"]').nth(1);
      const text = await firstRow.textContent();
      console.log(`First row: ${text?.substring(0, 120)}`);
      
      // Take screenshot before clicking
      await page.screenshot({ path: `${runDir}/explore/before-click.png`, fullPage: true });
      
      // Click first row
      await firstRow.click();
      await page.waitForTimeout(2000);

      const url = page.url();
      console.log(`DRAWER URL: ${url}`);

      // Parse params
      const urlObj = new URL(url);
      for (const [k, v] of urlObj.searchParams) {
        console.log(`PARAM ${k}: ${v.substring(0, 80)}`);
      }

      // Check for drawer and capture elements
      const drawer = page.locator('[data-asset-drawer]');
      if (await drawer.isVisible()) {
        console.log('✓ Drawer is visible!');
        
        const info = await drawer.evaluate(el => {
          const h = el.querySelector('h1, h2, [class*="title"], [class*="name"]');
          const docName = h?.textContent?.trim();
          const buttons = Array.from(el.querySelectorAll('button')).map(b => ({
            label: b.getAttribute('aria-label') || '',
            title: b.getAttribute('title') || '',
            text: b.textContent?.trim().substring(0, 30) || ''
          }));
          return {
            documentName: docName?.substring(0, 100),
            buttons: buttons.slice(0, 15)
          };
        });

        console.log('=== DRAWER ELEMENTS ===');
        console.log(JSON.stringify(info, null, 2));

        await page.screenshot({ path: `${runDir}/explore/drawer-opened.png`, fullPage: true });
      }
    } else {
      console.log('No rows found');
    }
  } else {
    console.log('Assets link not visible');
  }
});
