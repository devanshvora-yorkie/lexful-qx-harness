import { test as base, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

/**
 * Feature specs import `test` and `expect` from here instead of '@playwright/test'.
 *
 * An automatic fixture records what a passing assertion does not see: console errors,
 * uncaught page errors, API calls that answered 4xx/5xx, and API calls that never got an
 * answer. Rows go to <run dir>/playwright/signals.jsonl. The server reports them, and a
 * verifier session looks at server errors and page errors before the run is signed off.
 */

type Signal = {
  kind: 'console' | 'pageerror' | 'response' | 'requestfailed';
  text?: string;
  method?: string;
  status?: number;
  path?: string;
  host?: string;
};

const API_TYPES = new Set(['fetch', 'xhr']);

export const test = base.extend<{ qaSignals: void }>({
  qaSignals: [
    async ({ page }, use, testInfo) => {
      const rows: Signal[] = [];
      page.on('console', (message) => {
        if (message.type() === 'error') rows.push({ kind: 'console', text: message.text().slice(0, 300) });
      });
      page.on('pageerror', (error) => {
        rows.push({ kind: 'pageerror', text: String(error?.message || error).slice(0, 300) });
      });
      page.on('response', (response) => {
        const request = response.request();
        if (!API_TYPES.has(request.resourceType()) || response.status() < 400) return;
        const url = new URL(response.url());
        rows.push({ kind: 'response', method: request.method(), status: response.status(), path: url.pathname, host: url.host });
      });
      page.on('requestfailed', (request) => {
        const reason = request.failure()?.errorText || '';
        // A navigation or a fetch the page cancelled on purpose is not a failure.
        if (!API_TYPES.has(request.resourceType()) || /ERR_ABORTED|NS_BINDING_ABORTED/i.test(reason)) return;
        const url = new URL(request.url());
        rows.push({ kind: 'requestfailed', method: request.method(), path: url.pathname, host: url.host, text: reason });
      });

      await use();

      const dir = process.env.QA_RUN_DIR;
      if (!dir || rows.length === 0) return;
      const target = path.join(dir, 'playwright', 'signals.jsonl');
      fs.mkdirSync(path.dirname(target), { recursive: true });
      const where = {
        test: testInfo.titlePath.slice(1).join(' › '),
        file: path.basename(testInfo.file),
        outcome: testInfo.status,
        retry: testInfo.retry,
      };
      fs.appendFileSync(target, rows.map((row) => JSON.stringify({ ...where, ...row })).join('\n') + '\n');
    },
    { auto: true },
  ],
});

export { expect };
