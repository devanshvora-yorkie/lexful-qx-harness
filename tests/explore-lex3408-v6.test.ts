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

test('LEX-3408: Examine DOM structure', async ({ page }) => {
  try {
    // Navigate
    await page.goto('https://e2e-test.uat.lexful.net/docs/assets/document', { 
      waitUntil: 'domcontentloaded',
      timeout: 10000
    });
    await page.waitForTimeout(3000);

    // Get full HTML structure
    const html = await page.evaluate(() => {
      const body = document.body;
      return {
        htmlLength: body.innerHTML.length,
        textLength: body.innerText.length,
        classes: Array.from(body.classList),
        id: body.id,
        childCount: body.children.length,
        firstChildren: Array.from(body.children).slice(0, 5).map((el: any) => ({
          tag: el.tagName,
          class: el.className,
          id: el.id,
          text: el.innerText?.substring(0, 50) || ''
        }))
      };
    });

    console.log('DOM Structure:', JSON.stringify(html, null, 2));

    // Check for specific elements
    const checks = {
      '#root': await page.locator('#root').count(),
      '[data-testid]': await page.locator('[data-testid]').count(),
      'main': await page.locator('main').count(),
      'nav': await page.locator('nav').count(),
      'button': await page.locator('button').count(),
      '[role="grid"]': await page.locator('[role="grid"]').count(),
      '[role="table"]': await page.locator('[role="table"]').count(),
      '[class*="grid"]': await page.locator('[class*="grid"]').count(),
      '[class*="ag-"]': await page.locator('[class*="ag-"]').count(),
    };

    console.log('Element counts:', checks);

    // Get all visible text
    const fullText = await page.evaluate(() => document.body.innerText);
    console.log(`Full text (first 1000 chars):\n${fullText.substring(0, 1000)}`);

    // Screenshot
    await page.screenshot({ path: `${exploreDir}/01-dom-structure.png`, fullPage: true });

    // Try to find clickable elements
    const clickables = await page.evaluate(() => {
      const elements = Array.from(document.querySelectorAll('a, button, [role="button"], [role="row"]'));
      return elements.slice(0, 20).map(el => ({
        tag: el.tagName,
        role: el.getAttribute('role'),
        text: el.textContent?.substring(0, 50) || '',
        href: el.getAttribute('href') || '',
        ariaLabel: el.getAttribute('aria-label') || '',
        className: el.className.substring(0, 50)
      }));
    });

    console.log('First 20 clickable elements:', JSON.stringify(clickables, null, 2));

  } catch (e) {
    console.error('Error:', e);
    throw e;
  }
});
