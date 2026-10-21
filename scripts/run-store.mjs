import { closeSync, existsSync, mkdirSync, openSync, readFileSync, statSync, unlinkSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { ROOT } from './harness-env.mjs';

export const RUNS = path.join(ROOT, 'runs');

export function newRunId(label) {
  const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z');
  const suffix = Math.random().toString(16).slice(2, 6);
  return `${label || 'manual'}-${stamp}-${suffix}`;
}

function withLock(fn) {
  mkdirSync(RUNS, { recursive: true });
  const lock = path.join(RUNS, 'index.lock');
  for (let attempt = 0; attempt < 50; attempt++) {
    try {
      const fd = openSync(lock, 'wx');
      try {
        return fn();
      } finally {
        closeSync(fd);
        try { unlinkSync(lock); } catch { /* already gone */ }
      }
    } catch (err) {
      if (err.code !== 'EEXIST') throw err;
      try {
        if (Date.now() - statSync(lock).mtimeMs > 15000) unlinkSync(lock);
      } catch { /* another writer removed it */ }
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 40);
    }
  }
  throw new Error('runs/index.json stayed locked');
}

export function updateIndex(entry) {
  return withLock(() => {
    const file = path.join(RUNS, 'index.json');
    const data = existsSync(file) ? JSON.parse(readFileSync(file, 'utf8')) : { runs: [] };
    const runs = Array.isArray(data.runs) ? data.runs : [];
    const index = runs.findIndex((row) => row.id === entry.id);
    if (index >= 0) runs[index] = { ...runs[index], ...entry };
    else runs.unshift(entry);
    writeFileSync(file, `${JSON.stringify({ runs }, null, 2)}\n`);
    return entry;
  });
}

/** Manual preflight owns this folder. The server passes --out and does not call this. */
export function createCliRun(label) {
  const id = newRunId(label);
  const dir = path.join(RUNS, id);
  mkdirSync(dir, { recursive: true });
  const now = new Date().toISOString();
  const ticket = /^LEX-\d+$/i.test(String(label || '')) ? String(label).toUpperCase() : null;
  const pr = /^pr-\d+$/.test(String(label || '')) ? Number(String(label).slice(3)) : null;
  updateIndex({
    id,
    ticket,
    pr,
    sha: null,
    status: 'preflight',
    createdAt: now,
    updatedAt: now,
  });
  return { id, dir };
}
