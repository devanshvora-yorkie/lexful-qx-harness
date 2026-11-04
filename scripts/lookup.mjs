// Read one more ticket or pull request that this run's context names, without giving the agent a token.
//
//   node scripts/lookup.mjs LEX-3462
//   node scripts/lookup.mjs 1957                     a pull request in the default repo
//   node scripts/lookup.mjs Lexful-ai/docu-stack#1957
//
// The agent has no Linear or GitHub key, so this asks the harness server on localhost, like persona.mjs.
// The server runs it with LOOKUP_DIRECT=1 and returns the text; this process, as the agent user, saves it under
// context/lookups/. Only references found in the run's own context are allowed (one hop), each is fetched once,
// and the per-run caps are enforced.
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { CFG, ROOT, fetchPullRequest, fetchTicketOnly } from './harness-env.mjs';
import { formatBytes, readGuard, renderPull, renderTicket, writeGuard } from './context-files.mjs';

const MAX_PATCH_CHARS = 300_000;

export function parseRef(raw) {
  const text = String(raw || '').trim();
  if (/^LEX-\d+$/i.test(text)) return { kind: 'ticket', key: text.toUpperCase() };
  const qualified = text.match(/^([A-Za-z0-9][\w.-]*\/[A-Za-z0-9][\w.-]*)#(\d+)$/);
  if (qualified) return { kind: 'pull', repo: qualified[1], number: Number(qualified[2]) };
  const bare = text.match(/^#?(\d+)$/);
  if (bare) return { kind: 'pull', repo: `${CFG.githubOrg}/${CFG.githubRepo}`, number: Number(bare[1]) };
  throw new Error('Give LEX-1234, a pull request number, or org/repo#123');
}

const shown = (runDir, relative) => path.relative(ROOT, path.join(runDir, relative));

/**
 * Policy and fetching. Returns the line to print and the files to save. It writes nothing into the run folder:
 * this half runs as the server, and the agent user owns that folder, so a planted symlink could redirect a write.
 */
export async function lookup(runDir, raw, fetchers = { ticket: fetchTicketOnly, pull: fetchPullRequest }) {
  const ref = parseRef(raw);
  const guard = readGuard(runDir);
  if (!guard) throw new Error('This run has no context index, so there is nothing to look up. Use pr-brief.md');
  const isTicket = ref.kind === 'ticket';
  const id = isTicket ? ref.key : `${ref.repo}#${ref.number}`;
  const local = guard.local?.[isTicket ? id : id.toLowerCase()];
  if (local) return { line: `${id} is already on disk: ${shown(runDir, local)}`, files: [] };

  const known = isTicket ? guard.tickets : guard.pulls;
  if (!known.some((item) => item.toLowerCase() === id.toLowerCase())) {
    throw new Error(`${id} is not named in this run's ticket or pull requests, so it cannot be looked up`);
  }
  const relative = `context/lookups/${isTicket ? id : `pr-${ref.number}`}.md`;
  const bucket = isTicket ? 'tickets' : 'pulls';
  const noun = isTicket ? 'tickets' : 'pull requests';
  if (guard.used[bucket].some((item) => item.toLowerCase() === id.toLowerCase())) {
    return { line: `${id} was already fetched: ${shown(runDir, relative)}`, files: [] };
  }
  const cap = guard.limits[bucket];
  if (guard.used[bucket].length >= cap) {
    throw new Error(`Lookup budget spent: ${guard.used[bucket].length} of ${cap} ${noun}. Plan with what you have and note the gap`);
  }

  const files = [];
  let title;
  if (isTicket) {
    const ticket = await fetchers.ticket(id);
    title = ticket.summary || '';
    files.push({ path: relative, text: renderTicket(ticket) });
  } else {
    const pull = await fetchers.pull(ref.number, ref.repo);
    title = pull.title || '';
    files.push({ path: relative, text: renderPull(pull) });
    const patch = (pull.fileDetails || []).filter((file) => file.patch)
      .map((file) => `--- ${file.filename}\n${file.patch}`).join('\n\n').slice(0, MAX_PATCH_CHARS);
    if (patch) files.push({ path: `context/lookups/pr-${ref.number}.patch`, text: `${patch}\n` });
  }
  guard.used[bucket].push(id);
  writeGuard(runDir, guard);
  const size = formatBytes(Buffer.byteLength(files[0].text));
  return {
    line: `${id} "${String(title).slice(0, 80)}" saved to ${shown(runDir, relative)} (${size}). Used ${guard.used[bucket].length} of ${cap} ${noun}. Grep it; do not print it whole.`,
    files,
  };
}

/** Runs as the agent user, in its own run folder. Only paths this script itself builds are accepted. */
export function saveFiles(runDir, files) {
  for (const file of files || []) {
    if (!/^context\/lookups\/[\w.-]+$/.test(String(file.path))) throw new Error(`Refusing to write ${file.path}`);
    const target = path.join(runDir, file.path);
    mkdirSync(path.dirname(target), { recursive: true });
    writeFileSync(target, file.text);
  }
}

async function askServer(run, ref) {
  const port = process.env.QA_SERVER_PORT || '8787';
  let response;
  try {
    response = await fetch(`http://127.0.0.1:${port}/internal/lookup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run, ref }),
    });
  } catch {
    throw new Error('The harness server is not running, so this cannot be looked up from here');
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Lookup failed with HTTP ${response.status}`);
  return body;
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));
if (isMain) {
  const args = process.argv.slice(2);
  const at = args.indexOf('--run');
  const run = at >= 0 ? args[at + 1] : process.env.QA_RUN_DIR;
  const raw = args.filter((_, index) => at < 0 || (index !== at && index !== at + 1))[0];
  try {
    if (!raw) throw new Error('Usage: node scripts/lookup.mjs <LEX-1234 | 123 | org/repo#123>');
    if (!run) throw new Error('No run directory: QA_RUN_DIR is not set');
    parseRef(raw);
    const runDir = path.resolve(run);
    if (process.env.LOOKUP_DIRECT === '1') {
      console.log(JSON.stringify(await lookup(runDir, raw)));
    } else {
      const result = await askServer(runDir, raw);
      saveFiles(runDir, result.files);
      console.log(result.line);
    }
  } catch (err) {
    console.error(err instanceof Error ? err.message : String(err));
    process.exit(1);
  }
}
