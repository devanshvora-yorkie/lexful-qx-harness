import { spawnSync } from 'child_process';
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

const PERSONA_ENV = {
  admin: ['STYTCH_ADMIN_EMAIL', 'STYTCH_ADMIN_PASSWORD'],
  support: ['STYTCH_SUPPORT_EMAIL', 'STYTCH_SUPPORT_PASSWORD'],
  viewer: ['STYTCH_VIEWER_EMAIL', 'STYTCH_VIEWER_PASSWORD'],
} as const;

const SESSION_FILE = path.join(__dirname, 'runs', 'cache', 'stytch', 'session.json');

function personaName(requested?: string): keyof typeof PERSONA_ENV {
  const name = (requested || process.env.STYTCH_PERSONA || 'admin').trim().toLowerCase();
  if (!(name in PERSONA_ENV)) {
    throw new Error(`STYTCH_PERSONA must be admin, support, or viewer. Got ${name}`);
  }
  return name as keyof typeof PERSONA_ENV;
}

function sessionPath(): string {
  return process.env.AUTH_STATE ? path.resolve(process.env.AUTH_STATE) : SESSION_FILE;
}

function personaPath(persona: keyof typeof PERSONA_ENV): string {
  return path.join(__dirname, 'runs', 'cache', 'stytch', `${persona}.json`);
}

interface SessionFile {
  persona?: string;
  email?: string;
  cookies?: AuthCookies[];
}

function loadSession(file = sessionPath()): SessionFile | null {
  try {
    if (!fs.existsSync(file)) return null;
    const data = JSON.parse(fs.readFileSync(file, 'utf-8'));
    if (!data || !Array.isArray(data.cookies) || data.cookies.length === 0) return null;
    return data;
  } catch {
    return null;
  }
}

/** Stytch session end from the JWT. Cookie Max-Age is not the session lifetime. */
function sessionExpiry(cookies: AuthCookies[]): number {
  const jwt = cookies.find(c => c.name === 'stytch_session_jwt')?.value;
  const part = jwt?.split('.')[1];
  if (!part) return 0;
  try {
    const padded = part.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (part.length % 4)) % 4);
    const payload = JSON.parse(Buffer.from(padded, 'base64').toString('utf8'));
    const raw = payload?.['https://stytch.com/session']?.expires_at;
    const seconds = raw ? Math.floor(Date.parse(raw) / 1000) : NaN;
    return Number.isFinite(seconds) ? seconds : 0;
  } catch {
    return 0;
  }
}

/**
 * Cookies for one persona.
 * Omit `persona` to use STYTCH_PERSONA from runs/cache/stytch/session.json.
 * Pass `support` or `viewer` to use runs/cache/stytch/<persona>.json.
 * A refresh runs scripts/persona.mjs. That script signs in when this process
 * has the password, and otherwise asks the harness server on localhost.
 */
export async function getLexfulCookies(persona?: string): Promise<AuthCookies[]> {
  const name = personaName(persona);
  const named = Boolean(persona);
  const file = named ? personaPath(name) : sessionPath();
  const saved = loadSession(file) || (name === personaName() ? loadSession(sessionPath()) : null);
  const now = Math.floor(Date.now() / 1000);
  const samePersona = !saved?.persona || saved.persona === name;
  if (saved?.cookies && samePersona && sessionExpiry(saved.cookies) > now + 60) {
    return saved.cookies;
  }
  const args = [path.join(__dirname, 'scripts', 'persona.mjs'), name];
  const result = spawnSync(process.execPath, args, {
    cwd: __dirname,
    env: process.env,
    encoding: 'utf8',
  });
  if (result.status !== 0) {
    const detail = (result.stderr || result.stdout || '').trim().slice(0, 180);
    throw new Error(`Stytch session expired for persona ${name}${detail ? `: ${detail}` : ''}`);
  }
  const fresh = loadSession(named ? personaPath(name) : sessionPath())
    || loadSession(personaPath(name))
    || (name === personaName() ? loadSession(sessionPath()) : null);
  if (!fresh?.cookies) {
    throw new Error(`Stytch session expired for persona ${name}`);
  }
  return fresh.cookies;
}

/**
 * Inject auth into a Playwright browser context.
 * The second argument selects admin, support, or viewer. The default is STYTCH_PERSONA.
 */
export async function injectAuthCookies(context: any, persona?: string): Promise<void> {
  const cookies = await getLexfulCookies(persona);
  await context.addCookies(cookies);
}
