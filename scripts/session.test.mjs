import assert from 'node:assert/strict';
import test from 'node:test';
import {
  SESSION_REUSE_SLACK_SECONDS,
  personaCredentials,
  sessionReusable,
  sessionTargets,
} from './harness-env.mjs';
import { parsePersonaArgs } from './persona.mjs';

function jwt(expiresAt) {
  const payload = Buffer.from(JSON.stringify({
    'https://stytch.com/session': { expires_at: expiresAt },
  })).toString('base64url');
  return `e30.${payload}.sig`;
}

function cached(persona, email, expiresAt) {
  return {
    persona,
    email,
    cookies: [{ name: 'stytch_session_jwt', value: jwt(expiresAt) }],
  };
}

const creds = { name: 'admin', email: 'admin@example.com', emailKey: 'STYTCH_ADMIN_EMAIL', passwordKey: 'STYTCH_ADMIN_PASSWORD', password: 'x' };
const now = 1_700_000_000;

test('a session for another persona is not reused', () => {
  const expires = new Date((now + SESSION_REUSE_SLACK_SECONDS + 60) * 1000).toISOString();
  assert.equal(sessionReusable(cached('viewer', 'view@example.com', expires), creds, now), false);
});

test('a session inside the slack window is not reused', () => {
  const expires = new Date((now + SESSION_REUSE_SLACK_SECONDS - 1) * 1000).toISOString();
  assert.equal(sessionReusable(cached('admin', creds.email, expires), creds, now), false);
});

test('the same persona with more than an hour left is reused', () => {
  const expires = new Date((now + SESSION_REUSE_SLACK_SECONDS + 60) * 1000).toISOString();
  assert.equal(sessionReusable(cached('admin', creds.email, expires), creds, now), true);
});

test('a named persona keeps its own file and the default also updates session.json', () => {
  const previous = process.env.STYTCH_PERSONA;
  process.env.STYTCH_PERSONA = 'admin';
  const support = sessionTargets('support').map((file) => file.split('/').pop());
  const admin = sessionTargets('admin').map((file) => file.split('/').pop());
  assert.deepEqual(support, ['support.json']);
  assert.deepEqual(admin, ['session.json', 'admin.json']);
  if (previous == null) delete process.env.STYTCH_PERSONA;
  else process.env.STYTCH_PERSONA = previous;
});

test('the persona script accepts one name', () => {
  assert.deepEqual(parsePersonaArgs(['support']), { fresh: false, persona: 'support' });
  assert.deepEqual(parsePersonaArgs(['--fresh', 'viewer']), { fresh: true, persona: 'viewer' });
  assert.equal(parsePersonaArgs([]).persona, null);
  assert.throws(() => parsePersonaArgs(['owner']), /admin, support, or viewer/);
  assert.throws(() => parsePersonaArgs(['admin', 'support']), /one persona/);
});

test('persona names are admin, support, or viewer', () => {
  const previous = process.env.STYTCH_PERSONA;
  process.env.STYTCH_PERSONA = 'nope';
  assert.throws(() => personaCredentials(), /STYTCH_PERSONA/);
  process.env.STYTCH_PERSONA = 'support';
  assert.equal(personaCredentials().name, 'support');
  assert.equal(personaCredentials().emailKey, 'STYTCH_SUPPORT_EMAIL');
  if (previous == null) delete process.env.STYTCH_PERSONA;
  else process.env.STYTCH_PERSONA = previous;
});
