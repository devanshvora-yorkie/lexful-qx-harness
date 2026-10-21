"""Process settings. `.env` in the repo root is loaded without printing values."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN_MODEL_DEFAULT = "openrouter/anthropic/claude-sonnet-5.5"
SUB_MODEL_DEFAULT = "openrouter/anthropic/claude-haiku-5.5"
SECRET_ENV = (
    "STYTCH_ADMIN_PASSWORD",
    "STYTCH_SUPPORT_PASSWORD",
    "STYTCH_VIEWER_PASSWORD",
    "LINEAR_API_KEY",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "HARNESS_DEPLOY_SECRET",
)


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    root: Path
    runs: Path
    port: int
    local_mode: bool
    deploy_secret: str
    main_model: str
    sub_model: str
    agent_timeout_seconds: int
    heal_attempts: int
    qa_url: str


def get_settings() -> Settings:
    _load_dotenv(ROOT / ".env")
    os.environ.setdefault("OPENCODE_MAIN_MODEL", MAIN_MODEL_DEFAULT)
    os.environ.setdefault("OPENCODE_DISABLE_AUTOUPDATE", "1")
    secret = os.getenv("HARNESS_DEPLOY_SECRET", "").strip()
    runs = Path(os.getenv("QA_RUNS_DIR", str(ROOT / "runs"))).expanduser()
    return Settings(
        root=ROOT,
        runs=runs,
        port=int(os.getenv("QA_SERVER_PORT", "8787")),
        local_mode=_flag("LOCAL_MODE", default=secret == ""),
        deploy_secret=secret,
        main_model=os.getenv("OPENCODE_MAIN_MODEL", MAIN_MODEL_DEFAULT).strip(),
        sub_model=os.getenv("OPENCODE_SUB_MODEL", SUB_MODEL_DEFAULT).strip(),
        agent_timeout_seconds=int(os.getenv("QA_AGENT_TIMEOUT_SECONDS", "2700")),
        heal_attempts=int(os.getenv("QA_HEAL_ATTEMPTS", "3")),
        qa_url=os.getenv("QA_ENV_URL", os.getenv("LEXFUL_APP_URL", "https://e2e-test.uat.lexful.net")).strip(),
    )
