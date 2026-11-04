import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import {
  downloadImages, extractReferences, fetchImage, findImages, findPullRefs, guardPath, readFirst, readGuard, signedBodyImages, writeContextFiles,
} from './context-files.mjs';
import { lookup, parseRef, saveFiles } from './lookup.mjs';
import { buildBrief, criteria, criterionLimit } from './pr-brief.mjs';

const PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const temp = () => mkdtempSync(path.join(tmpdir(), 'ctx-'));
const reply = (status, { headers = {}, body = PNG } = {}) => new Response(status >= 300 && status < 400 ? null : body, { status, headers });

const PACK = {
  appUrl: 'https://uat',
  repo: 'Lexful-ai/docu-stack',
  primaryPr: 5,
  ticket: {
    key: 'LEX-1',
    summary: 'Icons',
    description: 'The picker misses icons.\n\n## Acceptance criteria\n- AC names LEX-7 and Lexful-ai/docu-stack#40\n- second line\n\n![mock](https://uploads.linear.app/a/b.png)\nSee LEX-8 too.',
    acceptanceCriteria: '- AC names LEX-7 and Lexful-ai/docu-stack#40\n- second line\n\n![mock](https://uploads.linear.app/a/b.png)\nSee LEX-8 too.',
    comments: [{ author: 'Parth', at: '2026-11-02T00:00:00Z', body: `Please try this. ${'x'.repeat(900)} END-OF-COMMENT` }],
    attachments: [{ url: 'https://figma.com/file/1', title: 'Design' }],
  },
  connectedTickets: [{ key: 'LEX-2', relation: 'parent', summary: 'Parent', description: 'Parent names LEX-9.\n![p](https://uploads.linear.app/parent.png)', comments: [] }],
  pullRequests: [{
    number: 5, title: 'Fix', state: 'closed', merged: true, mergedAt: '2026-11-01T00:00:00Z', files: ['a.ts'],
    body: `Follows #41. ${'y'.repeat(900)} END-OF-BODY`,
    reviewComments: [{ author: 'rev', path: 'a.ts', line: 3, body: 'what about empty input?' }, { author: 'rev2', body: 'LGTM' }],
    discussion: [],
  }],
};

test('nothing is trimmed on disk: the whole comment and body are in context/', async () => {
  const dir = temp();
  process.env.QA_GUARD_DIR = path.join(dir, 'guard');
  const index = await writeContextFiles(dir, PACK, { fetcher: async () => ({ bytes: PNG, kind: 'png' }), signer: async () => ({}) });
  assert.match(readFileSync(path.join(dir, 'context/ticket.md'), 'utf8'), /END-OF-COMMENT/);
  assert.match(readFileSync(path.join(dir, 'context/pr-5.md'), 'utf8'), /END-OF-BODY/);
  assert.match(readFileSync(path.join(dir, 'context/connected-LEX-2.md'), 'utf8'), /Parent names LEX-9/);
  assert.equal(index.images[0].file, 'context/attachments/img-01.png');
  assert.ok(existsSync(path.join(dir, 'context/attachments/img-01.png')));
  assert.match(readFileSync(path.join(dir, 'context/links.md'), 'utf8'), /Design: https:\/\/figma\.com\/file\/1/);
  assert.equal(statSync(guardPath(dir)).mode & 0o777, 0o600);
});

test('references: what a criterion names is marked, what the pack holds is not listed', () => {
  const refs = extractReferences(PACK);
  assert.deepEqual(refs.tickets.map((t) => [t.key, t.inCriteria]), [['LEX-7', true], ['LEX-8', true], ['LEX-9', false]]);
  assert.deepEqual(refs.pulls.map((p) => [p.number, p.inCriteria]), [[40, true], [41, false]]);
  // A connected ticket's picture describes a neighbor. It is not downloaded.
  assert.deepEqual(refs.images.map((i) => i.url), ['https://uploads.linear.app/a/b.png']);
});

test('a pull request in another org is never a reference', () => {
  assert.deepEqual(findPullRefs('see evil/repo#12 and https://github.com/Lexful-ai/x/pull/3').map((r) => r.repo).sort(), ['Lexful-ai/x', 'evil/repo']);
  const refs = extractReferences({ ...PACK, ticket: { ...PACK.ticket, description: 'see evil/repo#12', acceptanceCriteria: '', comments: [] }, pullRequests: [], connectedTickets: [] });
  assert.deepEqual(refs.pulls, []);
});

test('images are found in markdown and html, with the sentence next to them', () => {
  const found = findImages('The empty state must look like this:\n\n<img width="10" src="https://github.com/user-attachments/assets/1" alt="empty">\n![](https://x/y.png)');
  assert.deepEqual(found.map((i) => i.url), ['https://github.com/user-attachments/assets/1', 'https://x/y.png']);
  assert.equal(found[0].alt, 'empty');
  assert.equal(found[0].near, 'The empty state must look like this:');
});

test('image fetch: allowlisted hosts only, on every redirect, and a token stays with its issuer', async () => {
  const hosts = new Set(['uploads.linear.app', 'objects.githubusercontent.com']);
  const auth = (host) => (host === 'uploads.linear.app' ? { Authorization: 'secret' } : {});
  const seen = [];
  const fetchImpl = async (url, init) => {
    seen.push([new URL(url).host, init.headers.Authorization]);
    return new URL(url).host === 'uploads.linear.app' ? reply(302, { headers: { location: 'https://objects.githubusercontent.com/a' } }) : reply(200);
  };
  const good = await fetchImage('https://uploads.linear.app/a.png', { fetchImpl, hosts, auth });
  assert.equal(good.kind, 'png');
  assert.deepEqual(seen, [['uploads.linear.app', 'secret'], ['objects.githubusercontent.com', undefined]]);

  const evil = async () => reply(302, { headers: { location: 'https://169.254.169.254/latest' } });
  assert.match((await fetchImage('https://uploads.linear.app/a.png', { fetchImpl: evil, hosts, auth })).error, /not allowed/);
  assert.match((await fetchImage('https://evil.example/a.png', { fetchImpl, hosts, auth })).error, /not allowed/);
  assert.match((await fetchImage('http://uploads.linear.app/a.png', { fetchImpl, hosts, auth })).error, /not allowed/);
});

test('image fetch: only real images under the limit', async () => {
  const hosts = new Set(['uploads.linear.app']);
  const auth = () => ({});
  const html = async () => reply(200, { body: Buffer.from('<html><script>alert(1)</script>') });
  assert.match((await fetchImage('https://uploads.linear.app/a.png', { fetchImpl: html, hosts, auth })).error, /not a png/);
  const huge = async () => reply(200, { headers: { 'content-length': '9000000' } });
  assert.match((await fetchImage('https://uploads.linear.app/a.png', { fetchImpl: huge, hosts, auth })).error, /larger/);
});

test('a failed image is listed, not fatal, and the count is capped', async () => {
  const dir = temp();
  const images = [{ url: 'a' }, { url: 'b' }, { url: 'c' }];
  const results = await downloadImages(images, dir, { max: 1, fetcher: async (url) => (url === 'a' ? { error: 'HTTP 404' } : { bytes: PNG, kind: 'png' }) });
  assert.deepEqual(results.map((r) => r.status), ['not downloaded: HTTP 404', 'ok', 'not downloaded: over the limit of 1']);
  assert.equal(results[1].file, 'context/attachments/img-01.png');
});

test('signed urls pair with the body only when the lists line up', async () => {
  const pull = { number: 5, body: '![a](https://github.com/user-attachments/assets/1)\n<img src="https://github.com/user-attachments/assets/2">' };
  const two = '<img src="https://private-user-images.githubusercontent.com/1.png?jwt=a&amp;x=1"><img alt="b" src="https://private-user-images.githubusercontent.com/2.png?jwt=b">';
  const pairs = await signedBodyImages(pull, 'o/r', async () => ({ body_html: two }));
  assert.equal(pairs['https://github.com/user-attachments/assets/1'], 'https://private-user-images.githubusercontent.com/1.png?jwt=a&x=1');
  assert.deepEqual(await signedBodyImages(pull, 'o/r', async () => ({ body_html: '<p>none</p>' })), {});
  assert.deepEqual(await signedBodyImages({ number: 6, body: 'no pictures' }, 'o/r', async () => { throw new Error('must not call'); }), {});
});

test('signed urls are not stored', async () => {
  const dir = temp();
  process.env.QA_GUARD_DIR = path.join(dir, 'guard');
  const pack = { ...PACK, ticket: { ...PACK.ticket, comments: [] }, pullRequests: [{ ...PACK.pullRequests[0], body: '![a](https://github.com/user-attachments/assets/1)' }] };
  let used;
  await writeContextFiles(dir, pack, {
    signer: async () => ({ 'https://github.com/user-attachments/assets/1': 'https://private-user-images.githubusercontent.com/1.png?jwt=SIGNED' }),
    fetcher: async (url) => { if (url.includes('jwt')) used = url; return { bytes: PNG, kind: 'png' }; },
  });
  assert.match(used, /jwt=SIGNED/);
  assert.doesNotMatch(readFileSync(path.join(dir, 'context/index.json'), 'utf8'), /SIGNED/);
});

test('read first: named by a criterion, shown by the ticket, said after the merge', () => {
  const refs = extractReferences(PACK);
  const items = readFirst(PACK, refs, [{ file: 'context/attachments/img-01.png', source: 'ticket description', near: 'mock' }]);
  const what = items.map((i) => i.what);
  assert.ok(what.includes('context/attachments/img-01.png'));
  assert.ok(what.includes('node scripts/lookup.mjs LEX-7'));
  assert.ok(what.includes('node scripts/lookup.mjs Lexful-ai/docu-stack#40'));
  assert.ok(!what.includes('node scripts/lookup.mjs LEX-9'));
  assert.ok(items.find((i) => i.what === 'context/ticket.md').why.startsWith('1 Linear comment'));
});

test('read first presses at most three images, because each stays in the conversation', () => {
  const images = [1, 2, 3, 4, 5].map((n) => ({ file: `context/attachments/img-0${n}.png`, source: 'ticket description' }));
  assert.equal(readFirst({ ticket: {}, pullRequests: [] }, { tickets: [], pulls: [] }, images).length, 3);
});

test('criteria stay whole unless the total passes the budget, and numbering never changes', () => {
  const short = ['a'.repeat(900), 'b'.repeat(900)];
  assert.equal(criterionLimit(short), 1500);
  const many = Array.from({ length: 30 }, () => 'c'.repeat(1000));
  const limit = criterionLimit(many);
  assert.ok(limit * 30 <= 6000 || limit === 250);
  const ticket = { key: 'LEX-1', acceptanceCriteria: many.join('\n') };
  const brief = buildBrief({ ticket, pullRequests: [], appUrl: 'u' }, { files: [] });
  assert.equal(criteria(ticket).length, 30);
  assert.match(brief, /- AC30\. c+…/);
  assert.match(brief, /read it in context\/ticket\.md/);
});

test('the brief is an index: full criteria, pointers, and no approval noise', async () => {
  const dir = temp();
  process.env.QA_GUARD_DIR = path.join(dir, 'guard');
  const index = await writeContextFiles(dir, PACK, { fetcher: async () => ({ bytes: PNG, kind: 'png' }), signer: async () => ({}) });
  const brief = buildBrief(PACK, index);
  assert.match(brief, /## The ticket\nThe picker misses icons\./);
  assert.match(brief, /## Read before planning/);
  assert.match(brief, /Full text: context\/pr-5\.md/);
  assert.match(brief, /context\/connected-LEX-2\.md/);
  assert.match(brief, /what about empty input\?/);
  assert.doesNotMatch(brief, /LGTM/);
  assert.doesNotMatch(brief, /END-OF-COMMENT|END-OF-BODY/);
  assert.match(brief, /context\/links\.md/);
  assert.match(brief, /up to 8 tickets and 5 pull requests/);
});

// ---- lookup -------------------------------------------------------------------------------------

async function lookupRun() {
  const dir = temp();
  process.env.QA_GUARD_DIR = path.join(dir, 'guard');
  const run = path.join(dir, 'run');
  mkdirSync(run);
  await writeContextFiles(run, PACK, { fetcher: async () => ({ error: 'off' }), signer: async () => ({}) });
  return run;
}
const fetchers = {
  ticket: async (key) => ({ key, summary: `About ${key}`, description: 'text', comments: [] }),
  pull: async (number, repo) => ({ number, repo, title: `PR ${number}`, body: 'b', state: 'open', fileDetails: [{ filename: 'a.ts', patch: '+x' }] }),
};

test('lookup: a named ticket is returned as text and nothing is written by the server half', async () => {
  const run = await lookupRun();
  const result = await lookup(run, 'lex-7', fetchers);
  assert.match(result.line, /LEX-7 "About LEX-7" saved to .*context\/lookups\/LEX-7\.md .*Used 1 of 8 tickets/);
  assert.equal(result.files[0].path, 'context/lookups/LEX-7.md');
  assert.ok(!existsSync(path.join(run, 'context/lookups')));
});

test('lookup: anything the context does not name is refused', async () => {
  const run = await lookupRun();
  await assert.rejects(lookup(run, 'LEX-999', fetchers), /not named/);
  await assert.rejects(lookup(run, '999', fetchers), /not named/);
  await assert.rejects(lookup(run, 'evil/repo#40', fetchers), /not named/);
  assert.equal(readGuard(run).used.tickets.length, 0);
});

test('lookup: what is already on disk or fetched costs nothing', async () => {
  const run = await lookupRun();
  assert.match((await lookup(run, 'LEX-1', fetchers)).line, /already on disk/);
  assert.match((await lookup(run, 'LEX-2', fetchers)).line, /already on disk/);
  assert.match((await lookup(run, '5', fetchers)).line, /already on disk/);
  await lookup(run, 'LEX-7', fetchers);
  const again = await lookup(run, 'LEX-7', { ticket: async () => { throw new Error('must not fetch twice'); } });
  assert.match(again.line, /already fetched/);
  assert.deepEqual(again.files, []);
  assert.equal(readGuard(run).used.tickets.length, 1);
});

test('lookup: the budget holds, and a failed fetch does not spend it', async () => {
  const run = await lookupRun();
  await assert.rejects(lookup(run, 'LEX-7', { ticket: async () => { throw new Error('Linear 500'); } }), /Linear 500/);
  assert.equal(readGuard(run).used.tickets.length, 0);
  const guard = readGuard(run);
  guard.limits.tickets = 1;
  writeFileSync(guardPath(run), JSON.stringify(guard));
  await lookup(run, 'LEX-7', fetchers);
  await assert.rejects(lookup(run, 'LEX-8', fetchers), /budget spent: 1 of 1 tickets/);
});

test('lookup: a pull request brings its patches', async () => {
  const run = await lookupRun();
  const result = await lookup(run, 'Lexful-ai/docu-stack#40', fetchers);
  assert.deepEqual(result.files.map((f) => f.path), ['context/lookups/pr-40.md', 'context/lookups/pr-40.patch']);
  assert.match(result.line, /Used 1 of 5 pull requests/);
});

test('saving: only the paths the script builds', () => {
  const run = temp();
  saveFiles(run, [{ path: 'context/lookups/LEX-7.md', text: 'ok' }]);
  assert.equal(readFileSync(path.join(run, 'context/lookups/LEX-7.md'), 'utf8'), 'ok');
  for (const bad of ['../../etc/passwd', 'context/lookups/../../x', '/etc/passwd', 'context/other/x.md']) {
    assert.throws(() => saveFiles(run, [{ path: bad, text: 'x' }]), /Refusing/);
  }
});

test('refs parse strictly', () => {
  assert.deepEqual(parseRef('lex-12'), { kind: 'ticket', key: 'LEX-12' });
  assert.equal(parseRef('#12').number, 12);
  assert.equal(parseRef('a/b#12').repo, 'a/b');
  for (const bad of ['', 'LEX-', '--flag', 'a/b', '12;rm', '../x#1']) assert.throws(() => parseRef(bad), /Give LEX/);
});
