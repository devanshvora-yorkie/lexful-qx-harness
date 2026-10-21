import { test } from '@playwright/test';
import * as fs from 'fs';

const runDir = '/Users/devansh.v/Workspace/lexful-ai/lexful-qa-opencode/runs/LEX-3408-20261019T094547Z-ce01';
const exploreDir = `${runDir}/explore`;

test.use({
  storageState: `${runDir}/auth-state.json`
});

test('debug-grid-loading', async ({ page }) => {
  await page.goto('https://e2e-test.uat.lexful.net/docs/d/all/assets', { 
    waitUntil: 'domcontentloaded'
  });

  // Wait longer and check what's loading
  for (let i = 0; i < 5; i++) {
    await page.waitForTimeout(2000);
    
    const pageState = await page.evaluate(() => ({
      title: document.title,
      bodySummary: document.body.innerText.substring(0, 300),
      gridElements: document.querySelectorAll('[role="grid"], [role="table"], [class*="ag-"]').length,
      rowElements: document.querySelectorAll('[role="row"]').length,
      cellElements: document.querySelectorAll('[role="gridcell"]').length,
      allText: document.body.innerText.includes('Documents 96'),
    }));

    console.log(`Attempt ${i + 1}:`, JSON.stringify(pageState));

    if (pageState.rowElements > 0) {
      console.log('✓ Rows found!');
      break;
    }
  }

  await page.screenshot({ path: `${exploreDir}/debug-grid-state.png`, fullPage: true });

  // Try to trigger loading by clicking on something
  console.log('\nTrying to find navigation element...');
  const allElements = await page.evaluate(() => {
    const allText = Array.from(document.querySelectorAll('button, a, [role="button"]')).map(el => ({
      text: el.textContent?.trim().substring(0, 50),
      href: el.getAttribute('href'),
      onclick: !!el.onclick
    }));
    return allText.slice(0, 20);
  });

  console.log('Elements:', JSON.stringify(allElements, null, 2));
});
