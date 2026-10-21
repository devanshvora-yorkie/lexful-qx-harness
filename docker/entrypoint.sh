#!/bin/sh
set -eu

cd /opt/lexful-qa-opencode
mkdir -p runs /root/.local/share/opencode

missing=""
for name in \
  STYTCH_ORGANIZATION_ID \
  STYTCH_ADMIN_EMAIL \
  STYTCH_ADMIN_PASSWORD \
  LINEAR_API_KEY \
  GITHUB_TOKEN \
  OPENROUTER_API_KEY
do
  eval "value=\${$name-}"
  if [ -z "$value" ]; then
    missing="$missing $name"
  fi
done
if [ -n "$missing" ]; then
  echo "harness: fill these in .env before starting a ticket:$missing" >&2
fi

if [ -n "${OPENROUTER_API_KEY:-}" ]; then
  python3 - <<'PY'
import json
import os

path = "/root/.local/share/opencode/auth.json"
key = os.environ["OPENROUTER_API_KEY"].strip()
if key:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"openrouter": {"type": "api", "key": key}}, handle)
    os.chmod(path, 0o600)
PY
fi

exec "$@"
