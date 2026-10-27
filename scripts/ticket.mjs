import process from 'node:process';

const base = process.env.QA_SERVER_URL || `http://127.0.0.1:${process.env.QA_SERVER_PORT || '8787'}`;
const phase1 = process.argv.includes('--phase1');
const ticket = process.argv.find((arg) => /^LEX-\d+$/i.test(arg))?.toUpperCase();
const forceNew = process.argv.includes('--new');
const active = new Set(['accepted', 'queued', 'preflight', 'agent', 'execute', 'heal']);
const done = new Set(['completed', 'needs_revision', 'halted', 'failed']);

if (!phase1 && !ticket) {
  console.error('Usage: npm run ticket -- LEX-3500    Feature Specific TCs');
  console.error('       npm run e2e                  E2E User Journey TCs');
  process.exit(1);
}

function requestHeaders() {
  const secret = process.env.HARNESS_DEPLOY_SECRET;
  return secret ? { 'x-harness-deploy-secret': secret } : {};
}

async function readJson(path, options = {}) {
  const response = await fetch(`${base}${path}`, {
    ...options,
    headers: { ...requestHeaders(), ...(options.headers || {}) },
  });
  const text = await response.text();
  let body = {};
  try {
    body = text ? JSON.parse(text) : {};
  } catch {
    body = { detail: text };
  }
  if (!response.ok) {
    throw new Error(body.detail || `HTTP ${response.status}`);
  }
  return body;
}

let runId;
try {
  if (!forceNew) {
    const listed = await readJson(phase1 ? '/runs' : `/runs?ticket=${ticket}`);
    const current = (listed.runs || []).find((row) => (
      active.has(row.status) && (phase1 ? row.kind === 'phase1' : true)
    ));
    if (current) {
      runId = current.id;
      console.log(`following ${runId} (${current.status})`);
    }
  }
  if (!runId) {
    const started = await readJson(phase1 ? '/run/phase1' : `/run/${ticket}`, { method: 'POST' });
    runId = started.runId;
    console.log(`${started.skipped ? 'following' : 'started'} ${runId} (${started.status})`);
  }
} catch (error) {
  console.error(`Cannot reach ${base}. Start it with: npm run serve`);
  console.error(error.message);
  process.exit(1);
}

async function follow(id, label) {
  let seen = '';
  console.log('');
  console.log(`${label}  ${id}`);
  console.log('');
  for (;;) {
    let row;
    try {
      row = await readJson(`/runs/${id}`);
    } catch (error) {
      console.error(error.message);
      process.exit(1);
    }
    const log = await fetch(`${base}/runs/${id}/log`, { headers: requestHeaders() });
    if (log.ok) {
      const text = await log.text();
      if (text.startsWith(seen)) {
        const extra = text.slice(seen.length);
        if (extra) process.stdout.write(extra.endsWith('\n') ? extra : `${extra}\n`);
      } else if (text) {
        process.stdout.write(text.endsWith('\n') ? text : `${text}\n`);
      }
      seen = text;
    }
    if (done.has(row.status)) {
      console.log('');
      console.log(row.error ? `${row.status}  ${row.error}` : row.status);
      return row.status === 'completed' ? 0 : 1;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}

if (!phase1) {
  const listed = await readJson('/runs');
  const e2e = (listed.runs || []).find((row) => row.kind === 'phase1' && active.has(row.status));
  if (e2e) {
    await follow(e2e.id, 'E2E User Journey TCs');
    console.log('');
    console.log('E2E User Journey TCs finished. Feature Specific TCs continues.');
  }
}

const code = await follow(
  runId,
  phase1 ? 'E2E User Journey TCs' : `Feature Specific TCs  ${ticket}`,
);
process.exit(code);
