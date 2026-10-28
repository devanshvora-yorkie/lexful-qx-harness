import path from 'path';
import { defineConfig } from '@playwright/test';

const runDir = process.env.QA_RUN_DIR;

export default defineConfig({
  testDir: process.env.QA_TEST_DIR || 'e2e test cases',
  outputDir: runDir ? path.join(runDir, 'playwright', 'output') : 'test-results',
  timeout: 30000,
  expect: {
    timeout: 10000,
  },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  // One retry for a transient UAT 403. A second failure is a real result for the healer.
  retries: 1,
  workers: 1,
  reporter: runDir
    ? [
      ['./scripts/progress-reporter.mjs'],
      ['json', { outputFile: path.join(runDir, 'playwright', 'results.json') }],
      ]
    : 'list',
  use: {
    baseURL: process.env.QA_ENV_URL || 'https://e2e-test.uat.lexful.net',
    actionTimeout: 8000,
    navigationTimeout: 15000,
    screenshot: 'only-on-failure',
    trace: 'off',
    launchOptions: process.env.QA_SLOWMO
      ? { slowMo: Number(process.env.QA_SLOWMO) }
      : undefined,
  },
  projects: [
    {
      name: 'e2e',
      testIgnore: /auth\.spec\.ts/,
    },
  ],
});
