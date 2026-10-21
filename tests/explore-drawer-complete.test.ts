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

test('1-open-document-and-capture-drawer', async ({ page }) => {
  // Navigate to assets
  await page.goto('https://e2e-test.uat.lexful.net/docs/d/all/assets', { 
    waitUntil: 'domcontentloaded'
  });
  await page.waitForTimeout(3000);

  // Wait for actual grid row by looking for document name text
  console.log('Waiting for grid row with real document data...');
  await page.waitForSelector('[role="row"] [role="gridcell"]', { timeout: 10000 }).catch(() => {
    console.log('Timeout waiting for grid cells');
  });
  await page.waitForTimeout(2000);

  // Get all rows and click first data row
  const rows = await page.locator('[role="row"]').all();
  console.log(`Found ${rows.length} rows total`);

  if (rows.length > 1) {
    // Click first data row (skip header at index 0)
    const firstRow = rows[1];
    const rowText = await firstRow.textContent();
    console.log(`Opening document: ${rowText?.substring(0, 100)}`);
    
    await firstRow.click();
    await page.waitForTimeout(2000);

    // Capture drawer URL and structure
    const drawerUrl = page.url();
    console.log(`DRAWER URL: ${drawerUrl}`);

    // Extract query parameters
    const urlObj = new URL(drawerUrl);
    for (const [key, val] of urlObj.searchParams.entries()) {
      console.log(`PARAM ${key}: ${val.substring(0, 100)}`);
    }

    // Snapshot drawer with text output
    const drawerInfo = await page.evaluate(() => {
      const drawer = document.querySelector('[data-asset-drawer]');
      if (!drawer) return null;
      
      return {
        documentName: drawer.querySelector('[class*="title"], h1, h2')?.textContent?.trim(),
        buttons: Array.from(drawer.querySelectorAll('button')).map(btn => ({
          ariaLabel: btn.getAttribute('aria-label'),
          title: btn.getAttribute('title'),
          text: btn.textContent?.trim(),
          className: btn.className
        })).slice(0, 15),
        hasDownload: !!Array.from(drawer.querySelectorAll('button')).find(b => 
          b.textContent?.includes('Download') || b.getAttribute('aria-label')?.includes('Download')
        ),
        hasLex: !!Array.from(drawer.querySelectorAll('button')).find(b =>
          b.getAttribute('aria-label')?.includes('Lex')
        ),
        hasTags: !!drawer.querySelector('[aria-label*="tag"], [class*="tag"]'),
        sections: Array.from(drawer.querySelectorAll('[aria-label], [role="region"]')).map(s => ({
          ariaLabel: s.getAttribute('aria-label'),
          role: s.getAttribute('role'),
          text: s.textContent?.substring(0, 50)
        })).slice(0, 10)
      };
    });

    console.log('=== DRAWER SNAPSHOT ===');
    console.log(JSON.stringify(drawerInfo, null, 2));
    
    await page.screenshot({ path: `${exploreDir}/drawer-01-open.png`, fullPage: true });
  }
});

test('2-explore-actions-menu', async ({ page }) => {
  await page.goto('https://e2e-test.uat.lexful.net/docs/d/all/assets', { 
    waitUntil: 'domcontentloaded'
  });
  await page.waitForTimeout(3000);

  // Open first document
  const rows = await page.locator('[role="row"]').all();
  if (rows.length > 1) {
    await rows[1].click();
    await page.waitForTimeout(2000);

    // Find and click actions menu
    const drawer = page.locator('[data-asset-drawer]');
    
    // Look for ellipsis/actions button
    const allButtons = await drawer.locator('button').all();
    console.log(`Found ${allButtons.length} buttons in drawer`);
    
    let actionBtn = null;
    for (const btn of allButtons) {
      const label = await btn.getAttribute('aria-label');
      const title = await btn.getAttribute('title');
      if (label?.toLowerCase().includes('action') || label?.toLowerCase().includes('more') ||
          title?.toLowerCase().includes('action') || title?.toLowerCase().includes('more')) {
        actionBtn = btn;
        console.log(`Found actions button: aria-label="${label}", title="${title}"`);
        break;
      }
    }

    if (actionBtn) {
      await actionBtn.click();
      await page.waitForTimeout(1000);

      // Capture menu items
      const menuItems = await page.locator('[role="menuitem"]').allTextContents();
      console.log('=== ACTIONS MENU ITEMS ===');
      menuItems.forEach(item => console.log(`- ${item.trim()}`));

      await page.screenshot({ path: `${exploreDir}/drawer-02-actions-menu.png`, fullPage: true });
    } else {
      console.log('No actions button found');
    }
  }
});

test('3-find-document-with-revisions', async ({ page }) => {
  await page.goto('https://e2e-test.uat.lexful.net/docs/d/all/assets', { 
    waitUntil: 'domcontentloaded'
  });
  await page.waitForTimeout(3000);

  // Try multiple rows to find one with revisions
  const rows = await page.locator('[role="row"]').all();
  console.log(`Checking ${Math.min(rows.length, 5)} rows for revisions...`);

  for (let i = 1; i < Math.min(rows.length, 6); i++) {
    const row = rows[i];
    await row.click();
    await page.waitForTimeout(1500);

    // Look for revision button
    const viewRevBtn = page.locator('[data-asset-drawer] button:has-text("View revision")').first();
    if (await viewRevBtn.isVisible()) {
      const rowText = await row.textContent();
      console.log(`Found document with revisions: ${rowText?.substring(0, 80)}`);

      // Capture revision section info
      const revisionInfo = await page.evaluate(() => {
        const drawer = document.querySelector('[data-asset-drawer]');
        return {
          hasViewRevisionBtn: !!drawer?.querySelector('button:contains("View revision")'),
          revisionSections: Array.from(drawer?.querySelectorAll('[aria-label*="revision"], [aria-label*="Revision"]') || []).map(s => ({
            tag: s.tagName,
            ariaLabel: s.getAttribute('aria-label'),
            text: s.textContent?.substring(0, 50)
          })),
          revisionItems: Array.from(drawer?.querySelectorAll('[aria-pressed]') || []).map(item => ({
            ariaPressed: item.getAttribute('aria-pressed'),
            text: item.textContent?.substring(0, 50)
          }))
        };
      });

      console.log('=== REVISION INFO ===');
      console.log(JSON.stringify(revisionInfo, null, 2));

      await page.screenshot({ path: `${exploreDir}/drawer-03-revisions.png`, fullPage: true });
      break;
    }

    // Go back to list
    const backBtn = page.locator('button[aria-label*="back"], button[aria-label*="close"]').first();
    if (await backBtn.isVisible()) {
      await backBtn.click();
      await page.waitForTimeout(1000);
    } else {
      // Use Escape to close
      await page.keyboard.press('Escape');
      await page.waitForTimeout(1000);
    }
  }
});

test('4-lex-menu-and-selection', async ({ page }) => {
  await page.goto('https://e2e-test.uat.lexful.net/docs/d/all/assets', { 
    waitUntil: 'domcontentloaded'
  });
  await page.waitForTimeout(3000);

  // Open document
  const rows = await page.locator('[role="row"]').all();
  if (rows.length > 1) {
    await rows[1].click();
    await page.waitForTimeout(2000);

    // Find Lex menu
    const drawer = page.locator('[data-asset-drawer]');
    const lexBtn = drawer.locator('[aria-label*="Lex"]').first();
    
    if (await lexBtn.isVisible()) {
      console.log('Found Lex button');
      
      // Check if it's a menu trigger
      const label = await lexBtn.getAttribute('aria-label');
      const title = await lexBtn.getAttribute('title');
      console.log(`Lex button: aria-label="${label}", title="${title}"`);

      // Click to see menu
      await lexBtn.click();
      await page.waitForTimeout(1000);

      const lexMenuItems = await page.locator('[role="menuitem"]').allTextContents();
      console.log('=== LEX MENU ITEMS ===');
      lexMenuItems.forEach(item => console.log(`- ${item.trim()}`));

      await page.screenshot({ path: `${exploreDir}/drawer-04-lex-menu.png`, fullPage: true });
    }

    // Try edit mode to see Lex in different context
    const editBtn = drawer.locator('button:has-text("Edit"), [aria-label*="edit"]').first();
    if (await editBtn.isVisible()) {
      console.log('Found Edit button, clicking to enter edit mode...');
      await editBtn.click();
      await page.waitForTimeout(1500);

      // Look for Lex in edit mode
      const editLexBtn = drawer.locator('[aria-label*="Lex"]').first();
      if (await editLexBtn.isVisible()) {
        console.log('Found Lex button in edit mode');
        await page.screenshot({ path: `${exploreDir}/drawer-05-edit-mode-lex.png`, fullPage: true });
      }
    }
  }
});

test('5-search-and-bulk-actions', async ({ page }) => {
  await page.goto('https://e2e-test.uat.lexful.net/docs/d/all/assets', { 
    waitUntil: 'domcontentloaded'
  });
  await page.waitForTimeout(3000);

  // Look for search input
  const searchInput = page.locator('input[placeholder*="Search"], [aria-label*="search"]').first();
  if (await searchInput.isVisible()) {
    console.log('Found search input');
    
    // Look for "Ask Lex" button near search
    const askLexBtn = page.locator('button:has-text("Ask Lex"), [aria-label*="Ask Lex"]').first();
    if (await askLexBtn.isVisible()) {
      console.log('Found "Ask Lex" button');
      const label = await askLexBtn.getAttribute('aria-label');
      const title = await askLexBtn.getAttribute('title');
      console.log(`Ask Lex: aria-label="${label}", title="${title}"`);
    }
  }

  // Look for bulk action bar
  const rows = await page.locator('[role="row"]').all();
  if (rows.length > 1) {
    // Try clicking checkbox in first row
    const firstRow = rows[1];
    const checkbox = firstRow.locator('input[type="checkbox"], [role="checkbox"]').first();
    
    if (await checkbox.isVisible()) {
      console.log('Found checkbox, clicking to select row...');
      await checkbox.click();
      await page.waitForTimeout(1000);

      // Look for bulk action bar
      const bulkBar = page.locator('[class*="bulk"], [aria-label*="action"]').first();
      if (await bulkBar.isVisible()) {
        console.log('Found bulk action bar');
        
        // Look for "More actions" or "Duplicate"
        const moreBtn = page.locator('button:has-text("More actions"), button:has-text("Duplicate")').first();
        if (await moreBtn.isVisible()) {
          const text = await moreBtn.textContent();
          console.log(`Found button: "${text?.trim()}"`);
        }

        await page.screenshot({ path: `${exploreDir}/drawer-06-bulk-actions.png`, fullPage: true });
      }
    }
  }
});

test('6-tag-edit-hover', async ({ page }) => {
  await page.goto('https://e2e-test.uat.lexful.net/docs/d/all/assets', { 
    waitUntil: 'domcontentloaded'
  });
  await page.waitForTimeout(3000);

  // Open a document
  const rows = await page.locator('[role="row"]').all();
  if (rows.length > 1) {
    await rows[1].click();
    await page.waitForTimeout(2000);

    // Look for tags
    const drawer = page.locator('[data-asset-drawer]');
    const tagsArea = drawer.locator('[class*="tag"], [aria-label*="tag"]').first();
    
    if (await tagsArea.isVisible()) {
      console.log('Found tags area');
      
      // Get tag structure
      const tagInfo = await drawer.evaluate(() => {
        const tags = document.querySelectorAll('[class*="tag"], [role*="tag"]');
        return {
          tagCount: tags.length,
          tags: Array.from(tags).map(tag => ({
            text: tag.textContent?.trim(),
            className: tag.className.substring(0, 100),
            ariaLabel: tag.getAttribute('aria-label')
          })).slice(0, 5)
        };
      });

      console.log('=== TAG INFO ===');
      console.log(JSON.stringify(tagInfo, null, 2));

      // Hover over tags area to see edit controls
      await tagsArea.hover();
      await page.waitForTimeout(500);

      await page.screenshot({ path: `${exploreDir}/drawer-07-tags-hover.png`, fullPage: true });
    }
  }
});
