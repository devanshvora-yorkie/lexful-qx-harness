import process from 'node:process';

const base = process.env.QA_SERVER_URL || `http://127.0.0.1:${process.env.QA_SERVER_PORT || '8787'}`;

function requestHeaders() {
  const secret = process.env.HARNESS_DEPLOY_SECRET;
  return secret ? { 'x-harness-deploy-secret': secret } : {};
}

const response = await fetch(`${base}/runs/cancel-all`, {
  method: 'POST',
  headers: requestHeaders(),
});

const text = await response.text();
let body = {};
try {
  body = text ? JSON.parse(text) : {};
} catch {
  body = { detail: text };
}

if (!response.ok) {
  console.error(body.detail || `HTTP ${response.status}`);
  process.exit(1);
}

const ids = body.cancelled || [];
if (!ids.length) {
  console.log('No active or queued runs.');
} else {
  console.log(`Cancelled ${ids.length} run(s):`);
  for (const id of ids) {
    console.log(`  - ${id}`);
  }
}
if (body.drained) {
  console.log(`Drained ${body.drained} item(s) from the worker queue.`);
}
console.log('If a run was mid-flight (agent/playwright), restart the harness to stop it:  docker compose restart harness');
