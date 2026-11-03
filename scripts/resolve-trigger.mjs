// The ticket a pull request or a deployed commit belongs to, read before the run folder exists,
// so a run is created under runs/tickets/<ticket>/ and never moves.
//
//   node scripts/resolve-trigger.mjs --pr 2245      {"ticket":"LEX-3642","pr":2245}
//   node scripts/resolve-trigger.mjs --sha ca77ea4  {"ticket":"LEX-3509","pr":2268}
//
// Prints {"ticket":null,...} when GitHub names no LEX key. Exits 1 with {"error":...} when GitHub
// cannot be read; the server then keeps the run under pull-requests/ or deploys/.
import process from 'node:process';
import { CFG, github, primaryLexKey, pullRequestForSha } from './harness-env.mjs';

function argument(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

async function main() {
  const pr = Number(argument('--pr')) || null;
  const sha = argument('--sha') || null;
  if (pr) {
    const raw = await github(`/repos/${CFG.githubOrg}/${CFG.githubRepo}/pulls/${pr}`);
    return { ticket: primaryLexKey({ title: raw.title, headRef: raw.head?.ref, body: raw.body }), pr };
  }
  if (sha) {
    const found = await pullRequestForSha(sha);
    return { ticket: found.ticket, pr: found.number };
  }
  throw new Error('give --pr <number> or --sha <commit>');
}

try {
  console.log(JSON.stringify(await main()));
} catch (error) {
  console.log(JSON.stringify({ error: String(error.message || error).slice(0, 240) }));
  process.exit(1);
}
