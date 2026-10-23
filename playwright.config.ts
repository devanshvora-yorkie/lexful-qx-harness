import path from 'path';
import { defineConfig } from '@playwright/test';

const runDir = process.env.QA_RUN_DIR;

export default defineConfig({
  testDir: process.env.QA_TEST_DIR || './tests',
  timeout: 30000,
  expect: {
    timeout: 10000,
  },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 2, // absorbs sporadic CloudFront 403s on shared UAT (seen ~1-3% of navigations)
  workers: process.env.CI ? 1 : 1,
  reporter: runDir
    ? [
      ['list'],
      ['json', { outputFile: path.join(runDir, 'playwright', 'results.json') }],
      ['html', { outputFolder: path.join(runDir, 'playwright', 'html'), open: 'never' }],
      ]
    : 'html',
  use: {
    baseURL: process.env.QA_ENV_URL || 'https://e2e-test.uat.lexful.net',
    actionTimeout: 8000,
    navigationTimeout: 15000,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    launchOptions: process.env.QA_SLOWMO
      ? { slowMo: Number(process.env.QA_SLOWMO) }
      : undefined,
  },
  projects: [
    {
      name: 'auth-setup',
      testMatch: /auth\.spec\.ts/,
    },
    {
      name: 'e2e',
      // No dependency on auth-setup — each test authenticates independently via saved cookies
      testIgnore: /auth\.spec\.ts/,
    },
  ],
});
