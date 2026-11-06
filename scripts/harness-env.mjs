import { execFileSync } from 'node:child_process';
import { chmodSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

try {
  process.loadEnvFile(path.join(ROOT, '.env'));
} catch {
  /* missing .env is reported by the env check */
}

export function env(name, fallback = '') {
  const value = process.env[name];
  return value == null || value.trim() === '' ? fallback : value.trim();
}

export const PERSONAS = {
  admin: ['STYTCH_ADMIN_EMAIL', 'STYTCH_ADMIN_PASSWORD'],
  support: ['STYTCH_SUPPORT_EMAIL', 'STYTCH_SUPPORT_PASSWORD'],
  viewer: ['STYTCH_VIEWER_EMAIL', 'STYTCH_VIEWER_PASSWORD'],
};

/** A suite must not start on a session that will die while Playwright is still running. */
export const SESSION_REUSE_SLACK_SECONDS = 60 * 60;

export const CFG = {
  qaUrl: env('QA_ENV_URL', env('LEXFUL_APP_URL', 'https://e2e-test.uat.lexful.net')),
  apiUrl: env('STYTCH_API_URL', 'https://api.uat.lexful.net').replace(/\/$/, ''),
  slug: env('SLUG', 'e2e-test'),
  org: env('STYTCH_ORGANIZATION_ID'),
  linearKey: env('LINEAR_API_KEY'),
  linearUrl: env('LINEAR_API_URL', 'https://api.linear.app/graphql'),
  githubToken: env('GITHUB_TOKEN', env('GH_TOKEN')),
  githubOrg: env('GITHUB_ORG', 'Lexful-ai'),
  githubRepo: env('GITHUB_REPO', 'docu-stack'),
};

export function writeJson(file, value) {
  writeFileSync(file, JSON.stringify(value, null, 2) + '\n');
}

export function check(name, status, detail) {
  return { name, status, detail };
}

export async function linear(query, variables = {}) {
  if (!CFG.linearKey) throw new Error('LINEAR_API_KEY is not set');
  const res = await fetch(CFG.linearUrl, {
    method: 'POST',
    headers: { Authorization: CFG.linearKey, 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, variables }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`Linear HTTP ${res.status}`);
  if (body.errors?.length) throw new Error(body.errors.map((e) => e.message).join('; '));
  if (!body.data) throw new Error('Linear response contained no data');
  return body.data;
}

const REPO_PATH = /^\/repos\/([^/]+)\/[^/]+\//;

/**
 * Pull requests, their comments, and deployment records only. Never lists the repo tree or
 * file contents (the server's read-only clone does that), and only inside GITHUB_ORG.
 */
export async function github(apiPath, query, accept = 'application/vnd.github+json') {
  const allowed = apiPath === '/user'
    || apiPath === '/search/issues'
    || /^\/repos\/[^/]+\/[^/]+\/pulls\/\d+(\/(files|comments|reviews|commits))?$/.test(apiPath)
    || /^\/repos\/[^/]+\/[^/]+\/issues\/\d+\/comments$/.test(apiPath)
    || /^\/repos\/[^/]+\/[^/]+\/(environments|deployments)$/.test(apiPath)
    || /^\/repos\/[^/]+\/[^/]+\/deployments\/\d+\/statuses$/.test(apiPath)
    || /^\/repos\/[^/]+\/[^/]+\/compare\/[0-9a-f]{7,40}\.\.\.[0-9a-f]{7,40}$/i.test(apiPath)
    || /^\/repos\/[^/]+\/[^/]+\/commits\/[0-9a-f]{7,40}\/pulls$/i.test(apiPath);
  if (!allowed) throw new Error(`GitHub path is outside the pull request: ${apiPath}`);
  const owner = apiPath.match(REPO_PATH)?.[1];
  if (owner && owner.toLowerCase() !== CFG.githubOrg.toLowerCase()) {
    throw new Error(`GitHub path is outside ${CFG.githubOrg}: ${apiPath}`);
  }
  const url = new URL(`https://api.github.com${apiPath}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) url.searchParams.set(key, value);
  }
  const headers = {
    Accept: accept,
    'User-Agent': 'lexful-qa-opencode',
  };
  if (CFG.githubToken) headers.Authorization = `Bearer ${CFG.githubToken}`;
  const res = await fetch(url, { headers });
  const text = await res.text();
  if (!res.ok) throw new Error(`GitHub ${res.status} ${apiPath}: ${text.slice(0, 240)}`);
  return text ? JSON.parse(text) : {};
}

const LEX_KEY_RE = /\bLEX-\d+\b/gi;

export function extractLexKeys(...texts) {
  const seen = new Set();
  for (const text of texts) {
    for (const match of String(text || '').matchAll(LEX_KEY_RE)) seen.add(match[0].toUpperCase());
  }
  return [...seen].sort();
}

export function primaryLexKey(pr) {
  for (const field of ['title', 'headRef', 'body']) {
    const keys = extractLexKeys(pr?.[field]);
    if (keys.length) return keys[0];
  }
  return null;
}

function touchesUatUi(files) {
  return files.some((f) => f.startsWith('apps/docu-app/') || f.startsWith('apps/platform-app/'));
}

export function pickPrimaryPr(prs) {
  if (!prs.length) return null;
  const merged = prs.filter((p) => p.merged);
  const mergedUi = merged.filter((p) => touchesUatUi(p.files || []));
  if (mergedUi.length) return mergedUi[mergedUi.length - 1].number;
  const openUi = prs
    .filter((p) => String(p.state).toLowerCase() === 'open' && touchesUatUi(p.files || []))
    .sort((a, b) => a.number - b.number);
  if (openUi.length) return openUi[openUi.length - 1].number;
  if (merged.length) return merged[merged.length - 1].number;
  return prs[0].number;
}

function parseSetCookie(raw) {
  const parts = raw.split(';').map((p) => p.trim());
  const eq = parts[0].indexOf('=');
  if (eq < 0) return null;
  let expires;
  const maxAge = parts.find((p) => p.toLowerCase().startsWith('max-age='));
  if (maxAge) {
    const seconds = parseInt(maxAge.split('=')[1], 10);
    if (!Number.isNaN(seconds)) expires = Math.floor(Date.now() / 1000) + seconds;
  }
  return {
    name: parts[0].slice(0, eq).trim(),
    value: parts[0].slice(eq + 1).trim(),
    domain: '.lexful.net',
    path: '/',
    httpOnly: true,
    secure: true,
    sameSite: 'Lax',
    expires,
  };
}

export function personaName() {
  const name = env('STYTCH_PERSONA', 'admin').toLowerCase();
  if (!PERSONAS[name]) {
    throw new Error(`STYTCH_PERSONA must be admin, support, or viewer. Got ${name}`);
  }
  return name;
}

export function personaCredentials(name = personaName()) {
  const key = String(name || personaName()).trim().toLowerCase();
  if (!PERSONAS[key]) {
    throw new Error(`STYTCH_PERSONA must be admin, support, or viewer. Got ${key}`);
  }
  const [emailKey, passwordKey] = PERSONAS[key];
  return { name: key, emailKey, passwordKey, email: env(emailKey), password: env(passwordKey) };
}

/** Default persona cookie file. Playwright reads this when a test does not name a persona. */
export function sessionFile() {
  return path.join(ROOT, 'runs', 'cache', 'stytch', 'session.json');
}

/** Cookie file for one persona. The default persona also keeps session.json. */
export function personaSessionFile(name) {
  const creds = personaCredentials(name);
  return path.join(ROOT, 'runs', 'cache', 'stytch', `${creds.name}.json`);
}

export function sessionTargets(name = personaName()) {
  const creds = personaCredentials(name);
  const named = personaSessionFile(creds.name);
  if (creds.name === personaName()) return [sessionFile(), named];
  return [named];
}

function writeSecretJson(file, value) {
  mkdirSync(path.dirname(file), { recursive: true });
  writeJson(file, value);
  try { chmodSync(file, 0o600); } catch { /* volume may ignore mode */ }
}

function jwtPayload(token) {
  const part = String(token || '').split('.')[1];
  if (!part) return null;
  try {
    const padded = part.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (part.length % 4)) % 4);
    return JSON.parse(Buffer.from(padded, 'base64').toString('utf8'));
  } catch {
    return null;
  }
}

/**
 * Stytch's real session end. Cookie Max-Age is only how long the browser keeps
 * the cookie (months here) and is not the session lifetime (~12h).
 * Returns 0 when the claim is missing so a stale file cannot be reused.
 */
function sessionExpiry(cookies) {
  const jwt = (cookies || []).find((cookie) => cookie.name === 'stytch_session_jwt')?.value;
  const raw = jwtPayload(jwt)?.['https://stytch.com/session']?.expires_at;
  const seconds = raw ? Math.floor(Date.parse(raw) / 1000) : NaN;
  return Number.isFinite(seconds) ? seconds : 0;
}

async function probeApp(cookies) {
  const cookieHeader = cookies.map((cookie) => `${cookie.name}=${cookie.value}`).join('; ');
  const page = await fetch(CFG.qaUrl, { headers: { Cookie: cookieHeader }, redirect: 'follow' });
  return {
    landed: page.url,
    onLogin: /\/login\b/i.test(page.url),
    pageStatus: page.status,
  };
}

const ACCOUNT_FILE = path.join(ROOT, 'runs', 'cache', 'stytch', 'account-id.txt');
const API_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36';

/** 401 is the API saying the session is dead. A CDN 403 or a network error says nothing about it. */
export function apiVerdict(status) {
  if (status === 401) return 'invalid';
  if (status >= 200 && status < 300) return 'valid';
  return 'unknown';
}

/**
 * The app page answers 200 with or without a login, because the SPA checks the session later, so the
 * page cannot tell a dead session from a live one. The API can: it answers 401 to a session Stytch
 * has revoked or expired, even while the cookie's own expiry is still in the future.
 */
export async function probeApi(cookies) {
  const account = env('LEXFUL_ACCOUNT_ID') || (existsSync(ACCOUNT_FILE) ? readFileSync(ACCOUNT_FILE, 'utf8').trim() : '');
  if (!account) return { checked: false, verdict: 'unknown' };
  try {
    const res = await fetch(`${CFG.apiUrl}/v1/asset_types?limit=1`, {
      headers: {
        Cookie: cookies.map((cookie) => `${cookie.name}=${cookie.value}`).join('; '),
        'X-Account-Id': account,
        'User-Agent': API_UA,
      },
    });
    return { checked: true, status: res.status, verdict: apiVerdict(res.status) };
  } catch {
    return { checked: false, verdict: 'unknown' };
  }
}

function publishSession(record, files) {
  for (const file of files) writeSecretJson(file, record);
}

export function sessionReusable(cached, creds, now = Math.floor(Date.now() / 1000)) {
  if (!cached || cached.persona !== creds.name) return false;
  if (creds.email && cached.email && cached.email !== creds.email) return false;
  const expiresAt = sessionExpiry(cached.cookies);
  if (!(expiresAt > now + SESSION_REUSE_SLACK_SECONDS)) return false;
  return Array.isArray(cached.cookies) && cached.cookies.length > 0;
}

async function loginStytch(creds = personaCredentials()) {
  if (!CFG.org || !creds.email || !creds.password) {
    throw new Error(`Set STYTCH_ORGANIZATION_ID, ${creds.emailKey}, and ${creds.passwordKey}`);
  }
  const res = await fetch(`${CFG.apiUrl}/auth/password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      account_external_id: CFG.org,
      email: creds.email,
      password: creds.password,
    }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Stytch HTTP ${res.status}: ${text.slice(0, 180)}`);
  }
  const cookies = [];
  for (const raw of res.headers.getSetCookie?.() || []) {
    const parsed = parseSetCookie(raw);
    if (parsed) cookies.push(parsed);
  }
  const names = new Set(cookies.map((cookie) => cookie.name));
  if (!names.has('stytch_session') || !names.has('stytch_session_jwt')) {
    throw new Error('Stytch response did not set stytch_session and stytch_session_jwt');
  }
  const probe = await probeApp(cookies);
  const api = await probeApi(cookies);
  if (api.verdict === 'invalid') {
    throw new Error(`Stytch accepted the password for ${creds.email}, but the API answered ${api.status} to the new session`);
  }
  return { status: res.status, cookies, ...probe, apiStatus: api.status ?? null };
}

function sessionUsable(probe) {
  if (!probe || probe.onLogin) return false;
  return probe.pageStatus === 200 || probe.pageStatus === 403;
}

function readCached(file) {
  if (!existsSync(file)) return null;
  try {
    return JSON.parse(readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
}

/**
 * Sign in as `persona`, or as STYTCH_PERSONA when omitted.
 * A named persona is stored at runs/cache/stytch/<persona>.json.
 * The default persona is also stored at session.json, which existing specs read.
 * Reuse a file only when the persona matches and more than an hour remains.
 */
export async function ensureStytchSession({ force = false, persona } = {}) {
  const creds = personaCredentials(persona);
  const files = sessionTargets(creds.name);
  const now = Math.floor(Date.now() / 1000);
  if (!force) {
    for (const file of files) {
      const cached = readCached(file);
      if (!cached || !sessionReusable(cached, creds, now)) continue;
      try {
        const probe = await probeApp(cached.cookies);
        if (!sessionUsable(probe)) continue;
        const api = await probeApi(cached.cookies);
        if (api.verdict === 'invalid') continue; // revoked before its expiry: sign in again below
        probe.apiStatus = api.status ?? null;
        const record = {
          ...cached,
          persona: creds.name,
          email: creds.email,
          origins: [],
          expiresAt: sessionExpiry(cached.cookies),
          probe,
          reusedAt: new Date().toISOString(),
        };
        publishSession(record, files);
        return {
          reused: true,
          persona: creds.name,
          status: cached.status,
          cookieCount: cached.cookies.length,
          file: path.relative(ROOT, files[files.length - 1]),
          ...probe,
        };
      } catch (err) {
        if (err instanceof Error && err.message.startsWith('STYTCH_PERSONA')) throw err;
      }
    }
  }
  const fresh = await loginStytch(creds);
  const record = {
    persona: creds.name,
    email: creds.email,
    capturedAt: new Date().toISOString(),
    expiresAt: sessionExpiry(fresh.cookies),
    status: fresh.status,
    cookies: fresh.cookies,
    origins: [],
    probe: { landed: fresh.landed, onLogin: fresh.onLogin, pageStatus: fresh.pageStatus, apiStatus: fresh.apiStatus },
  };
  publishSession(record, files);
  return {
    reused: false,
    persona: creds.name,
    status: fresh.status,
    cookieCount: fresh.cookies.length,
    file: path.relative(ROOT, files[files.length - 1]),
    landed: fresh.landed,
    onLogin: fresh.onLogin,
    pageStatus: fresh.pageStatus,
    apiStatus: fresh.apiStatus,
  };
}

export function playwrightCliBin() {
  const local = path.join(ROOT, 'node_modules', '.bin', 'playwright-cli');
  if (existsSync(local)) return local;
  return 'playwright-cli';
}

export function toolVersions() {
  const playwright = execFileSync('npx', ['playwright', '--version'], { cwd: ROOT, encoding: 'utf8' }).trim();
  let cli = '';
  try {
    cli = execFileSync(playwrightCliBin(), ['--version'], { cwd: ROOT, encoding: 'utf8' }).trim();
  } catch (err) {
    throw new Error(`playwright-cli is not installed (${err.message})`);
  }
  return { playwright, cli };
}

/** Pull requests associated with a commit. Used by the deploy webhook. */
export async function pullRequestForSha(sha) {
  const { githubOrg: owner, githubRepo: repo } = CFG;
  const data = await github(`/repos/${owner}/${repo}/commits/${sha}/pulls`);
  const list = Array.isArray(data) ? data : [];
  for (const raw of list) {
    const ticket = primaryLexKey({ title: raw.title, headRef: raw.head?.ref, body: raw.body });
    if (ticket) return { number: raw.number, ticket };
  }
  if (list[0]?.number) return { number: list[0].number, ticket: null };
  throw new Error(`No pull request is associated with ${sha}`);
}

export function acceptanceCriteria(description) {
  const text = description || '';
  const headed = text.match(/(?:^|\n)#{1,3}\s*(?:acceptance criteria|ac|given\/when\/then)\b[:\s]*([\s\S]+)/i);
  if (headed?.[1]) return headed[1].trim();
  const labeled = text.match(/(?:^|\n)\*{0,2}acceptance criteria\*{0,2}\s*[:\-]\s*([\s\S]+)/i);
  if (labeled?.[1]) return labeled[1].trim();
  return text.trim();
}

const ISSUE_FIELDS = `
  id identifier title description url
  state { name }
  parent { identifier }
  children { nodes { identifier } }
  relations { nodes { relatedIssue { identifier } } }
  attachments { nodes { url title } }
  comments(first: 100) { nodes { body createdAt user { name } } pageInfo { hasNextPage } }
`;

const PR_URL = /github\.com\/([^/\s]+)\/([^/\s]+)\/pull\/(\d+)/i;

/** GitHub pull requests linked on the Linear issue, in any repo of GITHUB_ORG. */
export function linkedPullRequests(issue) {
  const found = [];
  for (const node of issue?.attachments?.nodes || []) {
    const match = String(node?.url || '').match(PR_URL);
    if (!match || match[1].toLowerCase() !== CFG.githubOrg.toLowerCase()) continue;
    found.push({ repo: `${match[1]}/${match[2]}`, number: Number(match[3]) });
  }
  return found;
}

function mapIssue(issue, relation) {
  const description = issue.description || '';
  return {
    relation,
    id: issue.id,
    key: issue.identifier,
    summary: issue.title || '',
    description,
    acceptanceCriteria: acceptanceCriteria(description),
    url: issue.url || '',
    status: issue.state?.name || '',
    parent: issue.parent?.identifier || null,
    children: (issue.children?.nodes || []).map((n) => n.identifier).filter(Boolean),
    linkedKeys: (issue.relations?.nodes || []).map((n) => n.relatedIssue?.identifier).filter(Boolean),
    linkedPullRequests: linkedPullRequests(issue),
    attachments: (issue.attachments?.nodes || []).map((n) => ({ url: n?.url || '', title: n?.title || '' })).filter((n) => n.url),
    // Full text, oldest first. The brief shows the newest and points at context/ticket.md for the rest.
    comments: (issue.comments?.nodes || [])
      .filter((n) => n?.body)
      .map((n) => ({ author: n.user?.name || '', at: n.createdAt || '', body: n.body }))
      .sort((a, b) => a.at.localeCompare(b.at)),
    commentsTruncated: Boolean(issue.comments?.pageInfo?.hasNextPage),
  };
}

async function fetchIssue(key) {
  const data = await linear(
    `query Issue($id: String!) { issue(id: $id) { ${ISSUE_FIELDS} } }`,
    { id: key.toUpperCase() },
  );
  if (!data.issue) throw new Error(`Linear issue not found: ${key}`);
  return data.issue;
}

/** One ticket and nothing it links to. scripts/lookup.mjs uses this: a lookup is one hop, not a walk. */
export async function fetchTicketOnly(key) {
  return mapIssue(await fetchIssue(key), 'lookup');
}

/** The named ticket plus one hop of Linear parent, children, and relations. No team search. */
export async function fetchTicket(key) {
  const issue = await fetchIssue(key);
  const ticket = mapIssue(issue, 'self');
  const links = [
    ...ticket.children.map((id) => ['child', id]),
    ...ticket.linkedKeys.map((id) => ['related', id]),
    ...(ticket.parent ? [['parent', ticket.parent]] : []),
  ];
  const seen = new Set([ticket.key]);
  const connectedTickets = [];
  for (const [relation, id] of links) {
    if (!id || seen.has(id)) continue;
    seen.add(id);
    try {
      connectedTickets.push(mapIssue(await fetchIssue(id), relation));
    } catch (err) {
      connectedTickets.push({ relation, key: id, error: err.message });
    }
  }
  return { ...ticket, connectedTickets };
}

/** Every page of a GitHub list, up to `cap` items. */
export async function githubPages(apiPath, cap = 300, query = {}) {
  const items = [];
  for (let page = 1; items.length < cap; page += 1) {
    const data = await github(apiPath, { ...query, per_page: '100', page: String(page) });
    const list = Array.isArray(data) ? data : [];
    items.push(...list);
    if (list.length < 100) break;
  }
  return items.slice(0, cap);
}

export async function fetchPullRequest(number, fullRepo = `${CFG.githubOrg}/${CFG.githubRepo}`) {
  const [owner, repo] = fullRepo.split('/');
  const raw = await github(`/repos/${owner}/${repo}/pulls/${number}`);
  const files = await githubPages(`/repos/${owner}/${repo}/pulls/${number}/files`, 300);
  // Reviewers' questions are the cheapest bug leads there are. Kept in full; the brief shows a few.
  const [inline, conversation, reviews] = await Promise.all([
    githubPages(`/repos/${owner}/${repo}/pulls/${number}/comments`, 200).catch(() => []),
    githubPages(`/repos/${owner}/${repo}/issues/${number}/comments`, 100).catch(() => []),
    githubPages(`/repos/${owner}/${repo}/pulls/${number}/reviews`, 100).catch(() => []),
  ]);
  const isBot = (user) => /\[bot\]$|^github-actions/i.test(String(user?.login || ''));
  const reviewComments = [
    ...inline.filter((c) => !isBot(c.user)).map((c) => ({ path: c.path, line: c.line || c.original_line || null, author: c.user?.login || '', body: c.body || '' })),
    ...reviews.filter((r) => r.body && !isBot(r.user)).map((r) => ({ path: null, line: null, author: r.user?.login || '', state: r.state, body: r.body || '' })),
  ];
  const discussion = conversation.filter((c) => !isBot(c.user)).map((c) => ({ author: c.user?.login || '', body: c.body || '' }));
  const fileDetails = Array.isArray(files)
    ? files.map((item) => ({
      filename: item.filename,
      status: item.status || '',
      patch: item.patch || '',
      additions: item.additions,
      deletions: item.deletions,
    }))
    : [];
  return {
    repo: fullRepo,
    number: raw.number,
    title: raw.title || '',
    body: raw.body || '',
    state: raw.state || '',
    merged: Boolean(raw.merged_at),
    mergedAt: raw.merged_at,
    mergeCommitSha: raw.merged_at ? raw.merge_commit_sha || '' : '',
    reviewComments,
    discussion,
    htmlUrl: raw.html_url || '',
    headRef: raw.head?.ref || '',
    baseRef: raw.base?.ref || 'main',
    files: fileDetails.map((f) => f.filename),
    fileDetails,
  };
}

/**
 * PRs for this ticket: the ones linked on the Linear issue (any repo of the org), plus the
 * ones whose title or body mentions the key in the default repo. Does not list a repository.
 */
/**
 * A linked pull request in another repository of the org that the token cannot read (GitHub answers
 * 404 for a private repo it has no access to, 403 when access is refused). It is skipped, not fatal:
 * one ops-repo link must not stop the run. In the default repository the same answer is a real token
 * problem and still fails.
 */
export function skippablePullError(err, fullRepo, defaultRepo) {
  return fullRepo.toLowerCase() !== defaultRepo.toLowerCase() && /^GitHub (403|404) /.test(String(err?.message || ''));
}

export async function searchPullRequests(ticketKey, known = [], linked = [], unreadable = []) {
  const { githubOrg: owner, githubRepo: repo } = CFG;
  const defaultRepo = `${owner}/${repo}`;
  const key = (fullRepo, number) => `${fullRepo.toLowerCase()}#${number}`;
  const wanted = new Map(linked.map((item) => [key(item.repo, item.number), item]));
  for (let page = 1; page <= 3; page += 1) {
    const data = await github('/search/issues', {
      q: `repo:${defaultRepo} is:pr ${ticketKey.toUpperCase()}`,
      per_page: '30',
      page: String(page),
    });
    for (const item of data.items || []) wanted.set(key(defaultRepo, item.number), { repo: defaultRepo, number: item.number });
    if ((data.items || []).length < 30) break;
  }
  const have = new Map(known.filter((pr) => pr?.number != null).map((pr) => [key(pr.repo || defaultRepo, pr.number), pr]));
  const pulls = [];
  for (const [id, item] of wanted) {
    if (have.get(id)) {
      pulls.push(have.get(id));
      continue;
    }
    try {
      pulls.push(await fetchPullRequest(item.number, item.repo));
    } catch (err) {
      if (!skippablePullError(err, item.repo, defaultRepo)) throw err;
      unreadable.push({ repo: item.repo, number: item.number, reason: String(err.message).slice(0, 60) });
    }
  }
  for (const [id, pr] of have) if (!wanted.has(id)) pulls.push(pr);
  return pulls.sort((a, b) => String(a.mergedAt || '').localeCompare(String(b.mergedAt || '')));
}

/**
 * Is each merged PR on UAT? GitHub keeps a deployment per environment (docu-app-uat, ...).
 * A changed path segment that names an environment (`apps/docu-app/...` → docu-app-uat)
 * selects it. The PR is deployed when its merge commit is an ancestor of the last successful
 * deployment there.
 */
export async function deploymentStatus(pulls) {
  const defaultRepo = `${CFG.githubOrg}/${CFG.githubRepo}`;
  const merged = pulls.filter((p) => p.merged && p.mergeCommitSha && (p.repo || defaultRepo) === defaultRepo);
  const open = pulls.filter((p) => !p.merged && String(p.state).toLowerCase() === 'open');
  if (!merged.length) {
    return { summary: open.length ? `no merged PR; ${open.length} open PR(s) are not on UAT` : 'no merged PR to check', build: '', components: [] };
  }
  const [owner, repo] = defaultRepo.split('/');
  const envs = ((await github(`/repos/${owner}/${repo}/environments`, { per_page: '100' })).environments || [])
    .map((e) => e.name).filter((name) => /-uat$/.test(name));
  const latest = new Map();
  async function lastGood(env) {
    if (latest.has(env)) return latest.get(env);
    let found = null;
    for (const d of await github(`/repos/${owner}/${repo}/deployments`, { environment: env, per_page: '10' })) {
      const statuses = await github(`/repos/${owner}/${repo}/deployments/${d.id}/statuses`, { per_page: '5' });
      if ((statuses || []).some((s) => s.state === 'success')) { found = { sha: d.sha, at: d.created_at }; break; }
    }
    latest.set(env, found);
    return found;
  }
  const components = [];
  for (const pr of merged) {
    const segments = new Set((pr.files || []).flatMap((f) => f.split('/').slice(0, 3)));
    const targets = envs.filter((env) => segments.has(env.replace(/-uat$/, '')));
    for (const env of targets) {
      const good = await lastGood(env);
      let included = null;
      if (good?.sha) {
        try {
          const cmp = await github(`/repos/${owner}/${repo}/compare/${pr.mergeCommitSha}...${good.sha}`);
          included = cmp.status === 'ahead' || cmp.status === 'identical';
        } catch { included = null; }
      }
      components.push({ pr: pr.number, env, deployedSha: good?.sha || '', deployedAt: good?.at || '', included });
    }
  }
  const missing = components.filter((c) => c.included === false);
  const unknown = components.filter((c) => c.included === null);
  const summary = !components.length
    ? 'no UAT environment matches the changed paths; deployment not verified'
    : missing.length
      ? `NOT DEPLOYED: ${missing.map((c) => `#${c.pr} on ${c.env}`).join(', ')} (UAT runs an older build)`
      : unknown.length
        ? `unverified for ${unknown.map((c) => c.env).join(', ')}; deployed on ${components.filter((c) => c.included).map((c) => c.env).join(', ') || 'none'}`
        : `deployed: ${components.map((c) => `#${c.pr} on ${c.env} (${c.deployedSha.slice(0, 8)}, ${c.deployedAt.slice(0, 16)})`).join(', ')}`;
  const build = components.find((c) => c.deployedSha)?.deployedSha?.slice(0, 12) || '';
  return { summary, build, components };
}

export function parseArgs(argv) {
  const args = argv.slice(2);
  let pr = null;
  let ticket = null;
  let out = null;
  let sha = null;
  let toolsOnly = false;
  let sessionOnly = false;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--pr') pr = Number(args[++i]);
    else if (/^--pr=\d+$/.test(args[i])) pr = Number(args[i].slice(5));
    else if (args[i] === '--out') out = args[++i];
    else if (args[i] === '--sha') sha = args[++i];
    else if (args[i] === '--tools') toolsOnly = true;
    else if (args[i] === '--session-only') sessionOnly = true;
    else if (/^LEX-\d+$/i.test(args[i])) ticket = args[i].toUpperCase();
    else if (/^\d+$/.test(args[i])) pr = Number(args[i]);
  }
  return { pr, ticket, out, sha, toolsOnly, sessionOnly };
}
