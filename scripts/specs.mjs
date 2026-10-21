import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { CFG, ROOT, ensureStytchSession } from './harness-env.mjs';
import { RUNS, newRunId } from './run-store.mjs';

function usage() {
  console.error('Usage: node scripts/specs.mjs [--headed] <folder-or-spec> [more paths]');
  console.error('       node scripts/specs.mjs --headed runs/LEX-2293/<run-id>/specs');
  console.error('       node scripts/specs.mjs --headed runs/LEX-2293/<run-id>/specs/read.spec.ts');
  console.error('       node scripts/specs.mjs "e2e test cases/search"');
  console.error('On this Mac, --headed opens a Chrome window. Inside Docker the window stays on a virtual display.');
}

function isSpec(file) {
  const base = path.basename(file);
  if (base === 'auth.spec.ts' || base === 'auth.spec.js') return false;
  return base.endsWith('.spec.ts') || base.endsWith('.spec.js');
}

function walk(abs, explicitFile, into) {
  const stat = statSync(abs);
  if (stat.isDirectory()) {
    for (const entry of readdirSync(abs, { withFileTypes: true })) {
      if (entry.name.startsWith('.')) continue;
      walk(path.join(abs, entry.name), false, into);
    }
    return;
  }
  if (!stat.isFile()) return;
  if (isSpec(abs)) {
    into.add(path.relative(ROOT, abs));
    return;
  }
  if (explicitFile) throw new Error(`Not a spec file: ${path.relative(ROOT, abs)}`);
}

function collect(targets) {
  const specs = new Set();
  for (const target of targets) {
    const abs = path.resolve(ROOT, target);
    const rel = path.relative(ROOT, abs);
    if (rel.startsWith('..') || path.isAbsolute(rel)) {
      throw new Error(`Path is outside the repo: ${target}`);
    }
    if (!existsSync(abs)) throw new Error(`Not found: ${target}`);
    const before = specs.size;
    walk(abs, statSync(abs).isFile(), specs);
    if (specs.size === before && statSync(abs).isDirectory()) {
      throw new Error(`No spec files in ${rel || '.'}`);
    }
  }
  return [...specs].sort();
}

function parseTargets(argv) {
  const targets = [];
  let out = null;
  let headed = false;
  for (let i = 2; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--') continue;
    if (arg === '--help' || arg === '-h') return { help: true, targets, out, headed };
    if (arg === '--headed') {
      headed = true;
      continue;
    }
    if (arg === '--out') {
      out = argv[++i];
      if (!out) throw new Error('--out needs a directory');
      continue;
    }
    if (arg.startsWith('-')) throw new Error(`Unknown option: ${arg}`);
    targets.push(arg);
  }
  return { help: false, targets, out, headed };
}

function runGroup(runId) {
  const match = /^(LEX-\d+|pr-\d+|sha-[0-9a-fA-F]+|specs|manual|tools)/.exec(runId);
  return match ? match[1] : 'manual';
}

function newRunFolder() {
  const id = newRunId('manual');
  return path.join(RUNS, runGroup(id), id);
}

function owningRun(abs) {
  let dir = statSync(abs).isDirectory() ? abs : path.dirname(abs);
  const root = path.resolve(RUNS);
  while (dir === root || dir.startsWith(root + path.sep)) {
    if (existsSync(path.join(dir, 'manifest.json')) || existsSync(path.join(dir, 'planned-specs.json'))) {
      return dir;
    }
    if (dir === root) break;
    dir = path.dirname(dir);
  }
  return null;
}

function testDirFor(specs) {
  const dirs = specs.map((file) => path.dirname(file));
  let prefix = dirs[0].split(path.sep);
  for (const dir of dirs.slice(1)) {
    const parts = dir.split(path.sep);
    while (prefix.length && prefix.join(path.sep) !== parts.slice(0, prefix.length).join(path.sep)) {
      prefix.pop();
    }
  }
  return path.join(ROOT, prefix.join(path.sep) || '.');
}

function summary(runDir) {
  const report = path.join(runDir, 'playwright', 'results.json');
  const empty = { passed: 0, failed: 0, skipped: 0, flaky: 0 };
  if (!existsSync(report)) return empty;
  try {
    const stats = JSON.parse(readFileSync(report, 'utf8')).stats || {};
    return {
      passed: Number(stats.expected || 0),
      failed: Number(stats.unexpected || 0),
      skipped: Number(stats.skipped || 0),
      flaky: Number(stats.flaky || 0),
    };
  } catch {
    return empty;
  }
}

function runPlaywright(runDir, specs, headed) {
  const authState = path.join(runDir, 'auth-state.json');
  const args = ['playwright', 'test', '--workers=1', '--project=e2e'];
  if (headed) args.push('--headed');
  args.push(...specs);
  // macOS and Windows open a real window with DISPLAY unset. Only a Linux container needs xvfb.
  const virtualDisplay = headed && process.platform === 'linux' && !process.env.DISPLAY;
  if (virtualDisplay && !existsSync('/usr/bin/xvfb-run')) {
    throw new Error('Headed mode needs a display. xvfb-run is not installed in this container.');
  }
  const command = virtualDisplay ? 'xvfb-run' : 'npx';
  const commandArgs = virtualDisplay ? ['-a', '-s', '-screen 0 1440x900x24', 'npx', ...args] : args;
  return new Promise((resolve) => {
    const child = spawn(
      command,
      commandArgs,
      {
        cwd: ROOT,
        env: {
          ...process.env,
          QA_RUN_DIR: runDir,
          QA_TEST_DIR: testDirFor(specs),
          AUTH_STATE: authState,
          QA_ENV_URL: CFG.qaUrl,
          ...(headed && !virtualDisplay ? { QA_SLOWMO: '350' } : {}),
        },
        stdio: 'inherit',
      },
    );
    child.on('error', (error) => {
      console.error(error.message);
      resolve(1);
    });
    child.on('exit', (code) => resolve(code ?? 1));
  });
}

async function main() {
  const parsed = parseTargets(process.argv);
  if (parsed.help || parsed.targets.length === 0) {
    usage();
    process.exit(parsed.help ? 0 : 1);
  }

  const specs = collect(parsed.targets);
  const owners = [...new Set(parsed.targets.map((target) => owningRun(path.resolve(ROOT, target))).filter(Boolean))];
  const runDir = parsed.out
    ? path.resolve(ROOT, parsed.out)
    : owners.length === 1
      ? owners[0]
      : newRunFolder();
  mkdirSync(path.join(runDir, 'playwright'), { recursive: true });

  const session = await ensureStytchSession(runDir);
  if (session.onLogin) {
    throw new Error(`Session cookies were rejected. ${CFG.qaUrl} landed on login`);
  }
  const how = session.reused ? 'reused cached session' : `fresh login HTTP ${session.status}`;
  console.log(`session   ${how}, ${session.cookieCount} cookies, app HTTP ${session.pageStatus}`);
  console.log(`uat       ${CFG.qaUrl}`);
  console.log(`specs     ${specs.length} file${specs.length === 1 ? '' : 's'}`);
  for (const file of specs) console.log(`          ${file}`);
  const browser = !parsed.headed
    ? 'headless'
    : process.platform === 'linux' && !process.env.DISPLAY
      ? 'headed, virtual display'
      : 'headed, window on this screen';
  console.log(`browser   ${browser}`);
  console.log(`results   ${path.relative(ROOT, runDir)}/playwright/`);
  console.log('');

  const exitCode = await runPlaywright(runDir, specs, parsed.headed);
  const counts = summary(runDir);
  writeFileSync(
    path.join(runDir, 'manifest.json'),
    `${JSON.stringify({
      appUrl: CFG.qaUrl,
      specs,
      headed: parsed.headed,
      sessionReused: session.reused,
      exitCode,
      ...counts,
      finishedAt: new Date().toISOString(),
    }, null, 2)}\n`,
  );
  console.log('');
  console.log(
    `done      passed ${counts.passed}  failed ${counts.failed}  skipped ${counts.skipped}  flaky ${counts.flaky}`,
  );
  process.exit(exitCode);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
