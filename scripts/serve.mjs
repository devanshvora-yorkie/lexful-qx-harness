import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { ensureToolchain } from './toolchain.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const python = path.join(root, 'server', '.venv', 'bin', 'python');

const checks = ensureToolchain();
const failed = checks.filter((row) => row.status === 'fail');
for (const row of checks) console.log(`${row.status.toUpperCase()}  ${row.name}: ${row.detail}`);
if (failed.length) process.exit(1);

const port = process.env.QA_SERVER_PORT || '8787';
const child = spawn(
  python,
  ['-m', 'uvicorn', 'app.main:app', '--app-dir', 'server', '--host', '0.0.0.0', '--port', port],
  { cwd: root, stdio: 'inherit' },
);
child.on('exit', (code) => process.exit(code ?? 1));
