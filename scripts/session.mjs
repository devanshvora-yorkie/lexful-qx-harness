import { ensureStytchSession, personaCredentials } from './harness-env.mjs';

const fresh = process.argv.includes('--fresh');

try {
  const creds = personaCredentials();
  const session = await ensureStytchSession({ force: fresh });
  if (session.onLogin) {
    console.error(`session rejected for persona ${creds.name}. The app landed on login`);
    process.exit(1);
  }
  const how = session.reused ? 'reused' : 'refreshed';
  console.log(`session ${how}  persona ${creds.name}  cookies ${session.cookieCount}  app HTTP ${session.pageStatus}`);
} catch (err) {
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
}
