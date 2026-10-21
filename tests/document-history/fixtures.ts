import { test as base, expect } from '@playwright/test';
import { injectAuthCookies } from '../../auth-helper';
import { DocumentHistoryPOM } from './document-history-pom';

export const test = base.extend<{ doc: DocumentHistoryPOM }>({
  doc: async ({ page }, use, testInfo) => {
    testInfo.setTimeout(90000);
    await injectAuthCookies(page.context());
    await use(new DocumentHistoryPOM(page));
  },
});

export { expect };
