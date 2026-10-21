# Lexful QX Harness

OpenCode QA harness for a Lexful ticket. Preflight signs in, writes a context pack, and the server runs the coordinator. Playwright reports land in `runs/`.

## Run after clone

Docker Desktop (or another engine with Compose v2) is the only install.

```bash
git clone https://github.com/devanshvora-yorkie/lexful-qx-harness.git
cd lexful-qx-harness
cp .env.example .env
```

Fill these in `.env`. Leave the other values as they are unless the tenant changes.

- `STYTCH_ORGANIZATION_ID`
- `STYTCH_ADMIN_EMAIL`
- `STYTCH_ADMIN_PASSWORD`
- `LINEAR_API_KEY`
- `GITHUB_TOKEN`
- `OPENROUTER_API_KEY`

Then:

```bash
docker compose up --build -d
```

`make up` does the same check and start. The API is on [http://127.0.0.1:8787](http://127.0.0.1:8787).

With `LOCAL_MODE=true` the API does not require `HARNESS_DEPLOY_SECRET`. Set `LOCAL_MODE=false` and a secret before exposing the port.

## Start a ticket

From this directory, after the container is up:

```bash
docker compose exec harness npm run ticket -- LEX-2293
```

That starts the run and streams the log. Preflight signs in, the coordinator explores live UAT, the author writes specs, and Playwright runs them. `docker compose down` stops the server and keeps the run volume.

## Where a run is stored

Everything for one attempt lives in one folder:

```text
runs/<ticket>/<run-id>/
  FEATURE.md            what was observed on UAT
  specs/                spec files, POM, and the plan copy
  explore/              browser snapshots
  playwright/           results.json, html report, output.log
  planned-specs.json
  qa-result.json
  report.md
  preflight.json
  context-pack.json
  auth-state.json
  opencode/
```

Example: `runs/LEX-2293/LEX-2293-20261021T102159Z-1722/`. That directory is on your machine and mounted into the container, so a ticket run and a later spec run see the same files. Specs are not written into `tests/`. That directory is the older checked-in suite, not a place for run output.

`runs/` is gitignored. Do not commit `.env` or `auth-state.json`.

## Run specs again

The spec runner reuses the Stytch session and targets live UAT (`QA_ENV_URL`, default `https://e2e-test.uat.lexful.net`). Pass a spec file or a folder.

Watch it on this Mac. A Chrome window opens, slowed down enough to follow:

```bash
node scripts/specs.mjs --headed runs/LEX-2293/<run-id>/specs
node scripts/specs.mjs --headed runs/LEX-2293/<run-id>/specs/asset-related-items-read.spec.ts
```

Headless, inside the container:

```bash
docker compose exec harness node scripts/specs.mjs runs/LEX-2293/<run-id>/specs
```

`--headed` inside Docker uses a virtual display, so the window does not appear on the Mac. Run the command on the host when you want to see it. Results are written back into that run's `playwright/` folder when the path is already inside a run. A path that is not inside a run gets a new folder under `runs/manual/<run-id>/`.

## Checked-in e2e suites

These live in `e2e test cases/` and use the same runner. With the container up:

```bash
docker compose exec harness node scripts/specs.mjs "e2e test cases/search"
docker compose exec harness node scripts/specs.mjs "e2e test cases/asset crud"
docker compose exec harness node scripts/specs.mjs "e2e test cases/document editing"
```

Watch them on this Mac. A Chrome window opens:

```bash
node scripts/specs.mjs --headed "e2e test cases/search"
node scripts/specs.mjs --headed "e2e test cases/asset crud"
node scripts/specs.mjs --headed "e2e test cases/document editing"
```

`tests/` is the older suite. A new ticket does not write there, and these three suites do not read it. You can delete `tests/` when you no longer need those older specs.

The image installs Node, Playwright Chromium, the Python server, and OpenCode. On startup the OpenRouter key from `.env` is written into the container auth store. `.env` is mounted read-only and is not copied into the image.

## Local process

Use this when you want the server on the host instead of in Docker.

```bash
cp .env.example .env
npm install
npx playwright install chromium
python3 -m venv server/.venv
server/.venv/bin/pip install -r server/requirements.txt
curl -fsSL https://opencode.ai/v2/install | bash -s -- --version 2.0.30 --no-modify-path
opencode auth login
npm run serve
```

`npm run ticket -- LEX-1234` starts a run and follows its log. Do not commit `.env`, `auth-state.json`, or `runs/`.
