#!/usr/bin/env python3
"""
Validate a generated ux-report.html against .agents/ux/report-contract.md.

This is the regression gate for the report layer. It reads the HTML only — it does not
audit the product and it cannot tell whether a finding is true. What it can tell you is
whether the report still honours the contract: ticket-driven matrix, journey-scoped
checks, one verdict, Expected/Observed on every card, no placeholders, no raw dicts,
no boilerplate results, and counts that agree with each other.

Usage:
    python3 scripts/check_report_contract.py <run_dir | ux-report.html> [--json] [--strict] [--quiet]

Exit codes:
    0  every rule passed (warnings allowed unless --strict)
    1  at least one failure
    2  the report could not be read
"""

import json
import re
import sys
import html as H
from pathlib import Path

ALLOWED_VERDICTS = {"PASS", "PASS WITH ADVISORIES", "BLOCKED", "FAIL", "BLOCKING FAIL", "INCOMPLETE"}

# Results that belonged to a different journey in an earlier generation of the report.
BOILERPLATE_PHRASES = [
    "license revocation",
    "licence revocation",
    "tenant downgrade",
    "bulk license",
    "bulk licence",
    "users and clients tabs",
    "assign licenses",
]


class Result:
    def __init__(self):
        self.failures = []
        self.warnings = []
        self.passes = 0

    def fail(self, rule, message):
        self.failures.append((rule, message))

    def warn(self, rule, message):
        self.warnings.append((rule, message))

    def ok(self):
        self.passes += 1


def detag(fragment):
    """Strip tags and unescape, collapsing whitespace. CSS/JS must be removed by the caller."""
    text = re.sub(r'<[^>]+>', ' ', fragment)
    text = H.unescape(text)
    return " ".join(text.split())


def load(html_path):
    raw = html_path.read_text(encoding="utf-8", errors="replace")
    # drop CSS and JS so class names and scripts never look like report copy
    body = re.sub(r'<style[^>]*>.*?</style>', ' ', raw, flags=re.S | re.I)
    body = re.sub(r'<script[^>]*>.*?</script>', ' ', body, flags=re.S | re.I)
    return raw, body


def section(body, element_id):
    """Return the HTML of a tab pane by id (up to the next tab pane or the lightbox)."""
    m = re.search(r'id="' + re.escape(element_id) + r'"', body)
    if not m:
        return ""
    start = m.start()
    nxt = re.search(r'<div id="tab-[a-z]+" class="tab-pane|<div id="lightbox"', body[start + 10:])
    end = start + 10 + nxt.start() if nxt else len(body)
    return body[start:end]


def norm_verdict(value):
    v = " ".join(str(value or "").upper().split())
    if v in ("FAIL", "BLOCKING FAIL", "BLOCKING-FAIL"):
        return "BLOCKED"
    return v


def check(raw, body, res):
    text = detag(body)
    cards = re.findall(r'<article class="finding-card[^"]*".*?</article>', body, flags=re.S)
    ac_sec = section(body, "tab-ac")
    chk_sec = section(body, "tab-criteria")

    # ---------- 1. self-contained document ----------
    if raw.lstrip().lower().startswith("<!doctype html"):
        res.ok()
    else:
        res.fail("doctype-missing", "The file does not start with <!DOCTYPE html>.")
    if "<style" in raw:
        res.ok()
    else:
        res.fail("inline-style-missing", "No inline <style> block; the report must be self-contained.")
    if re.search(r'<script[^>]+src=', raw, re.I):
        res.fail("external-script", "A <script src=…> was found; the report must not require an external runtime.")
    else:
        res.ok()

    # ---------- 2. placeholders and raw data ----------
    placeholder_rules = [
        ("placeholder-expected-actual", "No expected vs actual documented",
         "A finding fell back to the 'not documented' placeholder instead of Expected/Observed text."),
        ("placeholder-ac-matrix", "No specific acceptance criteria breakdown",
         "The acceptance matrix printed its empty-state placeholder instead of scoring the ticket."),
        ("unmapped-pattern", "Unmapped / candidate",
         "A pattern chip printed a taxonomy miss instead of a real BP-* id or nothing."),
    ]
    for rule, needle, message in placeholder_rules:
        if needle.lower() in text.lower():
            res.fail(rule, message)
        else:
            res.ok()

    if re.search(r'\{\s*[\'"]what[\'"]\s*:', text):
        res.fail("raw-dict-in-copy", "A raw dict literal ({'what': …}) reached the report copy.")
    elif re.search(r'[\'"]developer[\'"]\s*:\s*[\'"]', text):
        res.fail("raw-dict-in-copy", "A raw dict literal reached the report copy.")
    else:
        res.ok()

    # ---------- 3. hero carries the whole ticket ----------
    if "Ticket as filed" in text:
        res.ok()
    else:
        res.fail("ticket-block-missing", "No 'Ticket as filed' block; the report does not show the ticket it audited.")
    if "Acceptance Criteria" in text or "acceptance criteria" in text.lower():
        res.ok()
    else:
        res.warn("ticket-acceptance-missing", "The report shows no acceptance criteria.")
    hero = re.search(r'class="hero-description"[^>]*>(.*?)</p>', body, re.S)
    if hero:
        hero_text = detag(hero.group(1))
        if hero_text.endswith("...") or hero_text.endswith("…"):
            res.fail("ticket-truncated", "The hero summary is truncated with an ellipsis.")
        else:
            res.ok()
    ticket_block = re.search(r'<div class="ticket-block">(.*?)</div>\s*</div>', body, re.S)
    if ticket_block:
        tb = detag(ticket_block.group(1))
        if tb.endswith("...") or tb.endswith("…"):
            res.fail("ticket-truncated", "The ticket block text is truncated with an ellipsis.")
        else:
            res.ok()

    # ---------- 4. one verdict, consistent with severity ----------
    found = []
    m = re.search(r'class="badge-pill[^"]*">QA:\s*([A-Za-z_\- ]+)</span>', body)
    if m:
        found.append(("nav badge", norm_verdict(m.group(1))))
    m = re.search(r'class="verdict-text">(.*?)</div>', body, re.S)
    if m:
        found.append(("hero card", norm_verdict(detag(m.group(1)))))
    m = re.search(r'One verdict applies to this report:\s*<strong>([A-Za-z_\- ]+)</strong>', body, re.S)
    if m:
        found.append(("integrity strip", norm_verdict(m.group(1))))
    m = re.search(r'Verdict:\s*([A-Za-z_\- ]+?)\s*</p>', body, re.S)
    if m:
        found.append(("footer", norm_verdict(m.group(1))))

    verdicts = {v for _, v in found if v}
    if not verdicts:
        res.fail("verdict-missing", "No verdict could be read from the nav, hero, integrity strip or footer.")
    elif len(verdicts) > 1:
        detail = ", ".join(f"{where}={v}" for where, v in found)
        res.fail("verdict-count", f"The report shows more than one verdict: {detail}.")
    else:
        res.ok()
        displayed = verdicts.pop()
        if displayed not in ALLOWED_VERDICTS:
            res.warn("verdict-unrecognised", f"Verdict '{displayed}' is outside the contract's vocabulary.")

        # severity counts from the Defects stat card
        card = re.search(r'Defects \(S0[^)]*\)(.*?)</div>\s*</div>', body, re.S)
        counts = {}
        if card:
            seg = detag(card.group(1))
            for sev in ("S0", "S1", "S2", "S3"):
                sm = re.search(sev + r'\s*(\d+)', seg)
                if sm:
                    counts[sev] = int(sm.group(1))
        if len(counts) == 4:
            expected = "BLOCKED" if counts["S0"] + counts["S1"] else (
                "PASS WITH ADVISORIES" if counts["S2"] + counts["S3"] else "PASS")
            if expected != displayed:
                res.fail("verdict-severity-mismatch",
                         f"Verdict says {displayed} but the severities (S0 {counts['S0']}, S1 {counts['S1']}, "
                         f"S2 {counts['S2']}, S3 {counts['S3']}) derive {expected}.")
            else:
                res.ok()
            # stat card must agree with the cards actually rendered
            rendered = {}
            for sev in re.findall(r'<article class="finding-card severity-(S[0-3])"', body):
                rendered[sev] = rendered.get(sev, 0) + 1
            mismatched = {s: (counts[s], rendered.get(s, 0)) for s in counts if counts[s] != rendered.get(s, 0)}
            if mismatched:
                detail = "; ".join(f"{s} card says {a}, {b} rendered" for s, (a, b) in mismatched.items())
                res.fail("defect-count-mismatch", f"Stat card and defect cards disagree: {detail}.")
            else:
                res.ok()

    # ---------- 5. acceptance criteria / scope matrix ----------
    ac_rows = re.findall(r'<tr>\s*<td><span class="ac-item">(.*?)</span>', ac_sec, re.S)
    if ac_rows:
        res.ok()
        rows = re.findall(r'<tr>(.*?)</tr>', ac_sec, re.S)
        bad_reason, bad_status = [], []
        for row in rows:
            if 'class="ac-item"' not in row:
                continue
            label = detag(re.search(r'class="ac-item">(.*?)</span>', row, re.S).group(1))
            if 'class="ac-note"' not in row or not detag(
                    re.search(r'class="ac-note">(.*?)</div>', row, re.S).group(1)):
                bad_reason.append(label)
            if not re.search(r'class="badge-status', row):
                bad_status.append(label)
        if bad_status:
            res.fail("ac-row-without-status", f"Matrix rows with no status: {', '.join(bad_status)}.")
        else:
            res.ok()
        if bad_reason:
            res.fail("ac-row-without-reason", f"Matrix rows with no stated reason: {', '.join(bad_reason)}.")
        else:
            res.ok()
        statuses = [detag(x) for x in re.findall(r'class="badge-status[^"]*">(.*?)</span>', ac_sec, re.S)]
        known = {"VERIFIED", "VERIFIED WITH ADVISORY", "PARTIAL", "DEFECT FOUND", "UNVERIFIED",
                 "OUTSTANDING", "BLOCKED"}
        unknown = [s for s in statuses if s.upper() not in known]
        if unknown:
            res.warn("ac-status-unrecognised", f"Matrix statuses outside the contract vocabulary: {set(unknown)}.")
        else:
            res.ok()
    else:
        res.fail("ac-matrix-empty",
                 "The Acceptance Criteria & Scope Matrix has no rows. Read the ticket's criteria, scope and "
                 "validation claim; an empty matrix needs a stated reason, not silence.")

    # ---------- 6. checks matrix ----------
    chk_rows = re.findall(r'<span class="badge-status[^"]*">', chk_sec)
    if chk_rows:
        res.ok()
    else:
        res.fail("checks-table-empty", "The Evaluated Checks Matrix has no rows.")

    for phrase in BOILERPLATE_PHRASES:
        if phrase in detag(chk_sec).lower():
            res.fail("boilerplate-check-result",
                     f"The checks table carries a result sentence from another journey ('{phrase}').")
            break
    else:
        res.ok()

    n_pass = len(re.findall(r'class="badge-status status-pass', chk_sec))
    n_note = len(re.findall(r'class="badge-status status-note', chk_sec))
    n_def = len(re.findall(r'class="badge-status status-defect', chk_sec))
    n_na = len(re.findall(r'class="badge-status status-na', chk_sec))
    chk_text = detag(chk_sec)
    tally = re.search(r'(\d+)\s+exercised\s*\((\d+)\s*pass,\s*(\d+)\s*observation,\s*(\d+)\s*defect\)\s*•?\s*(\d+)\s*not applicable',
                      chk_text)
    if tally:
        e, p, o, d, na = (int(x) for x in tally.groups())
        actual = (n_pass + n_note + n_def, n_pass, n_note, n_def, n_na)
        if (e, p, o, d, na) != actual:
            res.fail("checks-tally-mismatch",
                     f"Tally line says {e} exercised ({p} pass, {o} observation, {d} defect) · {na} N/A, "
                     f"but the table renders {actual[0]} exercised ({actual[1]} pass, {actual[2]} observation, "
                     f"{actual[3]} defect) · {actual[4]} N/A.")
        else:
            res.ok()
    else:
        res.warn("checks-tally-missing", "No tally line under the checks table.")

    integrity = re.search(r'Run integrity(.*?)</div>\s*</div>', body, re.S)
    if integrity:
        res.ok()
        ig = detag(integrity.group(1))
        im = re.search(r'(\d+) of (\d+)\s*checks', ig)
        if im and tally:
            if int(im.group(1)) != e or int(im.group(2)) != e + na:
                res.fail("integrity-checks-mismatch",
                         f"Integrity strip says {im.group(1)} of {im.group(2)} exercised; the checks tally "
                         f"says {e} of {e + na}.")
            else:
                res.ok()
    else:
        res.fail("integrity-strip-missing",
                 "No integrity strip under the summary cards (checks exercised, verdict arithmetic, open items).")

    # ---------- 7. finding cards ----------
    if not cards:
        res.warn("no-finding-cards", "No finding cards in the report.")
    ids, no_expected, no_actual, no_res, no_evidence, no_scope = [], [], [], [], [], []
    for card_html in cards:
        cid_m = re.search(r'class="finding-id">(.*?)</span>', card_html, re.S)
        cid = detag(cid_m.group(1)) if cid_m else "?"
        ids.append(cid)
        if 'class="callout-expected"' not in card_html:
            no_expected.append(cid)
        if 'class="callout-actual"' not in card_html:
            no_actual.append(cid)
        if 'class="res-block"' not in card_html or "What to change" not in detag(card_html):
            no_res.append(cid)
        if not re.search(r'evidence-list-label', card_html) or not re.search(
                r'evidence-list-label.*?<li>', card_html, re.S):
            no_evidence.append(cid)
        if re.search(r'severity-S[0-3]', card_html) and 'class="tag-scope' not in card_html:
            no_scope.append(cid)

    for rule, offenders, message in (
        ("card-missing-expected", no_expected, "cards with no EXPECTED callout"),
        ("card-missing-actual", no_actual, "cards with no ACTUAL/OBSERVED callout"),
        ("card-missing-resolution", no_res, "cards with no What/Developer/Design resolution block"),
        ("card-missing-evidence", no_evidence, "cards with no Evidence list"),
    ):
        if offenders:
            res.fail(rule, f"{len(offenders)} {message}: {', '.join(offenders[:6])}"
                           + (" …" if len(offenders) > 6 else ""))
        else:
            res.ok()

    if no_scope:
        res.warn("defect-missing-scope-chip",
                 f"Defect cards with no In scope / Pre-existing chip: {', '.join(no_scope[:6])}")
    else:
        res.ok()

    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        res.fail("duplicate-finding-id", f"Duplicate finding ids: {', '.join(sorted(dupes))}.")
    else:
        res.ok()

    return res


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("-")]
    flags = {a for a in argv[1:] if a.startswith("-")}
    if len(args) != 1:
        print(__doc__.strip())
        return 2

    target = Path(args[0])
    html_path = target / "ux-report.html" if target.is_dir() else target
    if not html_path.is_file():
        print(f"check_report_contract: cannot read {html_path}")
        return 2

    raw, body = load(html_path)
    res = check(raw, body, Result())

    if "--json" in flags:
        print(json.dumps({
            "report": str(html_path),
            "ok": not res.failures,
            "rules_passed": res.passes,
            "failures": [{"rule": r, "message": m} for r, m in res.failures],
            "warnings": [{"rule": r, "message": m} for r, m in res.warnings],
        }, indent=2))
    else:
        if "--quiet" not in flags:
            print(f"check_report_contract — {html_path}")
        for rule, message in res.failures:
            print(f"  FAIL  {rule}: {message}")
        for rule, message in res.warnings:
            print(f"  warn  {rule}: {message}")
        if "--quiet" not in flags:
            print(f"  {res.passes} rule group(s) passed, {len(res.failures)} failure(s), {len(res.warnings)} warning(s)")

    failed = bool(res.failures) or ("--strict" in flags and bool(res.warnings))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
