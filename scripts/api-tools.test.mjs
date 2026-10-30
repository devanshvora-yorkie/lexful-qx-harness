import assert from 'node:assert/strict';
import test from 'node:test';
import { parseProbeArgs } from './api-probe.mjs';
import { buildBrief } from './pr-brief.mjs';

test('probe refuses writes without --write', () => {
  assert.throws(() => parseProbeArgs(['POST', '/v1/x']), /--write/);
  assert.equal(parseProbeArgs(['--persona', 'all', 'GET', '/v1/x']).persona, 'all');
  assert.throws(() => parseProbeArgs(['--persona', 'root', 'GET', '/v1/x']), /persona/);
});

test('brief keeps criteria, PR text, and file paths, and leaves the patches out', () => {
  const pack = { ticket: { key: 'LEX-1', summary: 's', acceptanceCriteria: '- [ ] a' }, appUrl: 'u',
    pullRequests: [{ number: 5, title: 't', body: 'b', state: 'open', files: ['a/b.ts'], fileDetails: [{ patch: 'x'.repeat(5000) }] }] };
  const brief = buildBrief(pack);
  assert.match(brief, /#5 t \[open, 1 files\]/);
  assert.match(brief, /Files: a\/b\.ts/);
  assert.ok(brief.length < 1500);
});
