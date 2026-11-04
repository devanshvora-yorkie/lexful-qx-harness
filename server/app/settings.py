"""Process settings. `.env` in the repo root is loaded without printing values."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN_MODEL_DEFAULT = "amazon-bedrock/us.anthropic.claude-haiku-5-5"
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
    agent_timeout_seconds: int
    playwright_timeout_seconds: int
    heal_attempts: int
    qa_url: str
    e2e_with_ticket: bool  # QA_PHASE1_ON_START: each ticket run starts with the E2E User Journey stage, stored in its e2e/
    run_ux_audit: bool = True
    heal_fresh_session: bool = True  # QA_HEAL_FRESH_SESSION: heals read the run files, not the Explore conversation
    pw_workers: int = 3  # QA_PW_WORKERS: Playwright workers, the browsers that hit UAT at once
    pw_fully_parallel: bool = True  # QA_PW_FULLY_PARALLEL: each test goes to the next free worker; false = one file per worker
    max_parallel_runs: int = 1  # QA_MAX_PARALLEL_RUNS: runs the server executes at the same time
    agent_retries: int = 1  # QA_AGENT_RETRIES: resumes of an OpenCode session after a dropped connection
    agent_user: str = "qa"  # QA_AGENT_USER: OpenCode and Playwright run as this user. Empty keeps the server user
    verify_findings: bool = True  # QA_VERIFY_FINDINGS: a fresh session reproduces suspected bugs before filing
    ux_parallel: bool = True  # QA_UX_PARALLEL: the UX audit runs while Playwright and heal run
    session_check_minutes: int = 20  # QA_SESSION_CHECK_MINUTES: how often a busy server renews Stytch sessions. 0 = off


def _int(name: str, default: int, low: int = 0) -> int:
    try:
        return max(low, int(os.getenv(name, str(default)).strip() or default))
    except ValueError:
        return default


def get_settings() -> Settings:
    _load_dotenv(ROOT / ".env")
    os.environ.setdefault("OPENCODE_MAIN_MODEL", MAIN_MODEL_DEFAULT)
    os.environ.setdefault("OPENCODE_DISABLE_AUTOUPDATE", "1")
    secret = os.getenv("HARNESS_DEPLOY_SECRET", "").strip()
    runs = Path(os.getenv("QA_RUNS_DIR", str(ROOT / "runs"))).expanduser()
    return Settings(
        root=ROOT,
        runs=runs,
        port=_int("QA_SERVER_PORT", 8787, low=1),
        local_mode=_flag("LOCAL_MODE", default=secret == ""),
        deploy_secret=secret,
        main_model=os.getenv("OPENCODE_MAIN_MODEL", MAIN_MODEL_DEFAULT).strip(),
        agent_timeout_seconds=_int("QA_AGENT_TIMEOUT_SECONDS", 2700, low=60),
        playwright_timeout_seconds=_int("QA_PLAYWRIGHT_TIMEOUT_SECONDS", 2700, low=60),
        heal_attempts=_int("QA_HEAL_ATTEMPTS", 3),
        qa_url=os.getenv("QA_ENV_URL", os.getenv("LEXFUL_APP_URL", "https://e2e-test.uat.lexful.net")).strip(),
        e2e_with_ticket=_flag("QA_PHASE1_ON_START", default=True),
        run_ux_audit=_flag("QA_RUN_UX_AUDIT", default=True),
        heal_fresh_session=_flag("QA_HEAL_FRESH_SESSION", default=True),
        pw_workers=_int("QA_PW_WORKERS", 3, low=1),
        pw_fully_parallel=_flag("QA_PW_FULLY_PARALLEL", default=True),
        max_parallel_runs=_int("QA_MAX_PARALLEL_RUNS", 1, low=1),
        agent_retries=_int("QA_AGENT_RETRIES", 1),
        agent_user=os.getenv("QA_AGENT_USER", "qa").strip(),
        verify_findings=_flag("QA_VERIFY_FINDINGS", default=True),
        ux_parallel=_flag("QA_UX_PARALLEL", default=True),
        session_check_minutes=_int("QA_SESSION_CHECK_MINUTES", 20),
    )

