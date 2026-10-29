import process from 'node:process';

const base = process.env.QA_SERVER_URL || `http://127.0.0.1:${process.env.QA_SERVER_PORT || '8787'}`;
const phase1 = process.argv.includes('--phase1');
const ticket = process.argv.find((arg) => /^LEX-\d+$/i.test(arg))?.toUpperCase();
const forceNew = process.argv.includes('--new');
const active = new Set(['accepted', 'queued', 'preflight', 'agent', 'execute', 'heal']);
const done = new Set(['completed', 'needs_revision', 'halted', 'failed']);

if (!phase1 && !ticket) {
  console.error('Usage: npm run ticket -- LEX-3500    Feature Specific TCs');
  console.error('       npm run e2e                  E2E User Journey TCs only');
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

async function e2eBeforeTicket() {
  try {
    const health = await readJson('/health');
    return health.phase1BeforeTicket !== false;
  } catch {
    return true;
  }
}

function appendLog(seen, text) {
  if (!text) {
    return seen;
  }
  if (text.startsWith(seen)) {
    const extra = text.slice(seen.length);
    if (extra) {
      process.stdout.write(extra.endsWith('\n') ? extra : `${extra}\n`);
    }
  } else {
    process.stdout.write(text.endsWith('\n') ? text : `${text}\n`);
    seen = '';
  }
  return text;
}

async function follow(id, label) {
  let seen = '';
  let idleTicks = 0;
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

    const logResponse = await fetch(`${base}/runs/${id}/log`, { headers: requestHeaders() });
    if (logResponse.ok) {
      seen = appendLog(seen, await logResponse.text());
      idleTicks = 0;
    } else if (Array.isArray(row.log) && row.log.length) {
      const tail = `${row.log.join('\n')}\n`;
      seen = appendLog(seen, tail);
      idleTicks = 0;
    } else {
      idleTicks += 1;
      if (idleTicks === 1 || idleTicks % 5 === 0) {
        console.log(`  … status ${row.status}  (log appears when the worker starts this run)`);
      }
    }

    if (done.has(row.status)) {
      console.log('');
      console.log(row.error ? `${row.status}  ${row.error}` : row.status);
      return row.status === 'completed' ? 0 : 1;
    }

    const delay = row.status === 'queued' || row.status === 'accepted' ? 500 : 1000;
    await new Promise((resolve) => setTimeout(resolve, delay));
  }
}

let runId;
let phase1RunId;

try {
  if (!phase1 && forceNew && ticket) {
    const listed = await readJson(`/runs?ticket=${ticket}`);
    const inFlight = (listed.runs || []).find((row) => active.has(row.status));
    if (inFlight) {
      console.error(`${ticket} is already running as ${inFlight.id} (${inFlight.status}).`);
      console.error(`One worker runs at a time. A new --new run would sit behind it (E2E included).`);
      console.error(`Follow the active run:  npm run ticket -- ${ticket}`);
      console.error(`Or wait until it finishes, then use --new again.`);
      process.exit(1);
    }
  }
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
    phase1RunId = started.phase1RunId || null;
    console.log(`${started.skipped ? 'following' : 'started'} ${runId} (${started.status})`);
    if (phase1RunId && phase1RunId !== runId) {
      console.log(`E2E queued first  ${phase1RunId}`);
    }
  }
} catch (error) {
  console.error(`Cannot reach ${base}. Start it with: npm run serve`);
  console.error(error.message);
  process.exit(1);
}

try {
  const health = await readJson('/health');
  const busy = health.runningRun;
  if (busy && busy.id !== runId && busy.id !== phase1RunId) {
    const name = busy.ticket ? `${busy.ticket}  ${busy.id}` : busy.id;
    console.log(`Worker busy: ${name} (${busy.status}). Queued runs stream when it is their turn.`);
  }
} catch {
  // health is optional for the hint
}

if (!phase1 && (await e2eBeforeTicket())) {
  let e2eId = phase1RunId;
  if (!e2eId) {
    const listed = await readJson('/runs');
    const e2e = (listed.runs || []).find((row) => row.kind === 'phase1' && active.has(row.status));
    e2eId = e2e?.id;
  }
  if (e2eId && e2eId !== runId) {
    await follow(e2eId, 'E2E User Journey TCs');
    console.log('');
    console.log('E2E User Journey TCs finished. Feature Specific TCs continues.');
  }
}

const code = await follow(
  runId,
  phase1 ? 'E2E User Journey TCs' : `Feature Specific TCs  ${ticket}`,
);
process.exit(code);
