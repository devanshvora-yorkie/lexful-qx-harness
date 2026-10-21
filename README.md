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

```bash
curl http://127.0.0.1:8787/health
curl -X POST http://127.0.0.1:8787/run/LEX-1234
curl http://127.0.0.1:8787/runs
```

With `LOCAL_MODE=true` the API does not require `HARNESS_DEPLOY_SECRET`. Set `LOCAL_MODE=false` and a secret before exposing the port.

Run folders stay in the `harness-runs` volume. `docker compose logs -f harness` follows the server. `docker compose down` stops it and keeps that volume.

The image installs Node, Playwright Chromium, the Python server, and OpenCode. On startup the OpenRouter key from `.env` is written into the container auth store. `.env` is mounted read-only and is not copied into the image.

## Local process

Use this when you want the server on the host instead of in Docker.

```bash
cp .env.example .env
npm install
npx playwright install chromium
python3 -m venv server/.venv
server/.venv/bin/pip install -r server/requirements.txt
curl -fsSL https://opencode.ai/install | bash
opencode auth login
npm run serve
```

`npm run ticket -- LEX-1234` starts a run and follows its log. Do not commit `.env`, `auth-state.json`, or `runs/`.
