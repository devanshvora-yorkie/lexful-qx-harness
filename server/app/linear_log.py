"""Log a sealed run to Linear: one tracking ticket, one comment per run, one Bug ticket per bug.

This is plain server code, not an agent session. The agent never gets Linear write access, and
filing needs no model: the bug text is already written (`bugs.md`), the numbers are in
`summary.json`, and the links are known.

What it creates, all in the WRITE team and project (`LINEAR_WRITE_TEAM_ID`, `LINEAR_WRITE_PROJECT_ID`):

- **Tracking ticket**, one per source ticket (`QA: LEX-2293`), reused by every run of that ticket.
  A run started on its own (the E2E User Journey TCs) uses one standing ticket for them.
- **A comment on it**, one per run: run id, attempt number, verdict, counts, links.
- **Bug tickets**, sub-issues of the tracking ticket, labelled `Bug: Functionality` and `automated`.
  Feature bugs and E2E regression bugs are separate: E2E titles start with `[E2E]`.
- **The UX report**, linked by `QA_REPORT_BASE_URL` when the harness hosts it, else uploaded to Linear.

Who counts what:

- Issue numbers (`YOR-1102`) are Linear's. It assigns the next one; the harness never does.
- The run id and the attempt number ("run 3 of LEX-2293") are the harness's, from its own index.
- A bug is recognised across runs by a fingerprint written into its description. A bug that is still
  open in Linear gets a "seen again" comment with an occurrence count instead of a second ticket.

Nothing here may fail a run. `file_run` is called from the seal step and its errors are logged.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from app.settings import get_settings

BUG_LABELS = ("Bug: Functionality", "automated")
TRACKING_LABELS = ("automated",)
PRIORITY = {"P0": 1, "P1": 2, "P2": 3, "P3": 4}  # Linear: 1 urgent .. 4 low
CLOSED_STATES = {"completed", "canceled"}
FINISHED = {"completed", "needs_revision"}
SEEN_MARK = "<!-- qx-seen -->"
TITLE_MAX = 140
LINEAR_URL_DEFAULT = "https://api.linear.app/graphql"
SOURCE_URL = "https://linear.app/lexful/issue/"


class LinearError(RuntimeError):
    pass


# ── settings ─────────────────────────────────────────────────────────────────────────────────


def config() -> dict[str, str]:
    import os

    get_settings()  # loads .env into the environment
    pick = os.environ.get
    return {
        "enabled": (pick("QA_LINEAR_LOG", "") or "").strip().lower(),
        "key": (pick("LINEAR_API_KEY", "") or "").strip(),
        "url": (pick("LINEAR_API_URL", "") or LINEAR_URL_DEFAULT).strip(),
        "team": (pick("LINEAR_WRITE_TEAM_ID", "") or pick("LINEAR_TEAM_ID", "") or "").strip(),
        "read_team": (pick("LINEAR_READ_TEAM_ID", "") or "").strip(),
        "project": (pick("LINEAR_WRITE_PROJECT_ID", "") or pick("LINEAR_PROJECT_ID", "") or "").strip(),
        "report_base": (pick("QA_REPORT_BASE_URL", "") or "").strip().rstrip("/"),
    }


def is_enabled(cfg: dict[str, str] | None = None) -> bool:
    cfg = cfg or config()
    return cfg["enabled"] in {"1", "true", "yes", "on"}


def check_config(cfg: dict[str, str]) -> None:
    if not (cfg["key"] and cfg["team"] and cfg["project"]):
        raise LinearError("LINEAR_API_KEY and the write team and project ids must be set")
    if cfg["team"] == cfg["read_team"]:
        raise LinearError("the write team is the read team; refusing to create tickets there")


# ── Linear API ───────────────────────────────────────────────────────────────────────────────


def gql(cfg: dict[str, str], query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(
        cfg["url"],
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": cfg["key"], "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise LinearError(f"Linear HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise LinearError(f"Linear unreachable: {exc}") from exc
    if body.get("errors"):
        raise LinearError("; ".join(str(e.get("message")) for e in body["errors"])[:300])
    return body.get("data") or {}


def upload(cfg: dict[str, str], file: Path) -> str:
    """Store a file in Linear and return its URL. Only signed-in members of the workspace can open it."""
    data = file.read_bytes()
    kind = {".png": "image/png", ".html": "text/html"}.get(file.suffix.lower(), "application/octet-stream")
    slot = gql(
        cfg,
        "mutation($t:String!,$f:String!,$s:Int!){fileUpload(contentType:$t,filename:$f,size:$s){uploadFile{uploadUrl assetUrl headers{key value}}}}",
        {"t": kind, "f": file.name, "s": len(data)},
    ).get("fileUpload", {}).get("uploadFile")
    if not slot:
        raise LinearError(f"no upload slot for {file.name}")
    headers = {"Content-Type": kind, "Cache-Control": "public, max-age=31536000"}
    headers.update({h["key"]: h["value"] for h in slot.get("headers") or []})
    put = urllib.request.Request(slot["uploadUrl"], data=data, headers=headers, method="PUT")
    try:
        urllib.request.urlopen(put, timeout=120).close()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise LinearError(f"upload of {file.name} failed: {exc}") from exc
    return str(slot["assetUrl"])


# ── what a run contains ──────────────────────────────────────────────────────────────────────


def _json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def bug_sections(markdown: str) -> list[tuple[str, str]]:
    """bugs.md is one `## title` block per bug, written to be pasted into a ticket."""
    out = []
    for block in re.split(r"^## ", markdown, flags=re.M):
        if block.strip():
            title, _, body = block.partition("\n")
            out.append((title.strip(), body.strip()))
    return out


def collect_bugs(folder: Path, scope: str) -> list[dict[str, Any]]:
    """The bugs of one stage folder, with ticket-ready text. `scope` is `feature` or `e2e`."""
    bugs = _json(folder / "bugs.json").get("bugs") or []
    sections = []
    try:
        sections = bug_sections((folder / "bugs.md").read_text(encoding="utf-8"))
    except OSError:
        pass
    found = []
    for index, bug in enumerate(b for b in bugs if isinstance(b, dict)):
        title, body = sections[index] if index < len(sections) else (str(bug.get("title") or "Untitled bug"), str(bug.get("description") or ""))
        found.append({
            "scope": scope,
            "title": title,
            "body": body,
            "severity": str(bug.get("severity") or "Medium"),
            "priority": str(bug.get("priority") or "P2"),
            "folder": folder,
        })
    return found


def fingerprint(scope: str, source: str, title: str) -> str:
    """Same bug, same fingerprint, in any run. Feature bugs are per source ticket; E2E bugs are global."""
    text = re.sub(r"\s+", " ", title.lower()).strip()
    return hashlib.sha1(f"{scope}|{source if scope == 'feature' else ''}|{text}".encode()).hexdigest()[:12]


def ticket_title(bug: dict[str, Any]) -> str:
    title = ("[E2E] " if bug["scope"] == "e2e" else "") + bug["title"]
    return title if len(title) <= TITLE_MAX else title[: TITLE_MAX - 1].rstrip() + "…"


# ── tracking ticket and bugs ─────────────────────────────────────────────────────────────────


def _labels(cfg: dict[str, str]) -> dict[str, str]:
    team = gql(cfg, "query($id:String!){team(id:$id){key labels{nodes{id name}}}}", {"id": cfg["team"]}).get("team") or {}
    if team.get("key") == "LEX":
        raise LinearError("the write team resolved to LEX; refusing")
    return {n["name"]: n["id"] for n in team.get("labels", {}).get("nodes", [])}


def _find(cfg: dict[str, str], marker: str) -> dict[str, Any] | None:
    data = gql(
        cfg,
        """query($p:ID!,$m:String!){issues(first:1,filter:{project:{id:{eq:$p}},description:{contains:$m}}){
             nodes{id identifier url state{type} comments(first:100){nodes{body}}}}}""",
        {"p": cfg["project"], "m": marker},
    )
    nodes = (data.get("issues") or {}).get("nodes") or []
    return nodes[0] if nodes else None


def _create(cfg: dict[str, str], **fields: Any) -> dict[str, Any]:
    fields.update(teamId=cfg["team"], projectId=cfg["project"])
    fields = {k: v for k, v in fields.items() if v not in (None, [], "")}
    data = gql(cfg, "mutation($i:IssueCreateInput!){issueCreate(input:$i){issue{id identifier url}}}", {"i": fields})
    issue = (data.get("issueCreate") or {}).get("issue")
    if not issue:
        raise LinearError("Linear did not create the issue")
    return issue


def _comment(cfg: dict[str, str], issue_id: str, body: str) -> str:
    data = gql(cfg, "mutation($i:CommentCreateInput!){commentCreate(input:$i){comment{url}}}", {"i": {"issueId": issue_id, "body": body}})
    return str(((data.get("commentCreate") or {}).get("comment") or {}).get("url") or "")


def tracking_ticket(cfg: dict[str, str], labels: dict[str, str], source: str) -> tuple[dict[str, Any], bool]:
    marker = f"qx-ticket:{source}"
    found = _find(cfg, marker)
    if found:
        return found, False
    if source == "e2e-journeys":
        title, intro = "QA: E2E User Journey TCs (UAT regression)", "Standing ticket for the E2E User Journey regression runs on UAT."
    else:
        title, intro = f"QA: {source}", f"QA runs of [{source}]({SOURCE_URL}{source}). Each run adds a comment; each bug is a sub-issue."
    issue = _create(
        cfg,
        title=title,
        description=f"{intro}\n\n<!-- {marker} -->",
        labelIds=[labels[n] for n in TRACKING_LABELS if n in labels],
    )
    return issue, True


def file_bug(cfg: dict[str, str], labels: dict[str, str], parent: dict[str, Any], bug: dict[str, Any], source: str, run: str) -> dict[str, Any]:
    """Create the bug, or comment on the open ticket that already has it. Returns the record for the comment."""
    fp = fingerprint(bug["scope"], source, bug["title"])
    marker = f"qx-bug:{fp}"
    existing = _find(cfg, marker)
    record = {"title": bug["title"], "severity": bug["severity"], "scope": bug["scope"], "fingerprint": fp}
    if existing and (existing.get("state") or {}).get("type") not in CLOSED_STATES:
        seen = sum(SEEN_MARK in (c.get("body") or "") for c in (existing.get("comments") or {}).get("nodes", [])) + 2
        _comment(cfg, existing["id"], f"{SEEN_MARK}\nSeen again in run `{run}` (occurrence {seen}).")
        return {**record, "status": "seen again", "occurrence": seen, "identifier": existing["identifier"], "url": existing["url"]}
    body = bug["body"]
    for shot in sorted(set(re.findall(r"bug-evidence/[\w.-]+\.png", body))):
        path = bug["folder"] / shot
        if path.is_file():
            body = body.replace(shot, upload(cfg, path))
    reopened = f"\n\nPreviously filed as {existing['identifier']} (closed)." if existing else ""
    body += f"{reopened}\n\n---\nFound by QA run `{run}`.\n\n<!-- {marker} -->"
    issue = _create(
        cfg,
        parentId=parent["id"],
        title=ticket_title(bug),
        description=body,
        priority=PRIORITY.get(bug["priority"], 3),
        labelIds=[labels[n] for n in BUG_LABELS if n in labels],
    )
    return {**record, "status": "new", "occurrence": 1, **issue}


# ── the run comment ──────────────────────────────────────────────────────────────────────────


def _bug_lines(records: list[dict[str, Any]]) -> list[str]:
    if not records:
        return ["None."]
    lines = []
    for r in records:
        tag = "new" if r["status"] == "new" else f"seen again, occurrence {r['occurrence']}"
        lines.append(f"- [{r['identifier']}]({r['url']}) ({r['severity']}, {tag}): {r['title'][:110]}")
    return lines


def run_comment(manifest: dict[str, Any], summary: dict[str, Any], attempt: int, total: int, feature: list[dict[str, Any]], e2e: list[dict[str, Any]], ux_url: str) -> str:
    tests = summary.get("tests") or {}
    minutes = round(float(summary.get("seconds") or 0) / 60)
    lines = [
        f"## QA run `{manifest.get('id')}`",
        f"**Verdict: {summary.get('verdict', 'unknown')}**  ·  run {attempt} of {total} for this ticket  ·  "
        f"{'PR #' + str(manifest['pr']) if manifest.get('pr') else str(manifest.get('trigger') or 'manual') + ' trigger'}",
        "",
        "| Area | Result |",
        "|---|---|",
        f"| Feature tests | {tests.get('passed', 0)} passed, {tests.get('failed', 0)} failed, {tests.get('flaky', 0)} flaky |",
        f"| E2E regression | {summary.get('e2e') or 'not run'} |",
        f"| UX audit | {summary.get('ux') or 'not run'} |",
        f"| Time and cost | {minutes} min, ${float(summary.get('cost') or 0):.2f} |",
        "",
        f"**Feature bugs ({len(feature)})**",
        *_bug_lines(feature),
        "",
        f"**E2E regression bugs ({len(e2e)})**",
        *_bug_lines(e2e),
        "",
        f"**UX report:** {ux_url}" if ux_url else "**UX report:** none",
    ]
    return "\n".join(lines)


# ── entry point ──────────────────────────────────────────────────────────────────────────────


def file_run(folder: Path, rel_folder: str, manifest: dict[str, Any], attempt: int, total: int, *, force: bool = False) -> dict[str, Any]:
    """File one finished run. Returns what was created; also written to `linear-filing.json`."""
    cfg = config()
    check_config(cfg)
    done = folder / "linear-filing.json"
    if done.is_file() and not force:
        return _json(done)
    summary = _json(folder / "summary.json")
    run = str(manifest.get("id") or folder.name)
    source = "e2e-journeys" if manifest.get("kind") == "phase1" else str(manifest.get("ticket") or "")
    if not source:
        raise LinearError("this run has no ticket to file under")

    labels = _labels(cfg)
    parent, created = tracking_ticket(cfg, labels, source)
    feature = [] if manifest.get("kind") == "phase1" else collect_bugs(folder, "feature")
    e2e_folder = folder if manifest.get("kind") == "phase1" else folder / "e2e"
    e2e = collect_bugs(e2e_folder, "e2e")

    filed_feature = [file_bug(cfg, labels, parent, b, source, run) for b in feature]
    filed_e2e = [file_bug(cfg, labels, parent, b, source, run) for b in e2e]

    ux_url = ""
    ux_file = folder / "ux-report.html"
    if ux_file.is_file():
        base = cfg["report_base"]
        ux_url = f"{base}/{rel_folder}/ux-report.html" if base else upload(cfg, ux_file)

    comment_url = _comment(cfg, parent["id"], run_comment(manifest, summary, attempt, total, filed_feature, filed_e2e, ux_url))
    result = {
        "run": run,
        "ticket": {"identifier": parent["identifier"], "url": parent["url"], "created": created},
        "comment": comment_url,
        "feature_bugs": filed_feature,
        "e2e_bugs": filed_e2e,
        "ux_report": ux_url,
    }
    done.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    """File a finished run again by hand:  python -m app.linear_log <run id or folder> [--force]"""
    import argparse

    from app import store

    parser = argparse.ArgumentParser(prog="python -m app.linear_log", description="Log a finished run to Linear.")
    parser.add_argument("run", help="run id, or the run folder under runs/")
    parser.add_argument("--force", action="store_true", help="file again even if linear-filing.json exists")
    args = parser.parse_args(argv)
    rows = store.list_runs()
    row = next((r for r in rows if r.get("id") == args.run or r.get("folder") == args.run.strip("/")), None)
    if row is None:
        print(f"no run {args.run} in the index")
        return 64
    folder = store.run_dir(str(row["id"]))
    attempt, total = attempt_of(row, rows)
    print(json.dumps(file_run(folder, str(row.get("folder") or ""), row, attempt, total, force=args.force), indent=2, default=str))
    return 0


def attempt_of(row: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[int, int]:
    """`run 3 of 5` for this source ticket, from the harness's own index (Linear has no such counter)."""
    same = sorted(
        (r for r in rows if r.get("kind") == row.get("kind") and r.get("ticket") == row.get("ticket")),
        key=lambda r: str(r.get("createdAt") or ""),
    )
    ids = [r.get("id") for r in same]
    return (ids.index(row.get("id")) + 1 if row.get("id") in ids else len(ids), len(ids))


if __name__ == "__main__":
    raise SystemExit(main())
