#!/bin/sh
set -eu

cd /opt/lexful-qa-opencode
mkdir -p runs /root/.local/share/opencode

persona="${STYTCH_PERSONA:-admin}"
case "$persona" in
  admin)
    email_var=STYTCH_ADMIN_EMAIL
    pass_var=STYTCH_ADMIN_PASSWORD
    ;;
  support)
    email_var=STYTCH_SUPPORT_EMAIL
    pass_var=STYTCH_SUPPORT_PASSWORD
    ;;
  viewer)
    email_var=STYTCH_VIEWER_EMAIL
    pass_var=STYTCH_VIEWER_PASSWORD
    ;;
  *)
    echo "harness: STYTCH_PERSONA must be admin, support, or viewer" >&2
    exit 1
    ;;
esac

missing=""
for name in \
  STYTCH_ORGANIZATION_ID \
  "$email_var" \
  "$pass_var" \
  LINEAR_API_KEY \
  GITHUB_TOKEN \
  BEDROCK_API_KEY
do
  eval "value=\${$name-}"
  if [ -z "$value" ]; then
    missing="$missing $name"
  fi
done
if [ -n "$missing" ]; then
  echo "harness: fill these in .env before starting a ticket:$missing" >&2
fi

# Login happens when the container starts, not during image build.
# The image has no .env, and a cookie baked into a layer would be stale.
echo "harness: refreshing Stytch session for persona ${persona}"
node scripts/session.mjs --fresh

# OpenCode's Bedrock provider reads AWS_BEARER_TOKEN_BEDROCK. BEDROCK_API_KEY is the name in .env.
if [ -z "${AWS_BEARER_TOKEN_BEDROCK:-}" ] && [ -n "${BEDROCK_API_KEY:-}" ]; then
  export AWS_BEARER_TOKEN_BEDROCK="$BEDROCK_API_KEY"
fi
export AWS_REGION="${AWS_REGION:-us-east-1}"

exec "$@"
