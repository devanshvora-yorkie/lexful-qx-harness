#!/usr/bin/env bash
# Set up the Lexful QA harness on this machine: check the tools, make sure .env has its keys,
# build the image, start the API container and, with --runner, register this machine as the
# GitHub Actions runner that runs the harness after each UAT deploy.
#
#   ./build.sh                 check, build the image, start the container
#   ./build.sh --check         check only. Changes nothing (also reads no secret values)
#   ./build.sh --update        git pull --ff-only first, then build and start
#   ./build.sh --runner        also register this machine as the qa-harness runner (needs gh, admin on the repo)
#   ./build.sh --help
#
# Values in .env are never printed. Only the names of missing keys are shown.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$ROOT/.env"
CHECK_ONLY=0
UPDATE=0
RUNNER=0
CUSTOM_ENV=0
REPO="${QA_REPO:-Lexful-ai/qa-harness}"

# Keys the server and the container cannot start without (see .env.example and docs/setup.md).
REQUIRED_KEYS="STYTCH_ORGANIZATION_ID STYTCH_ADMIN_EMAIL STYTCH_ADMIN_PASSWORD LINEAR_API_KEY GITHUB_TOKEN BEDROCK_API_KEY"

say() { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
die() { printf 'build.sh: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK_ONLY=1 ;;
    --update) UPDATE=1 ;;
    --runner) RUNNER=1 ;;
    --env-file)
      [ $# -ge 2 ] || die "--env-file needs a path"
      ENV_FILE="$2"
      CUSTOM_ENV=1
      shift
      ;;
    -h|--help)
      sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) die "unknown option: $1 (try --help)" ;;
  esac
  shift
done

if [ "$CUSTOM_ENV" = 1 ] && [ "$CHECK_ONLY" = 0 ]; then
  die "--env-file only works with --check. docker-compose.yml reads .env from this folder."
fi

# ---------------------------------------------------------------------------------------------
step "Tools"
command -v docker >/dev/null 2>&1 || die "Docker is not installed. Install Docker Desktop (macOS) or Docker Engine (Linux), then run this again."
docker info >/dev/null 2>&1 || die "Docker is installed but not running. Start it, then run this again."
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is missing (run: docker compose version)."
command -v git >/dev/null 2>&1 || die "git is missing."
command -v curl >/dev/null 2>&1 || die "curl is missing."
say "docker, docker compose v2, git and curl: ok"

# ---------------------------------------------------------------------------------------------
step "Settings in $ENV_FILE"
if [ ! -f "$ENV_FILE" ]; then
  [ "$CUSTOM_ENV" = 0 ] || die "$ENV_FILE does not exist"
  cp "$ROOT/.env.example" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  say "Created $ENV_FILE from .env.example. Fill in the keys listed below, then run ./build.sh again."
fi

missing=""
for key in $REQUIRED_KEYS; do
  if ! grep -Eq "^${key}=[^[:space:]]" "$ENV_FILE"; then
    missing="$missing $key"
  fi
done
if [ -n "$missing" ]; then
  say "Still empty in $ENV_FILE:$missing"
  die "fill those in, then run ./build.sh again."
fi
say "Required keys are set (values not shown)."

if [ "$UPDATE" = 1 ]; then
  step "Update the harness"
  git -C "$ROOT" pull --ff-only
fi

if [ "$CHECK_ONLY" = 1 ]; then
  say ""
  say "Checks passed. Nothing was built or started."
  exit 0
fi

# ---------------------------------------------------------------------------------------------
step "Build the image"
docker compose --project-directory "$ROOT" build harness

step "Start the API container"
docker compose --project-directory "$ROOT" up -d harness

step "Wait for the API"
healthy=0
for _ in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:8787/health" >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 3
done
[ "$healthy" = 1 ] || die "the API did not answer on 127.0.0.1:8787. Read: docker compose --project-directory \"$ROOT\" logs harness"
say "API is up at http://127.0.0.1:8787"

# ---------------------------------------------------------------------------------------------
register_runner() {
  step "GitHub Actions runner for $REPO"
  command -v gh >/dev/null 2>&1 || die "the GitHub CLI (gh) is needed to register the runner: install gh, then run gh auth login."
  gh auth status >/dev/null 2>&1 || die "run gh auth login first. The account needs admin access to $REPO."

  case "$(uname -s)-$(uname -m)" in
    Darwin-arm64) platform=osx-arm64 ;;
    Darwin-x86_64) platform=osx-x64 ;;
    Linux-x86_64) platform=linux-x64 ;;
    Linux-aarch64|Linux-arm64) platform=linux-arm64 ;;
    *) die "unsupported platform: $(uname -s) $(uname -m)" ;;
  esac

  runner_dir="${QA_RUNNER_DIR:-$HOME/actions-runner-qa-harness}"
  mkdir -p "$runner_dir"
  cd "$runner_dir"

  if [ ! -x ./config.sh ]; then
    version="$(gh api repos/actions/runner/releases/latest --jq .tag_name | sed 's/^v//')"
    say "Downloading the GitHub runner $version for $platform"
    curl -fsSL -o runner.tar.gz "https://github.com/actions/runner/releases/download/v${version}/actions-runner-${platform}-${version}.tar.gz"
    tar xzf runner.tar.gz
    rm -f runner.tar.gz
  fi

  if [ ! -f .runner ]; then
    token="$(gh api -X POST "repos/$REPO/actions/runners/registration-token" --jq .token)"
    ./config.sh --unattended --replace \
      --url "https://github.com/$REPO" \
      --token "$token" \
      --name "qa-$(hostname -s)" \
      --labels qa-harness \
      --work _work
  else
    say "This folder is already registered. Keeping the registration."
  fi

  # The job reads where the harness lives from the runner's .env, and finds docker through .path.
  printf 'QA_HARNESS_DIR=%s\n' "$ROOT" > .env
  printf '%s\n' "$PATH" > .path

  if [ "$(uname -s)" = Linux ]; then
    sudo ./svc.sh install >/dev/null 2>&1 || true
    sudo ./svc.sh start
  else
    ./svc.sh install >/dev/null 2>&1 || true
    ./svc.sh start
  fi
  say ""
  say "Runner registered as qa-$(hostname -s) with label qa-harness. Check it under Settings > Actions > Runners in $REPO."
}

if [ "$RUNNER" = 1 ]; then
  register_runner
fi

step "Done"
say "Container: docker compose --project-directory \"$ROOT\" ps"
say "Run a PR:  docker compose exec harness npm run ticket -- --pr <number>"
say "Logs:      docker compose --project-directory \"$ROOT\" logs -f harness"
