import path from 'node:path';
import { mkdirSync } from 'node:fs';
import { buildContext } from './context.mjs';
import {
  CFG,
  ROOT,
  check,
  ensureStytchSession,
  github,
  linear,
  parseArgs,
  pullRequestForSha,
  toolVersions,
  writeJson,
} from './harness-env.mjs';
import { createCliRun, updateIndex } from './run-store.mjs';
import { ensureToolchain } from './toolchain.mjs';

function envCheck() {
  const missing = [];
  if (!CFG.linearKey) missing.push('LINEAR_API_KEY');
  if (!CFG.githubToken) missing.push('GITHUB_TOKEN');
  if (!CFG.org) missing.push('STYTCH_ORGANIZATION_ID');
  if (!CFG.email) missing.push('STYTCH_ADMIN_EMAIL');
  if (!CFG.password) missing.push('STYTCH_ADMIN_PASSWORD');
  if (missing.length) return check('Env file', 'fail', `Missing ${missing.join(', ')}`);
  return check('Env file', 'pass', 'Linear, GitHub, and Stytch credentials are set');
}

async function linearCheck() {
  const data = await linear('query Viewer { viewer { name } }');
  return check('Linear', 'pass', `Key accepted for ${data.viewer?.name || 'viewer'}`);
}

async function githubCheck() {
  const user = await github('/user');
  return check('GitHub', 'pass', `Token accepted for ${user.login}; repo files are read only through a pull request`);
}

async function stytchCheck(destDir) {
  const session = await ensureStytchSession(destDir);
  const reused = session.reused ? 'Reused cached session' : `HTTP ${session.status}`;
  if (session.onLogin) return check('Stytch', 'fail', `Cookies saved, but ${CFG.qaUrl} landed on login`);
  if (session.pageStatus === 403) {
    return check('Stytch', 'pass', `${reused}, cookies saved; app returned 403 (CloudFront)`);
  }
  return check('Stytch', 'pass', `${reused}, ${session.cookieCount} cookies, app HTTP ${session.pageStatus}`);
}

function versionCheck() {
  const versions = toolVersions();
  return check('Playwright', 'pass', `${versions.playwright}; playwright-cli ${versions.cli}`);
}

async function main() {
  const args = parseArgs(process.argv);
  let owned = null;
  if (!args.out && !args.toolsOnly && !args.sessionOnly) {
    const label = args.ticket || (args.pr ? `pr-${args.pr}` : args.sha ? `sha-${args.sha.slice(0, 7)}` : 'tools');
    owned = createCliRun(label);
    args.out = owned.dir;
  }
  if (args.out) {
    args.out = path.resolve(args.out);
    mkdirSync(args.out, { recursive: true });
    process.env.QA_RUN_DIR = args.out;
  }

  const checks = [];
  const run = async (name, fn) => {
    try {
      checks.push(await fn());
    } catch (err) {
      checks.push(check(name, 'fail', err.message));
    }
  };

  checks.push(...ensureToolchain());
  if (args.sessionOnly) {
    if (!args.out) {
      console.error('--session-only needs --out');
      process.exit(1);
    }
    const missing = [];
    if (!CFG.org) missing.push('STYTCH_ORGANIZATION_ID');
    if (!CFG.email) missing.push('STYTCH_ADMIN_EMAIL');
    if (!CFG.password) missing.push('STYTCH_ADMIN_PASSWORD');
    if (missing.length) checks.push(check('Env file', 'fail', `Missing ${missing.join(', ')}`));
    else {
      checks.push(check('Env file', 'pass', 'Stytch credentials are set. Linear and GitHub are not called'));
      await run('Stytch', () => stytchCheck(args.out));
    }
    await run('Playwright', versionCheck);
    const report = {
      ok: !checks.some((row) => row.status === 'fail'),
      checkedAt: new Date().toISOString(),
      appUrl: CFG.qaUrl,
      phase: 'checked-in-suite',
      linear: false,
      runDir: path.relative(ROOT, path.resolve(args.out)),
      checks,
    };
    const outFile = path.join(path.resolve(args.out), 'preflight.json');
    writeJson(outFile, report);
    for (const row of checks) console.log(`${row.status.toUpperCase()}  ${row.name}: ${row.detail}`);
    console.log(report.ok ? `ok → ${outFile}` : `failed → ${outFile}`);
    if (!report.ok) process.exit(1);
    return;
  }
  if (args.toolsOnly) {
    for (const row of checks) console.log(`${row.status.toUpperCase()}  ${row.name}: ${row.detail}`);
    if (checks.some((row) => row.status === 'fail')) process.exit(1);
    console.log('toolchain ok');
    return;
  }

  checks.push(envCheck());
  if (checks.some((row) => row.name === 'Env file' && row.status === 'pass')) {
    await run('Linear', linearCheck);
    await run('GitHub', githubCheck);
    await run('Stytch', () => stytchCheck(args.out));
  }
  await run('Playwright', versionCheck);

  const canResolve = checks.some((row) => row.name === 'Linear' && row.status === 'pass')
    && checks.some((row) => row.name === 'GitHub' && row.status === 'pass');
  const report = {
    ok: false,
    checkedAt: new Date().toISOString(),
    appUrl: CFG.qaUrl,
    repo: `${CFG.githubOrg}/${CFG.githubRepo}`,
    runDir: args.out ? path.relative(ROOT, path.resolve(args.out)) : null,
    checks,
  };

  if (canResolve && args.sha && !args.pr && !args.ticket) {
    try {
      const found = await pullRequestForSha(args.sha);
      if (!found.ticket && !found.number) throw new Error(`No LEX ticket on ${args.sha}`);
      args.pr = found.number;
      report.sha = args.sha;
    } catch (err) {
      checks.push(check('Ticket context', 'fail', err.message));
    }
  }

  if (canResolve && (args.ticket || args.pr)) {
    try {
      const built = await buildContext({ ticket: args.ticket, pr: args.pr, outDir: args.out });
      report.ticket = built.pack.ticket.key;
      report.pullRequests = built.pack.pullRequests.map((pr) => pr.number);
      report.primaryPr = built.pack.primaryPr;
      report.connectedTickets = (built.pack.connectedTickets || []).map((item) => item.key).filter(Boolean);
      report.contextPack = path.relative(ROOT, built.file);
      if (built.pack.contextErrors.length) {
        checks.push(check('Ticket context', 'fail', built.pack.contextErrors.map((entry) => entry.detail).join('; ')));
      } else {
        checks.push(check(
          'Ticket context',
          'pass',
          `${built.pack.ticket.key}: PR ${report.pullRequests.join(', ') || 'none'}; connected ${report.connectedTickets.join(', ') || 'none'}`,
        ));
      }
    } catch (err) {
      checks.push(check('Ticket context', 'fail', err.message));
    }
  }

  report.ok = !checks.some((row) => row.status === 'fail');
  const outFile = path.join(path.resolve(args.out), 'preflight.json');
  writeJson(outFile, report);
  if (owned) {
    updateIndex({
      id: owned.id,
      ticket: report.ticket || owned.ticket || null,
      pr: report.primaryPr || null,
      sha: args.sha || null,
      status: report.ok ? 'preflight_ok' : 'halted',
      updatedAt: new Date().toISOString(),
    });
  }
  for (const row of checks) console.log(`${row.status.toUpperCase()}  ${row.name}: ${row.detail}`);
  console.log(report.ok ? `ok → ${outFile}` : `failed → ${outFile}`);
  if (!report.ok) process.exit(1);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
