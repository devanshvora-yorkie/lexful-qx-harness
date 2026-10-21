import * as fs from 'fs';
import * as path from 'path';

/**
 * Authenticate with Lexful UAT and return session cookies.
 * Uses the custom /auth/password proxy endpoint that wraps Stytch internally.
 */

export interface AuthCookies {
  name: string;
  value: string;
  domain: string;
  path: string;
  httpOnly: boolean;
  secure: boolean;
  sameSite: 'Lax' | 'Strict' | 'None';
  expires?: number; // Unix timestamp (seconds)
}

// .env sits beside this file; missing it is fine — only the API-refresh path needs the password
try { process.loadEnvFile(path.join(__dirname, '.env')); } catch { /* env comes from shell instead */ }

const CFG = {
  api: process.env.STYTCH_API_URL || 'https://api.uat.lexful.net',
  org: process.env.STYTCH_ORGANIZATION_ID ?? '',
  email: process.env.STYTCH_ADMIN_EMAIL ?? '',
  password: process.env.STYTCH_ADMIN_PASSWORD ?? '',
};

const AUTH_STATE_PATH = process.env.AUTH_STATE
  ? path.resolve(process.env.AUTH_STATE)
  : path.join(__dirname, 'auth-state.json');

/**
 * Parse a Set-Cookie header value into Playwright-ready cookie objects.
 */
function parseSetCookie(raw: string): AuthCookies | null {
  const parts = raw.split(';').map(p => p.trim());
  const nv = parts[0];
  const eqIdx = nv.indexOf('=');
  if (eqIdx < 0) return null;

  const name = nv.slice(0, eqIdx).trim();
  const value = nv.slice(eqIdx + 1).trim();

  let expires: number | undefined;
  const maxAgePart = parts.find(p => p.toLowerCase().startsWith('max-age='));
  if (maxAgePart) {
    const maxAgeSec = parseInt(maxAgePart.split('=')[1], 10);
    if (!isNaN(maxAgeSec)) {
      expires = Math.floor(Date.now() / 1000) + maxAgeSec;
    }
  }

  return {
    name,
    value,
    domain: '.lexful.net',
    path: '/',
    httpOnly: true,
    secure: true,
    sameSite: 'Lax' as const,
    expires,
  };
}

/**
 * Call the auth endpoint and return parsed cookies ready for context.addCookies().
 */
async function fetchFreshCookies(): Promise<AuthCookies[]> {
  const res = await fetch(CFG.api + '/auth/password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      account_external_id: CFG.org,
      email: CFG.email,
      password: CFG.password,
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Auth failed HTTP ${res.status}: ${text}`);
  }

  const raw = res.headers.getSetCookie();
  const cookies: AuthCookies[] = [];
  for (const cookie of raw) {
    const parsed = parseSetCookie(cookie);
    if (parsed) cookies.push(parsed);
  }

  // Save to file for future test runs
  try {
    fs.writeFileSync(AUTH_STATE_PATH, JSON.stringify({ cookies }, null, 2));
  } catch { /* ignore save errors */ }

  return cookies;
}

/**
 * Load cookies from saved auth-state.json file.
 * Returns null if the file doesn't exist or has no cookies.
 */
function loadSavedCookies(): AuthCookies[] | null {
  try {
    if (!fs.existsSync(AUTH_STATE_PATH)) return null;
    const raw = fs.readFileSync(AUTH_STATE_PATH, 'utf-8');
    const data = JSON.parse(raw);
    if (data.cookies && Array.isArray(data.cookies) && data.cookies.length > 0) {
      return data.cookies;
    }
  } catch { /* ignore parse errors */ }
  return null;
}

/**
 * Get auth cookies — uses saved file first (fast, avoids rate limits),
 * falls back to API call if no saved state exists.
 */
export async function getLexfulCookies(): Promise<AuthCookies[]> {
  const saved = loadSavedCookies();
  if (saved) {
    // shortcut: sessions last ~12h, <1h of slack; upgrade to proactive refresh if a run ever spans expiry
    const now = Math.floor(Date.now() / 1000);
    const alive = saved.every(c => !c.expires || c.expires > now + 60);
    if (alive) return saved;
    console.warn('auth-state.json expired — refreshing via API');
  }
  return fetchFreshCookies();
}

/**
 * Inject auth into a Playwright browser context.
 */
export async function injectAuthCookies(context: any): Promise<void> {
  const cookies = await getLexfulCookies();
  await context.addCookies(cookies);
}
