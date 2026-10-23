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

# xvfb-run is already pulled in by Playwright's browser deps. It refuses to start without xauth.
RUN apt-get update \
  && apt-get install -y --no-install-recommends xauth \
  && rm -rf /var/lib/apt/lists/*

EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/health')"

ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["server/.venv/bin/python", "-m", "uvicorn", "app.main:app", "--app-dir", "server", "--host", "0.0.0.0", "--port", "8787"]
