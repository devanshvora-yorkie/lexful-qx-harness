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

test('the brief lists what this ticket changed that UAT does not run', () => {
  const brief = buildBrief({
    appUrl: 'https://uat',
    deployment: { summary: 'x', components: [
      { pr: 7, env: 'docu-service-uat', deployedSha: 'abcdef1234', included: false },
      { pr: 8, env: 'docu-app-uat', deployedSha: 'ffff', included: true },
    ] },
    ticket: { key: 'LEX-1', summary: 's' },
    pullRequests: [{ number: 9, title: 'fix', state: 'open', merged: false, files: [] }],
  });
  assert.match(brief, /## Not on UAT/);
  assert.match(brief, /#7 is merged, but docu-service-uat runs an older build \(abcdef12\)/);
  assert.match(brief, /#9 is open/);
  assert.doesNotMatch(brief, /#8 is merged/);
});

test('no Not on UAT section when everything is deployed', () => {
  const brief = buildBrief({ appUrl: 'u', deployment: { components: [{ pr: 1, env: 'docu-app-uat', included: true }] },
    ticket: { key: 'LEX-1' }, pullRequests: [{ number: 1, merged: true, files: [] }] });
  assert.doesNotMatch(brief, /Not on UAT/);
});
