import assert from 'node:assert/strict';
import test from 'node:test';

import { nextProgress } from './progress-reporter.mjs';

const title = 'Servers Listing Page › toolbar buttons are visible';

test('a retry stays on the same case', () => {
  const first = nextProgress(
    { done: 12, total: 59 },
    { title, status: 'failed', retry: 0, retries: 2 },
  );
  assert.equal(first.done, 12);
  assert.equal(first.line, `failed  ${title}  12 done of 59`);

  const retry = nextProgress(
    { done: first.done, total: 59 },
    { title, status: 'timedOut', retry: 1, retries: 2 },
  );
  assert.equal(retry.done, 12);
  assert.equal(retry.line, `retry 1  failed  ${title}  12 done of 59`);

  const last = nextProgress(
    { done: retry.done, total: 59 },
    { title, status: 'failed', retry: 2, retries: 2 },
  );
  assert.equal(last.done, 13);
  assert.equal(last.line, `13/59  failed  after 2 retries  ${title}`);
});

test('a pass on retry counts the case once', () => {
  const step = nextProgress(
    { done: 12, total: 59 },
    { title, status: 'passed', retry: 1, retries: 2 },
  );
  assert.equal(step.done, 13);
  assert.equal(step.line, `13/59  passed  on retry 1  ${title}`);
});
