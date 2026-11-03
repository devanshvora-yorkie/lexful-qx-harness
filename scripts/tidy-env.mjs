// Rewrite .env in the order and sections of .env.example, keeping every value.
//
//   node scripts/tidy-env.mjs [path/to/.env]
//
// The old file is kept as .env.bak. Keys that .env.example does not list are dropped, and their
// names are printed so you can see what went. Values are never printed.
import { chmodSync, copyFileSync, existsSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const template = path.join(ROOT, '.env.example');
const target = path.resolve(process.argv[2] || path.join(ROOT, '.env'));

if (!existsSync(target)) {
  console.error(`${target} does not exist. Copy .env.example to .env first.`);
  process.exit(1);
}

// A template key line: KEY=value with no spaces, or the same line commented out (`# QA_RUNS_DIR=`).
// A comment that happens to mention KEY=... in its text is not a key line.
const KEY = /^(#\s*)?([A-Z][A-Z0-9_]*)=(\S*)$/;

function parseValues(text) {
  const values = new Map();
  for (const line of text.split(/\r?\n/)) {
    const match = line.match(/^([A-Z][A-Z0-9_]*)=(.*)$/);
    if (match) values.set(match[1], match[2]);
  }
  return values;
}

const current = parseValues(readFileSync(target, 'utf8'));
const listed = new Set();
const out = [];

for (const line of readFileSync(template, 'utf8').split(/\r?\n/)) {
  const match = line.match(KEY);
  if (!match) {
    out.push(line);
    continue;
  }
  const [, commented, key] = match;
  listed.add(key);
  if (current.has(key)) {
    out.push(`${key}=${current.get(key)}`);
  } else {
    // Not in .env yet: take the template's line, so a default such as QA_PW_FULLY_PARALLEL=true is kept.
    out.push(line);
  }
}

const dropped = [...current.keys()].filter((key) => !listed.has(key));

copyFileSync(target, `${target}.bak`);
chmodSync(`${target}.bak`, 0o600);
writeFileSync(target, `${out.join('\n').replace(/\n+$/, '')}\n`, { mode: 0o600 });
chmodSync(target, 0o600);

console.log(`Rewrote ${target}. The previous file is ${target}.bak.`);
console.log(`Kept ${current.size - dropped.length} key(s) with their values.`);
if (dropped.length) {
  console.log(`Dropped ${dropped.length} key(s) that .env.example does not list:`);
  for (const key of dropped) console.log(`  ${key}`);
}
