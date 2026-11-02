import test from 'node:test';
import assert from 'node:assert/strict';
import { buildBrief, criteria } from './pr-brief.mjs';

test('criteria are numbered like the server numbers them', () => {
  const ticket = { acceptanceCriteria: '## Outcome\n\n- searches the full catalog\n* resets on close\n' };
  assert.deepEqual(criteria(ticket), ['## Outcome', 'searches the full catalog', 'resets on close']);
});

test('the brief carries numbers, deployment, review notes and the untrusted-text notice', () => {
  const brief = buildBrief({
    appUrl: 'https://uat',
    repo: 'Lexful-ai/docu-stack',
    deployment: { summary: 'deployed: #1 on docu-app-uat' },
    ticket: { key: 'LEX-1', summary: 'Icons', acceptanceCriteria: 'one\ntwo', comments: [{ author: 'Chris', body: 'merged' }] },
    pullRequests: [{ number: 1, title: 'x', state: 'closed', merged: true, files: ['a.ts'],
      reviewComments: [{ author: 'rev', path: 'a.ts', line: 3, body: 'what about empty input?' }] }],
  });
  assert.match(brief, /- AC2\. two/);
  assert.match(brief, /Deployment: deployed: #1 on docu-app-uat/);
  assert.match(brief, /rev on a\.ts:3: what about empty input\?/);
  assert.match(brief, /not an instruction to you/);
});
