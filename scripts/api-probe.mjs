import { existsSync, mkdirSync, readFileSync, appendFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { CFG, ROOT, personaSessionFile, sessionFile } from './harness-env.mjs';
import { signInPersona } from './persona.mjs';

/**
 * Authenticated API probe for the QA agent.
 *
 *   node scripts/api-probe.mjs GET /v1/asset_types?limit=5
 *   node scripts/api-probe.mjs --persona all GET /v1/permission_catalog
 *   node scripts/api-probe.mjs --persona viewer --write POST /v1/x --body '{"a":1}'
 *
 * The agent may not read runs/cache, so this script holds the cookies and the
 * account id. It prints one line per persona: status and the first --max
 * characters of the body (default 700), so a probe costs a few hundred tokens.
 * Every call is appended to <run dir>/api-probes.jsonl when QA_RUN_DIR or --run is set.
 */

const NAMES = ['admin', 'support', 'viewer'];
const WRITE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
const ACCOUNT_FILE = path.join(ROOT, 'runs', 'cache', 'stytch', 'account-id.txt');
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36';

export function parseProbeArgs(argv) {
  const out = { persona: 'admin', write: false, max: 700, body: null, run: process.env.QA_RUN_DIR || '', rest: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--write') out.write = true;
    else if (arg === '--persona') out.persona = String(argv[++i] || '').toLowerCase();
    else if (arg === '--body') out.body = argv[++i];
    else if (arg === '--max') out.max = Number(argv[++i]) || out.max;
    else if (arg === '--run') out.run = argv[++i];
    else out.rest.push(arg);
  }
  const [method, target] = out.rest;
  if (!method || !target) throw new Error('Usage: api-probe.mjs [--persona admin|support|viewer|all] [--write] [--body JSON] METHOD /v1/path');
  out.method = method.toUpperCase();
  out.target = target;
  if (out.persona !== 'all' && !NAMES.includes(out.persona)) throw new Error(`persona must be admin, support, viewer, or all. Got ${out.persona}`);
  if (WRITE_METHODS.has(out.method) && !out.write) {
    throw new Error(`${out.method} changes data. Pass --write, and delete what you create before you finish.`);
  }
  return out;
}

function cookieHeader(persona) {
  const files = persona === 'admin' ? [personaSessionFile('admin'), sessionFile()] : [personaSessionFile(persona)];
  for (const file of files) {
    if (!existsSync(file)) continue;
    const data = JSON.parse(readFileSync(file, 'utf8'));
    if (Array.isArray(data.cookies) && data.cookies.length) return data.cookies.map((c) => `${c.name}=${c.value}`).join('; ');
  }
  return '';
}

async function discoverAccountId(header) {
  const cached = process.env.LEXFUL_ACCOUNT_ID || (existsSync(ACCOUNT_FILE) ? readFileSync(ACCOUNT_FILE, 'utf8').trim() : '');
  if (cached) return cached;
  const { chromium } = await import('playwright');
  const browser = await chromium.launch();
  try {
    const context = await browser.newContext();
    const cookies = header.split('; ').map((pair) => {
      const [name, ...rest] = pair.split('=');
      return { name, value: rest.join('='), domain: `.${new URL(CFG.apiUrl).hostname.split('.').slice(-2).join('.')}`, path: '/' };
    });
    await context.addCookies(cookies);
    const page = await context.newPage();
    let found = '';
    page.on('request', (request) => {
      const id = request.headers()['x-account-id'];
      if (id && !found) found = id;
    });
    await page.goto(CFG.qaUrl, { waitUntil: 'domcontentloaded' });
    for (let i = 0; i < 40 && !found; i += 1) await page.waitForTimeout(500);
    if (!found) throw new Error('Could not learn X-Account-Id from the app. Set LEXFUL_ACCOUNT_ID.');
    mkdirSync(path.dirname(ACCOUNT_FILE), { recursive: true });
    writeFileSync(ACCOUNT_FILE, `${found}\n`, { mode: 0o600 });
    return found;
  } finally {
    await browser.close();
  }
}

async function call(args, persona) {
  let header = cookieHeader(persona);
  if (!header) {
    await signInPersona({ persona });
    header = cookieHeader(persona);
  }
  if (!header) throw new Error(`No session for ${persona}. Run: node scripts/persona.mjs ${persona}`);
  const url = args.target.startsWith('http') ? args.target : `${CFG.apiUrl}${args.target}`;
  if (new URL(url).host !== new URL(CFG.apiUrl).host) throw new Error('api-probe only calls the configured API host');
  const headers = { Cookie: header, 'X-Account-Id': await discoverAccountId(header), Accept: 'application/json', 'User-Agent': UA };
  if (args.body) headers['Content-Type'] = 'application/json';
  let res;
  let refreshed = false;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    res = await fetch(url, { method: args.method, headers, body: args.body || undefined });
    if (res.status === 401 && !refreshed) {
      // An expired cookie is not a permission answer. Sign the persona in again once.
      refreshed = true;
      await signInPersona({ persona, fresh: true });
      headers.Cookie = cookieHeader(persona);
      continue;
    }
    if (res.status !== 403) break;
    const peek = await res.clone().text();
    if (!/request blocked|cloudfront/i.test(peek)) break; // a real API 403, not the CDN
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  const text = await res.text();
  const blocked = res.status === 403 && /request blocked|cloudfront/i.test(text);
  return { persona, status: res.status, blocked, excerpt: text.replace(/\s+/g, ' ').slice(0, args.max) };
}

function record(args, result) {
  if (!args.run) return;
  mkdirSync(args.run, { recursive: true });
  appendFileSync(path.join(args.run, 'api-probes.jsonl'), `${JSON.stringify({
    at: new Date().toISOString(), method: args.method, target: args.target, body: args.body || undefined, persona: result.persona,
    status: result.status, cdn_block: result.blocked, excerpt: result.excerpt,
  })}\n`);
}

export async function runProbe(args) {
  const personas = args.persona === 'all' ? NAMES : [args.persona];
  const results = [];
  for (const persona of personas) {
    try {
      results.push(await call(args, persona));
    } catch (err) {
      results.push({ persona, status: 'ERR', excerpt: err instanceof Error ? err.message : String(err) });
    }
  }
  return results;
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));
if (isMain) {
  try {
    const args = parseProbeArgs(process.argv.slice(2));
    const results = await runProbe(args);
    for (const r of results) {
      record(args, r);
      const cdn = r.blocked ? ' [CDN block, not a product result]' : '';
      console.log(`${args.method} ${args.target}  ${r.persona}  ${r.status}${cdn}  ${r.excerpt}`);
    }
  } catch (err) {
    console.error(err instanceof Error ? err.message : String(err));
    process.exit(1);
  }
}
