import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * context-pack.json is often 1 MB of patches. pr-brief.md is the same pack with
 * the patches left out: acceptance criteria, each PR's title, state, body, and
 * changed file paths. It decides nothing. The skill tells the agent how to read
 * it, which lane to work in, and what to grep from the pack.
 */

const clip = (text, n) => String(text || '').replace(/\(<?https?:[^)]*>?\)/g, '').replace(/\s+/g, ' ').trim().slice(0, n);

export function buildBrief(pack) {
  const ticket = pack.ticket || {};
  const out = [`# Brief ${ticket.key || ''}: ${clip(ticket.summary, 120)}`, '', `App: ${pack.appUrl}`, ''];
  const ac = String(ticket.acceptanceCriteria || '').split('\n').map((l) => l.trim()).filter(Boolean).slice(0, 30);
  if (ac.length) out.push('## Acceptance criteria', ...ac.map((l) => `- ${clip(l.replace(/^[-*]\s*/, ''), 170)}`), '');
  out.push('## Pull requests');
  for (const pull of pack.pullRequests || []) {
    const files = pull.files || [];
    const state = pull.merged ? 'merged' : pull.state;
    out.push(`### #${pull.number} ${clip(pull.title, 90)} [${state}, ${files.length} files]`, clip(pull.body, 500));
    out.push(`Files: ${files.slice(0, 20).join(', ')}${files.length > 20 ? ` (+${files.length - 20} more)` : ''}`, '');
  }
  const connected = (pack.connectedTickets || []).map((t) => `${t.key} ${clip(t.summary, 70)}`);
  if (connected.length) out.push(`Connected: ${connected.join('; ')}`, '');
  out.push('The patches are in context-pack.json (pullRequests[].fileDetails[].patch). Do not open it whole. Grep it for one file or symbol.');
  return out.join('\n');
}

export function writeBrief(runDir) {
  const pack = JSON.parse(readFileSync(path.join(runDir, 'context-pack.json'), 'utf8'));
  const file = path.join(runDir, 'pr-brief.md');
  writeFileSync(file, `${buildBrief(pack)}\n`);
  return file;
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));
if (isMain) {
  const dir = process.argv[2];
  if (!dir) { console.error('Usage: node scripts/pr-brief.mjs <run dir>'); process.exit(1); }
  console.log(writeBrief(dir));
}
