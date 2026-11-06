import path from 'node:path';
import {
  CFG,
  deploymentStatus,
  fetchPullRequest,
  fetchTicket,
  parseArgs,
  pickPrimaryPr,
  primaryLexKey,
  searchPullRequests,
  writeJson,
} from './harness-env.mjs';
import { createCliRun, updateIndex } from './run-store.mjs';
import { writeContextFiles } from './context-files.mjs';
import { writeBrief } from './pr-brief.mjs';

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
  const unreadable = [];
  try {
    pulls = await searchPullRequests(issue.key, known, issue.linkedPullRequests || [], unreadable);
  } catch (err) {
    errors.push({ source: 'github', reason: 'pull_request_search_failed', detail: err.message });
  }
  let deployment = { summary: 'not checked', build: '', components: [] };
  try {
    deployment = await deploymentStatus(pulls);
  } catch (err) {
    // A failed check is reported, never fatal: the run still tests, marked unverified.
    deployment = { summary: `not verified: ${err.message.slice(0, 120)}`, build: '', components: [] };
  }

  const pack = {
    trigger,
    ticket: issue,
    connectedTickets: issue.connectedTickets,
    appUrl: CFG.qaUrl,
    repo: `${CFG.githubOrg}/${CFG.githubRepo}`,
    scope: 'pull-request-files-and-connected-linear-issues',
    pullRequests: pulls,
    unreadablePullRequests: unreadable,
    primaryPr: pr || pickPrimaryPr(pulls),
    deployment,
    contextErrors: errors,
    writtenAt: new Date().toISOString(),
  };
  if (!outDir) throw new Error('buildContext requires outDir');
  const file = path.join(outDir, 'context-pack.json');
  writeJson(file, pack);
  try {
    // Full text on disk. A failure here costs depth, not the run: the brief still works without it.
    const index = await writeContextFiles(outDir, pack);
    pack.contextFiles = { files: index.files.length, images: index.images.filter((image) => image.file).length, imagesFound: index.images.length };
  } catch (err) {
    pack.contextFiles = { error: String(err?.message || err).slice(0, 200) };
    console.error(`context files not written: ${pack.contextFiles.error}`);
  }
  try {
    writeBrief(outDir);
  } catch (err) {
    pack.contextErrors.push({ source: 'brief', reason: 'pr_brief_failed', detail: err.message });
  }
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
