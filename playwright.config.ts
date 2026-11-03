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
  // Each test goes to the next free worker (QA_PW_WORKERS of them), so one long file no longer runs alone
  // on one worker while the others idle. The worker count, not this, decides how many browsers hit UAT.
  // A file whose tests depend on each other declares test.describe.configure({ mode: 'serial' }), and a
  // file that must keep its order declares mode 'default'. QA_PW_FULLY_PARALLEL=false restores file-level.
  fullyParallel: process.env.QA_PW_FULLY_PARALLEL !== 'false',
  forbidOnly: !!process.env.CI,
  // One retry for a transient UAT 403. A second failure is a real result for the healer.
  retries: 1,
  workers: Number(process.env.QA_PW_WORKERS || 1),
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
