FROM node:26.12.1-bookworm

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    python3-pip \
    ca-certificates \
    curl \
    git \
  && rm -rf /var/lib/apt/lists/*

# The v1 installer refuses 2.x. Pin the same release that completed LEX-2293 locally.
RUN curl -fsSL https://opencode.ai/v2/install | bash -s -- --version 2.0.30 --no-modify-path
ENV PATH="/root/.opencode/bin:${PATH}"
ENV OPENCODE_DISABLE_AUTOUPDATE=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV CI=1
# `python -m app.cli` (one run, then exit) resolves the server package from here.
ENV PYTHONPATH=/opt/lexful-qa-opencode/server
# The working folder is writable by the agent user (sticky bit, see below). Python must never import
# from it: without this, `python -m` puts the current folder ahead of the standard library, and a
# module the agent planted there would run as root with every secret.
ENV PYTHONSAFEPATH=1

WORKDIR /opt/lexful-qa-opencode

COPY package.json package-lock.json ./
RUN npm ci
RUN npx playwright install --with-deps chromium

COPY server/requirements.txt server/requirements.txt
RUN python3 -m venv server/.venv \
  && server/.venv/bin/pip install --no-cache-dir -r server/requirements.txt

COPY . .
RUN chmod +x docker/entrypoint.sh \
  && mkdir -p runs

# Model-driven processes (OpenCode, playwright-cli, the specs it writes) run as `qa`, not root,
# so they cannot read the server's environment in /proc. The app folder is world-writable with
# the sticky bit: qa can create .playwright-cli/ and test-results/ there, but cannot rename or
# replace anything root put there (node_modules, scripts). The clones are root's; git must trust them.
# Root-owned, read-only placeholders in that writable folder, so the agent user cannot create them.
# Root reads each of them from this folder: .git (an empty, read-only directory: git skips it as not a
# repository, and the agent cannot turn it into one, so no git command run here reads agent config or hooks),
# .npmrc (npm settings such as script-shell for `npm run`), .env (scripts/harness-env.mjs and
# server/app/settings.py load it, so planted values could redirect where keys are sent).
RUN useradd --create-home --shell /bin/bash qa \
  && cp /root/.opencode/bin/opencode /usr/local/bin/opencode \
  && mkdir -p /home/qa/.local/share/opencode \
  && chown -R qa:qa /home/qa \
  && chmod 1777 /opt/lexful-qa-opencode \
  && git config --system --add safe.directory '*' \
  && mkdir /opt/lexful-qa-opencode/.git && chmod 555 /opt/lexful-qa-opencode/.git \
  && for f in .npmrc .env .yarnrc; do : > "/opt/lexful-qa-opencode/$f"; chmod 444 "/opt/lexful-qa-opencode/$f"; done

# xvfb-run is already pulled in by Playwright's browser deps. It refuses to start without xauth.
RUN apt-get update \
  && apt-get install -y --no-install-recommends xauth \
  && rm -rf /var/lib/apt/lists/*

EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/health')"

ENTRYPOINT ["docker/entrypoint.sh"]
# Default: the API server (docker compose up). A GitHub runner that starts one container per UAT deploy
# overrides the command with one run instead:  server/.venv/bin/python -m app.cli --sha <sha>
# See docs/setup.md.
CMD ["server/.venv/bin/python", "-P", "-m", "uvicorn", "app.main:app", "--app-dir", "server", "--host", "0.0.0.0", "--port", "8787"]
