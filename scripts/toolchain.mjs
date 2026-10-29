import { spawnSync } from 'node:child_process';
import { appendFileSync, existsSync, mkdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { ROOT, check, playwrightCliBin } from './harness-env.mjs';

const VENV_PYTHON = path.join(ROOT, 'server', '.venv', 'bin', 'python');
const REQUIREMENTS = path.join(ROOT, 'server', 'requirements.txt');
const MODEL_FALLBACK = 'amazon-bedrock/us.anthropic.claude-haiku-5-5';

function log(line) {
  const text = `${line}\n`;
  process.stderr.write(text);
  const runDir = process.env.QA_RUN_DIR;
  if (runDir) {
    mkdirSync(runDir, { recursive: true });
    appendFileSync(path.join(runDir, 'toolchain.log'), text);
  }
}

function run(cmd, args) {
  log(`$ ${cmd} ${args.join(' ')}`);
  const result = spawnSync(cmd, args, { cwd: ROOT, encoding: 'utf8' });
  const combined = `${result.stdout || ''}${result.stderr || ''}`.trim();
  if (combined) log(combined.split('\n').slice(-12).join('\n'));
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(combined.split('\n').slice(-8).join(' ').slice(0, 400) || `${cmd} exited ${result.status}`);
  }
  return (result.stdout || result.stderr || '').trim();
}

function which(name) {
  const dirs = (process.env.PATH || '').split(path.delimiter);
  for (const dir of dirs) {
    const full = path.join(dir, name);
    if (existsSync(full)) return full;
  }
  return null;
}

function ensureNodeModules() {
  const testPkg = path.join(ROOT, 'node_modules', '@playwright', 'test', 'package.json');
  const cliPkg = path.join(ROOT, 'node_modules', '@playwright', 'cli', 'package.json');
  if (existsSync(testPkg) && existsSync(cliPkg)) {
    return check('npm packages', 'pass', '@playwright/test and @playwright/cli are installed');
  }
  run('npm', ['install']);
  if (!existsSync(testPkg) || !existsSync(cliPkg)) {
    throw new Error('npm install finished without @playwright/test and @playwright/cli');
  }
  return check('npm packages', 'pass', 'Installed @playwright/test and @playwright/cli');
}

function ensureChromium() {
  run('npx', ['playwright', 'install', 'chromium']);
  const version = run('npx', ['playwright', '--version']);
  const executable = run('node', ['--input-type=module', '-e', `
    import { chromium } from 'playwright';
    import { existsSync } from 'node:fs';
    const bin = chromium.executablePath();
    if (!existsSync(bin)) { console.error(bin); process.exit(1); }
    console.log(bin);
  `]);
  return check('Chromium', 'pass', `${version}; ${executable.split('\n').pop()}`);
}

function ensurePlaywrightCli() {
  const bin = playwrightCliBin();
  const version = run(bin, ['--version']);
  return check('Playwright CLI', 'pass', `${bin} ${version}`);
}

function ensureFastApi() {
  const probe = [VENV_PYTHON, '-c', 'import fastapi, uvicorn, pydantic'];
  if (!existsSync(VENV_PYTHON)) {
    run('python3', ['-m', 'venv', path.join(ROOT, 'server', '.venv')]);
  }
  const existing = spawnSync(probe[0], probe.slice(1), { cwd: ROOT, encoding: 'utf8' });
  if (existing.status !== 0) {
    run(VENV_PYTHON, ['-m', 'pip', 'install', '-r', REQUIREMENTS]);
  }
  const imported = run(VENV_PYTHON, ['-c', 'import fastapi, uvicorn, pydantic; print(fastapi.__version__)']);
  return check('FastAPI', 'pass', `uvicorn ready, fastapi ${imported.split('\n').pop()}`);
}

function ensureOpenCode() {
  let bin = which('opencode');
  if (!bin) {
    const homeBin = path.join(process.env.HOME || '', '.opencode', 'bin');
    const candidate = path.join(homeBin, 'opencode');
    if (existsSync(candidate)) {
      process.env.PATH = `${homeBin}${path.delimiter}${process.env.PATH || ''}`;
      bin = candidate;
    }
  }
  if (!bin) {
    log('opencode is missing; running the official installer');
    run('bash', ['-lc', 'curl -fsSL https://opencode.ai/install | bash']);
    const homeBin = path.join(process.env.HOME || '', '.opencode', 'bin');
    process.env.PATH = `${homeBin}${path.delimiter}${process.env.PATH || ''}`;
    bin = which('opencode');
  }
  if (!bin) throw new Error('opencode is not on PATH after install');
  const version = run(bin, ['--version']);
  return check('OpenCode', 'pass', `${bin} ${version}`);
}

function stripJsonc(text) {
  let out = '';
  let i = 0;
  while (i < text.length) {
    const c = text[i];
    const next = text[i + 1];
    if (c === '"') {
      out += c;
      i += 1;
      while (i < text.length) {
        const ch = text[i];
        out += ch;
        if (ch === '\\') {
          if (i + 1 < text.length) out += text[i + 1];
          i += 2;
          continue;
        }
        i += 1;
        if (ch === '"') break;
      }
      continue;
    }
    if (c === '/' && next === '/') {
      i += 2;
      while (i < text.length && text[i] !== '\n') i += 1;
      continue;
    }
    if (c === '/' && next === '*') {
      i += 2;
      while (i < text.length && !(text[i] === '*' && text[i + 1] === '/')) i += 1;
      i += 2;
      continue;
    }
    out += c;
    i += 1;
  }
  return out;
}

function loadJsonc(file) {
  return JSON.parse(stripJsonc(readFileSync(file, 'utf8')));
}

function configuredValue(name) {
  const file = path.join(ROOT, '.env');
  if (existsSync(file)) {
    const match = readFileSync(file, 'utf8').match(new RegExp(`^${name}=(.*)$`, 'm'));
    if (match) return match[1].trim().replace(/^['"]|['"]$/g, '');
  }
  return (process.env[name] || '').trim().replace(/^['"]|['"]$/g, '');
}

function ensureOpenCodeSetup() {
  const config = loadJsonc(path.join(ROOT, 'opencode.jsonc'));
  const agents = config.agents || {};
  const mainModel = configuredValue('OPENCODE_MAIN_MODEL') || MODEL_FALLBACK;
  const subModel = configuredValue('OPENCODE_SUB_MODEL') || MODEL_FALLBACK;
  const expected = {
    qa: mainModel,
    'ux-auditor': subModel,
  };
  const problems = [];
  for (const [name, model] of Object.entries(expected)) {
    if (agents[name]?.model !== model) problems.push(`${name} is ${agents[name]?.model || 'missing'}`);
  }
  const quiet = (args) => {
    const result = spawnSync('opencode', args, { cwd: ROOT, encoding: 'utf8' });
    if (result.status !== 0) throw new Error((result.stderr || result.stdout || 'opencode failed').trim().slice(0, 300));
    return result.stdout || '';
  };
  const bedrockKey = configuredValue('BEDROCK_API_KEY') || configuredValue('AWS_BEARER_TOKEN_BEDROCK');
  if (!bedrockKey) {
    problems.push('Bedrock key is missing. Set BEDROCK_API_KEY');
  }
  const models = new Set(quiet(['models', '--standalone']).split('\n').map((line) => line.trim()));
  for (const id of new Set([mainModel, subModel])) {
    if (!models.has(id)) problems.push(`${id} is not available`);
  }
  if (problems.length) throw new Error(problems.join('; '));
  const listed = mainModel === subModel ? mainModel : `${mainModel}; ${subModel}`;
  return check('OpenCode setup', 'pass', `Bedrock key set; ${listed}`);
}

export function ensureToolchain() {
  const steps = [
    ['npm packages', ensureNodeModules],
    ['Chromium', ensureChromium],
    ['Playwright CLI', ensurePlaywrightCli],
    ['FastAPI', ensureFastApi],
    ['OpenCode', ensureOpenCode],
    ['OpenCode setup', ensureOpenCodeSetup],
  ];
  const checks = [];
  for (const [name, fn] of steps) {
    try {
      checks.push(fn());
    } catch (err) {
      checks.push(check(name, 'fail', err.message));
    }
  }
  return checks;
}
