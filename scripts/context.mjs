import path from 'node:path';
import {
  CFG,
  fetchPullRequest,
  fetchTicket,
  parseArgs,
  pickPrimaryPr,
  primaryLexKey,
  searchPullRequests,
  writeJson,
} from './harness-env.mjs';
import { createCliRun, updateIndex } from './run-store.mjs';

export async function buildContext({ ticket, pr, outDir }) {
  const errors = [];
  let trigger = 'ticket';
  let issueKey = ticket;
  let known = [];

  if (pr) {
    trigger = 'pr';
    const pull = await fetchPullRequest(pr);
    known = [pull];
    issueKey = primaryLexKey(pull);
    if (!issueKey) throw new Error(`PR #${pr} has no LEX-#### in the title, branch, or body`);
  }
  if (!issueKey) throw new Error('Pass a LEX-#### key or --pr <number>');

  const issue = await fetchTicket(issueKey);
  let pulls = known;
  try {
    const found = await searchPullRequests(issue.key, known);
    const byNumber = new Map(found.map((item) => [item.number, item]));
    for (const item of known) byNumber.set(item.number, item);
    pulls = [...byNumber.values()];
  } catch (err) {
    errors.push({ source: 'github', reason: 'pull_request_search_failed', detail: err.message });
  }

  const pack = {
    trigger,
    ticket: issue,
    connectedTickets: issue.connectedTickets,
    appUrl: CFG.qaUrl,
    repo: `${CFG.githubOrg}/${CFG.githubRepo}`,
    scope: 'pull-request-files-and-connected-linear-issues',
    pullRequests: pulls,
    primaryPr: pr || pickPrimaryPr(pulls),
    contextErrors: errors,
    writtenAt: new Date().toISOString(),
  };
  if (!outDir) throw new Error('buildContext requires outDir');
  const file = path.join(outDir, 'context-pack.json');
  writeJson(file, pack);
  return { file, pack };
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname);
if (isMain) {
  const args = parseArgs(process.argv);
  const owned = args.out ? null : createCliRun(args.ticket || (args.pr ? `pr-${args.pr}` : 'context'));
  buildContext({ ...args, outDir: args.out || owned.dir })
    .then(({ file, pack }) => {
      if (owned) {
        updateIndex({
          id: owned.id,
          ticket: pack.ticket.key,
          pr: pack.primaryPr,
          status: 'context_ok',
          updatedAt: new Date().toISOString(),
        });
      }
      const links = (pack.connectedTickets || []).map((item) => item.key).filter(Boolean);
      console.log(`${pack.ticket.key}: ${pack.pullRequests.length} PR(s), connected [${links.join(', ') || 'none'}] → ${file}`);
    })
    .catch((err) => {
      console.error(err.message);
      process.exit(1);
    });
}
