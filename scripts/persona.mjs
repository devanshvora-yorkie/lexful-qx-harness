import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { ensureStytchSession, personaCredentials } from './harness-env.mjs';

const NAMES = new Set(['admin', 'support', 'viewer']);

export function parsePersonaArgs(argv) {
  const fresh = argv.includes('--fresh');
  const names = argv.filter((arg) => !arg.startsWith('-'));
  if (names.length > 1) {
    throw new Error('Pass one persona: admin, support, or viewer');
  }
  const persona = names[0] ? names[0].toLowerCase() : null;
  if (persona && !NAMES.has(persona)) {
    throw new Error(`Persona must be admin, support, or viewer. Got ${persona}`);
  }
  return { fresh, persona };
}

function lineFor(session) {
  const how = session.reused ? 'reused' : 'refreshed';
  return `session ${how}  persona ${session.persona}  cookies ${session.cookieCount}  app HTTP ${session.pageStatus}  file ${session.file}`;
}

async function askServer(persona, fresh) {
  const port = process.env.QA_SERVER_PORT || '8787';
  let response;
  try {
    response = await fetch(`http://127.0.0.1:${port}/internal/persona`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ persona, fresh }),
    });
  } catch {
    throw new Error('The harness server is not running, so this persona cannot be signed in from here');
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || `Persona login failed with HTTP ${response.status}`);
  }
  return body.line || lineFor(body);
}

export async function signInPersona({ persona, fresh = false, direct = false } = {}) {
  const creds = personaCredentials(persona || undefined);
  if (!direct && !creds.password) return askServer(creds.name, fresh);
  const session = await ensureStytchSession({ force: fresh, persona: creds.name });
  if (session.onLogin) {
    throw new Error(`session rejected for persona ${creds.name}. The app landed on login`);
  }
  return lineFor(session);
}

const isMain = process.argv[1]
  && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));

if (isMain) {
  try {
    const args = parsePersonaArgs(process.argv.slice(2));
    const line = await signInPersona({
      ...args,
      direct: process.env.PERSONA_DIRECT === '1',
    });
    console.log(line);
  } catch (err) {
    console.error(err instanceof Error ? err.message : String(err));
    process.exit(1);
  }
}
