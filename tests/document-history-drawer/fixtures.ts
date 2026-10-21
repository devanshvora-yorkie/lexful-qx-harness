import { test as base, expect } from '@playwright/test';
import { injectAuthCookies } from '../../auth-helper';
import { DocumentHistoryDrawerPOM } from './document-history-drawer-pom';

export const test = base.extend<{ drawer: DocumentHistoryDrawerPOM }>({
  drawer: async ({ page }, use, testInfo) => {
    testInfo.setTimeout(90000);
    await injectAuthCookies(page.context());
    await use(new DocumentHistoryDrawerPOM(page));
  },
});

export { expect };
