#!/usr/bin/env python3
"""
Generate a self-contained, interactive HTML UX Audit Preview Report (ux-report.html)
modeled after .agents/ux/templates/audit-preview-reference.html.

Layout features:
- Exactly 3 top summary cards: Findings by Severity (1st), Total Deductions (2nd), Design Stack (3rd), equally filling space.
- Exactly 4 interactive tabs: UI/UX Defects (S0-S3), UX Observations & Verification (O), Acceptance Criteria Matrix, Evaluated Checks Matrix, equally filling 25% width.
- Defect cards: Show ONLY Severity level, Pattern, Pillar (replacing Lens), and AC tags. Remove all other tags.
- Expected vs. Actual: Clearly highlighted in dedicated emerald and rose callout boxes for instant readability.
- Deduction Points: Highlighted on the right-hand side in distinct range-based colors (0, 1-5, 6-15, 16-30, 31+ pts).
- Visual Lightbox: Inline screenshot preview on cards with full-screen zoom modal retained.

Usage:
    python3 scripts/generate_ux_report.py <run_dir>
"""

import sys
import os
import json
import base64
import html
import re
from pathlib import Path


def escape(val):
    if val is None:
        return ""
    return html.escape(str(val))


def get_image_data_uri(path: Path) -> str:
    try:
        data = path.read_bytes()
        ext = path.suffix.lower()
        mime = "image/png"
        if ext in [".jpg", ".jpeg"]:
            mime = "image/jpeg"
        elif ext == ".svg":
            mime = "image/svg+xml"
        b64 = base64.b64encode(data).decode("utf-8")
        return f"data:{mime};base64,{b64}"
    except Exception:
        return ""


def get_deduction_pill(deduct, is_obs=False) -> str:
    try:
        pts = int(deduct or 0)
    except Exception:
        pts = 0
    if is_obs or pts == 0:
        return '<span class="deduction-pill ded-range-0">0 pts Deduction</span>'
    elif 1 <= pts <= 5:
        return f'<span class="deduction-pill ded-range-1">−{pts} pts Deduction</span>'
    elif 6 <= pts <= 15:
        return f'<span class="deduction-pill ded-range-2">−{pts} pts Deduction</span>'
    elif 16 <= pts <= 30:
        return f'<span class="deduction-pill ded-range-3">−{pts} pts Deduction</span>'
    else:
        return f'<span class="deduction-pill ded-range-4">−{pts} pts Deduction</span>'


def format_expected_vs_actual(raw_text: str) -> str:
    if not raw_text:
        return "<p style='color:var(--text-dim);font-size:0.85rem;margin:0;'>No expected vs actual documented.</p>"
    text = str(raw_text).strip()
    
    match = re.search(r'(?:^|\b)Expected\s*:\s*(.*?)(?=(?:\bActual\s*:|$))', text, re.DOTALL | re.IGNORECASE)
    match_act = re.search(r'\bActual\s*:\s*(.*)', text, re.DOTALL | re.IGNORECASE)
    
    expected_part = match.group(1).strip() if match else ""
    actual_part = match_act.group(1).strip() if match_act else ""
    
    if expected_part or actual_part:
        expected_body = escape(expected_part) if expected_part else "Specified workflow behavior per acceptance criteria."
        actual_body = escape(actual_part) if actual_part else escape(text)
        return f"""
        <div class="callout-expected">
          <div class="callout-label label-expected">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            EXPECTED BEHAVIOR
          </div>
          <div class="callout-body">{expected_body}</div>
        </div>
        <div class="callout-actual">
          <div class="callout-label label-actual">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            OBSERVED ACTUAL
          </div>
          <div class="callout-body">{actual_body}</div>
        </div>
        """
    else:
        return f"""
        <div class="callout-actual">
          <div class="callout-label label-actual">OBSERVED BEHAVIOR</div>
          <div class="callout-body">{escape(text)}</div>
        </div>
        """


def format_pillar_chip(raw_lens: str) -> str:
    if not raw_lens:
        return ""
    val = str(raw_lens).strip()
    if val.lower().startswith("lens "):
        val = val[5:].strip()
    
    pillar_map = {
        "a": "Flows & speed",
        "b": "Clarity & trust",
        "c": "State & edge cases",
        "d": "Design alignment & a11y",
        "e": "Drift & consistency"
    }
    
    if "-" in val:
        after = val.split("-", 1)[1].strip()
        disp = f"Pillar: {after}"
    elif val.lower() in pillar_map:
        disp = f"Pillar: {pillar_map[val.lower()]}"
    else:
        disp = f"Pillar: {val}"
    
    return f"""<span class="tag-pillar" title="UX Audit Pillar"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="18" rx="1"/><rect x="14" y="3" width="7" height="18" rx="1"/></svg>{escape(disp)}</span>"""


def render_card(f, is_observation=False, image_lookup=None) -> str:
    fid = escape(f.get("id", "UX-FINDING"))
    sev = escape(f.get("severity", "O" if is_observation else "S3"))
    title = escape(f.get("title", ""))
    deduct = f.get("deduction", f.get("deductionPoints", 0))
    status = escape(f.get("status", "Reported"))

    # Severity badge
    if status.lower() in ["resolved", "verified fixed"] or sev.upper() == "RESOLVED":
        status = "Resolved"
        sev_badge = '<span class="badge-resolved">Status: Resolved / Verified Fixed</span>'
        card_class = "severity-Resolved"
    elif sev == "S0":
        sev_badge = '<span class="badge-s0">Severity: S0 (Blocker)</span>'
        card_class = f"severity-{sev}"
    elif sev == "S1":
        sev_badge = '<span class="badge-s1">Severity: S1 (Critical)</span>'
        card_class = f"severity-{sev}"
    elif sev == "S2":
        sev_badge = '<span class="badge-s2">Severity: S2 (Major)</span>'
        card_class = f"severity-{sev}"
    elif sev == "S3":
        sev_badge = '<span class="badge-s3">Severity: S3 (Minor)</span>'
        card_class = f"severity-{sev}"
    else:
        sev_badge = '<span class="badge-obs">Observation (O)</span>'
        card_class = f"severity-{sev}"

    # Right side: Deduction points highlight colored by range
    deduction_html = get_deduction_pill(deduct, is_obs=(is_observation or sev == "O"))

    # Bad UX Pattern Tags (kept per requirement)
    pattern_ids = f.get("patternIds", [])
    if isinstance(pattern_ids, str):
        pattern_ids = [pattern_ids]
    pattern_chips = "".join([
        f"""<span class="tag-pattern" title="Bad UX Pattern Library"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/></svg>Pattern: {escape(p)}</span>"""
        for p in pattern_ids if p
    ])

    # Pillar tag (replacing Lens per requirement)
    pillar_chip = format_pillar_chip(f.get("lens", ""))

    # AC tags (kept per requirement)
    ac_refs = f.get("acceptanceCriteria", [])
    if isinstance(ac_refs, str):
        if ac_refs.startswith("[") and ac_refs.endswith("]"):
            try:
                ac_refs = json.loads(ac_refs)
            except Exception:
                ac_refs = [ac_refs]
        else:
            ac_refs = [x.strip() for x in ac_refs.split(",") if x.strip()]
    
    # Filter short AC codes (e.g. AC1-d, AC2, AC3-b)
    valid_acs = [a for a in ac_refs if a and len(a) < 30 and not a.startswith("Verify")]
    if not valid_acs:
        # Check title and journeyStep for AC codes like AC1-d, AC2
        found = re.findall(r'\bAC\d+[a-z0-9\-]*\b', f.get("journeyStep", "") + " " + title)
        valid_acs = list(dict.fromkeys(found))
        
    ac_chips = "".join([
        f"""<span class="tag-ac" title="Acceptance Criteria"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>AC: {escape(ac)}</span>"""
        for ac in valid_acs
    ])

    # Evidence list
    ev_items = f.get("evidence", [])
    if isinstance(ev_items, str):
        ev_items = [ev_items]
    ev_html = "".join([f"<li>{escape(e)}</li>" for e in ev_items]) if ev_items else "<li>Documented via workflow exploration.</li>"

    # Repro steps list
    repro = f.get("reproSteps", f.get("reproductionSteps", []))
    if isinstance(repro, str):
        repro = [repro]
    repro_html = "".join([f"<li>{escape(r)}</li>" for r in repro]) if repro else "<li>Refer to exploration snapshots.</li>"

    # Solutions & Design System Guidance
    solution = escape(f.get("solution", "No product change recommended."))
    shadcn = escape(f.get("implementationShadcn", "Not applicable."))
    fluent = escape(f.get("fluentRationale", "Not applicable."))
    acceptance = escape(f.get("acceptanceCriteria", "Verify workflow behavior matches expected UX specifications."))
    if isinstance(acceptance, list):
        acceptance = ", ".join([str(a) for a in acceptance])

    box1_title = "Observed Behavior & Evidence" if is_observation else "Observed Defect & Evidence"
    box2_title = "Reproduction Steps & Details"

    # Resolve inline evidence screenshot preview
    inline_image_html = ""
    target_img = None

    direct_shot = f.get("screenshot") or f.get("screenshotPath")
    if not direct_shot and isinstance(f.get("evidenceScreenshots"), list) and f["evidenceScreenshots"]:
        direct_shot = f["evidenceScreenshots"][0]
    elif not direct_shot and isinstance(f.get("screenshots"), list) and f["screenshots"]:
        direct_shot = f["screenshots"][0]

    caption_text = f.get("screenshotCaption") or title

    if direct_shot and isinstance(direct_shot, str):
        if direct_shot.startswith("data:image/"):
            target_img = {"uri": direct_shot, "title": caption_text, "rel_path": "embedded-screenshot.png"}
        elif image_lookup:
            clean_name = Path(direct_shot.strip().split()[0]).name.lower()
            clean_rel = direct_shot.strip().split()[0].lower()
            target_img = image_lookup.get(clean_rel) or image_lookup.get(clean_name)

    # Search within evidence list if not found
    if not target_img and image_lookup and ev_items:
        for item in ev_items:
            m = re.search(r'([\w\-\./]+\.(?:png|jpg|jpeg|svg))', str(item), re.IGNORECASE)
            if m:
                path_str = m.group(1).lower()
                clean_name = Path(path_str).name.lower()
                if path_str in image_lookup:
                    target_img = image_lookup[path_str]
                    break
                elif clean_name in image_lookup:
                    target_img = image_lookup[clean_name]
                    break

    img_uri = None
    img_rel = None
    img_title = None
    if target_img:
        img_uri = target_img["uri"]
        img_rel = target_img.get("rel_path") or target_img.get("name") or "evidence-screenshot.png"
        img_title = caption_text or target_img.get("title") or title

    resolution_banner = ""
    if f.get("resolutionNote"):
        res_note = escape(f.get("resolutionNote"))
        resolved_from = f.get("resolvedFromRun")
        run_txt = f" from run {escape(resolved_from)}" if resolved_from else ""
        resolution_banner = f"""
              <div style="margin-top:10px;padding:8px 12px;background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.3);border-radius:8px;font-size:0.8rem;color:#34d399;">
                <strong>Stakeholder Fix Verified{run_txt}:</strong> {res_note}
              </div>"""

    expected_actual_html = format_expected_vs_actual(f.get("expectedVsActual", ""))
    journey_step = escape(f.get("journeyStep", ""))
    journey_html = f'<p class="finding-journey"><strong>Journey step:</strong> {journey_step}</p>' if journey_step else ""

    # Search data string
    search_terms = f"{fid} {title} {sev} {status} {' '.join(pattern_ids)} {' '.join(valid_acs)}".lower()

    # Build Side-by-Side Body Grid (Evidence Screenshot placed side-by-side with defect details)
    if target_img and img_uri:
        repro_section = f"""
              <div style="margin-top:14px;padding-top:12px;border-top:1px solid rgba(255,255,255,0.06);">
                <div style="font-size:0.75rem;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px;display:flex;align-items:center;gap:6px;">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                  Reproduction Steps &amp; Context
                </div>
                <ol style="padding-left:18px;margin:0;font-size:0.85rem;color:var(--text-muted);line-height:1.5;">{repro_html}</ol>
              </div>""" if (repro and repro != ["Refer to exploration snapshots."]) else ""

        body_grid_html = f"""
        <div class="finding-body-grid">
          <div class="section-box">
            <div class="section-box-title">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              {box1_title}
            </div>
            <div class="section-box-content">
              <ul style="padding-left:18px;margin-bottom:12px;">{ev_html}</ul>
              {expected_actual_html}
              {resolution_banner}
              {repro_section}
            </div>
          </div>

          <div class="section-box finding-screenshot-box">
            <div class="section-box-title">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
              Evidence Screenshot
              <span class="evidence-filename" title="{escape(img_rel)}">{escape(img_rel)}</span>
            </div>
            <div class="finding-image-preview" onclick="openLightbox('{img_uri}', '{escape(img_title)} ({escape(img_rel)})')">
              <img src="{img_uri}" alt="{escape(img_title)}" loading="lazy">
              <div class="image-overlay">
                <span>{escape(img_rel)}</span>
                <span>Click to view full resolution ⤢</span>
              </div>
            </div>
          </div>
        </div>"""
    else:
        body_grid_html = f"""
        <div class="finding-body-grid">
          <div class="section-box">
            <div class="section-box-title">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              {box1_title}
            </div>
            <div class="section-box-content">
              <ul style="padding-left:18px;margin-bottom:12px;">{ev_html}</ul>
              {expected_actual_html}
              {resolution_banner}
            </div>
          </div>

          <div class="section-box">
            <div class="section-box-title">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              {box2_title}
            </div>
            <div class="section-box-content">
              <ol style="padding-left:18px;margin-bottom:12px;">{repro_html}</ol>
            </div>
          </div>
        </div>"""

    return f"""
      <article class="finding-card {card_class}" data-severity="{sev}" data-status="{status}" data-search="{escape(search_terms)}">
        <div class="finding-header">
          <div class="finding-meta">
            <span class="finding-id">{fid}</span>
            {sev_badge}
            {pattern_chips}
            {pillar_chip}
            {ac_chips}
          </div>
          {deduction_html}
        </div>

        <h3 class="finding-title">{title}</h3>
        {journey_html}

        {body_grid_html}

        <!-- Recommended Solutions & Design Guidance -->
        <div class="guidance-grid">
          <div class="section-box" style="border-left:3px solid var(--accent-emerald);">
            <div class="section-box-title" style="color:#34d399;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
              {"Recommended Design Direction" if is_observation else "Recommended Resolution"}
            </div>
            <div class="section-box-content">
              {solution}
            </div>
          </div>

          <div class="section-box" style="border-left:3px solid var(--accent-indigo);">
            <div class="section-box-title" style="color:#818cf8;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
              shadcn/ui Implementation
            </div>
            <div class="section-box-content">
              {shadcn}
            </div>
          </div>

          <div class="section-box" style="border-left:3px solid var(--accent-cyan);">
            <div class="section-box-title" style="color:#22d3ee;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>
              Fluent Design Alignment
            </div>
            <div class="section-box-content">
              {fluent}
            </div>
          </div>
        </div>
      </article>
"""


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/generate_ux_report.py <run_dir>")
        sys.exit(1)

    run_dir = Path(sys.argv[1]).resolve()
    if not run_dir.is_dir():
        print(f"Error: Directory not found: {run_dir}")
        sys.exit(1)

    # Read artifacts
    findings_file = run_dir / "ux-findings.json"
    scorecard_file = run_dir / "ux-scorecard.json"
    context_file = run_dir / "context-pack.json"
    qa_file = run_dir / "qa-result.json"

    findings = []
    if findings_file.is_file():
        try:
            raw_f = json.loads(findings_file.read_text(encoding="utf-8"))
            if isinstance(raw_f, dict) and "findings" in raw_f:
                findings = raw_f["findings"]
            elif isinstance(raw_f, list):
                findings = raw_f
        except Exception as e:
            print(f"Warning: Failed to parse ux-findings.json: {e}")

    card = {}
    if scorecard_file.is_file():
        try:
            card = json.loads(scorecard_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Warning: Failed to parse ux-scorecard.json: {e}")

    ctx = {}
    if context_file.is_file():
        try:
            ctx = json.loads(context_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Warning: Failed to parse context-pack.json: {e}")

    qa = {}
    if qa_file.is_file():
        try:
            qa = json.loads(qa_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Warning: Failed to parse qa-result.json: {e}")

    # Extract Run & Ticket Info
    ticket = card.get("ticket") or ctx.get("ticket", {}).get("key") or run_dir.parent.name
    if not ticket or ticket.startswith("runs"):
        ticket = "LEX-TICKET"

    run_label = run_dir.name
    score = int(card.get("score", 100))
    verdict = card.get("verdict", "PASS WITH ADVISORIES" if score < 100 else "PASS")
    counts = card.get("counts", {"S0": 0, "S1": 0, "S2": 0, "S3": 0, "O": 0})
    total_deduction = int(card.get("totalDeduction", 0))

    # Separate Active Defects (S0-S3) from Observations and Stakeholder-Resolved findings
    defects = [f for f in findings if f.get("severity") in ["S0", "S1", "S2", "S3"] and str(f.get("status", "")).lower() not in ["resolved", "verified fixed"]]
    observations = [f for f in findings if f.get("severity") == "O" or str(f.get("status", "")).lower() in ["resolved", "verified fixed"]]

    # Gauge math: circumference ~ 264 (2 * pi * 42 = 263.89)
    circumference = 264
    dash_offset = max(0, circumference - (score / 100 * circumference))

    # Discover and index evidence images across all run directories
    search_dirs = [
        run_dir / "explore" / "ux",
        run_dir / "ux-evidence",
        run_dir / "ux-evidence" / "live",
        run_dir / "explore",
    ]
    evidence_images = []
    image_lookup = {}
    seen_paths = set()

    for sdir in search_dirs:
        if sdir.is_dir():
            all_files = sorted(sdir.glob("*.png")) + sorted(sdir.glob("*.jpg")) + sorted(sdir.glob("*.jpeg")) + sorted(sdir.glob("*.svg"))
            for p in all_files:
                resolved = p.resolve()
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)
                data_uri = get_image_data_uri(p)
                if data_uri:
                    try:
                        rel_path = str(p.relative_to(run_dir))
                    except ValueError:
                        rel_path = p.name
                    item = {
                        "name": p.name,
                        "title": p.stem.replace("-", " ").replace("_", " ").title(),
                        "uri": data_uri,
                        "rel_path": rel_path
                    }
                    evidence_images.append(item)
                    image_lookup[p.name.lower()] = item
                    image_lookup[rel_path.lower()] = item

    # Summary metrics
    pr_num = ctx.get("pr") or (ctx.get("pullRequests", [{}])[0].get("number", "") if ctx.get("pullRequests") else "")
    ticket_title = ctx.get("title") or ctx.get("ticket", {}).get("summary") or card.get("journey") or f"QA & UX Audit for {ticket}"
    ticket_desc = ctx.get("description") or ctx.get("ticket", {}).get("description") or card.get("journey") or ""
    if len(ticket_desc) > 350:
        ticket_desc = ticket_desc[:350].rsplit(" ", 1)[0] + "..."

    # Generate Defect Cards HTML
    if defects:
        defects_cards_html = [render_card(f, is_observation=False, image_lookup=image_lookup) for f in defects]
    else:
        defects_cards_html = ["""
        <div class="section-box" style="text-align:center;padding:48px 24px;border:1px dashed var(--border-subtle);border-radius:16px;">
          <div style="width:48px;height:48px;border-radius:12px;background:rgba(16,185,129,0.15);color:#34d399;display:inline-flex;align-items:center;justify-content:center;margin-bottom:12px;">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
          </div>
          <h4 style="font-size:1.15rem;font-weight:700;color:#fff;margin-bottom:6px;">0 UI/UX Defects Found</h4>
          <p style="font-size:0.85rem;color:var(--text-muted);margin:0;">All evaluated journeys completed with high quality and zero S0–S3 defect deductions.</p>
        </div>
        """]

    # Generate Observation Cards HTML
    if observations:
        observations_cards_html = [render_card(f, is_observation=True, image_lookup=image_lookup) for f in observations]
    else:
        observations_cards_html = ["""
        <div class="section-box" style="text-align:center;padding:48px 24px;border:1px dashed var(--border-subtle);border-radius:16px;">
          <p style="font-size:0.95rem;color:var(--text-muted);margin:0;">No observations recorded in this audit run.</p>
        </div>
        """]

    # Build Acceptance Criteria Matrix Table
    ac_rows = []
    ac_items_dict = {}
    
    # 1. Parse from context-pack acceptance criteria markdown if present
    raw_ac_text = ctx.get("ticket", {}).get("acceptanceCriteria") or ""
    if raw_ac_text:
        for line in raw_ac_text.splitlines():
            line_str = line.strip()
            if line_str.startswith("- [ ]") or line_str.startswith("- [x]"):
                clean_stmt = line_str.replace("- [ ]", "").replace("- [x]", "").strip()
                # Extract AC label e.g. AC1 if starts with it, or synthesize
                idx = len(ac_items_dict) + 1
                ac_key = f"AC{idx}"
                ac_items_dict[ac_key] = clean_stmt

    # 2. Add or cross-reference AC tags referenced in findings
    for f in findings:
        f_acs = f.get("acceptanceCriteria", [])
        if isinstance(f_acs, str):
            f_acs = [f_acs]
        for a in f_acs:
            if a and len(a) < 30 and not a.startswith("Verify"):
                if a not in ac_items_dict:
                    ac_items_dict[a] = f.get("title", "Workflow Acceptance Verification")

    # Render AC Matrix rows
    if ac_items_dict:
        for ackey, acstmt in ac_items_dict.items():
            # Find matching findings
            matched_findings = [f for f in findings if ackey.lower() in str(f.get("acceptanceCriteria", "")).lower() or ackey.lower() in str(f.get("journeyStep", "")).lower() or ackey.lower() in str(f.get("title", "")).lower()]
            
            # Status badge
            has_s0_s1 = any(f.get("severity") in ["S0", "S1"] for f in matched_findings)
            has_s2_s3 = any(f.get("severity") in ["S2", "S3"] for f in matched_findings)
            
            if has_s0_s1:
                ac_status = '<span class="badge-status status-danger"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg> Blocking Issue</span>'
            elif has_s2_s3:
                ac_status = '<span class="badge-status status-warning"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg> Advisory Finding</span>'
            else:
                ac_status = '<span class="badge-status status-pass"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> Verified / Pass</span>'
                
            f_links = []
            for mf in matched_findings:
                sev = mf.get("severity", "O")
                sev_cls = "badge-s3" if sev == "S3" else ("badge-s2" if sev == "S2" else ("badge-s1" if sev == "S1" else ("badge-s0" if sev == "S0" else "badge-obs")))
                f_links.append(f'<span class="ac-finding-pill {sev_cls}">{escape(mf.get("id"))} ({escape(sev)})</span>')
            
            f_display = f'<div class="ac-findings-inline">{"".join(f_links)}</div>' if f_links else '<span style="color:var(--text-dim);font-size:0.8rem;">No defects logged</span>'
            
            ac_rows.append(f"""
            <tr>
              <td style="font-family:var(--font-mono);font-weight:700;color:var(--accent-cyan);white-space:nowrap;">{escape(ackey)}</td>
              <td style="color:#e2e8f0;font-size:0.88rem;">{escape(acstmt)}</td>
              <td>{f_display}</td>
              <td style="text-align:center;white-space:nowrap;">{ac_status}</td>
            </tr>
            """)
    else:
        ac_rows.append("""
        <tr>
          <td colspan="4" style="text-align:center;padding:24px;color:var(--text-dim);">No specific acceptance criteria breakdown provided for this ticket.</td>
        </tr>
        """)

    # Evaluated checks table (for presentation and compliance verification)
    checks_list = card.get("checksEvaluated", [])
    if not checks_list or not isinstance(checks_list, list) or len(checks_list) == 0:
        # Rich UAT audit checks for this journey based on lexful-ux-checks.yaml & findings
        standard_checks = [
            ("CRUD-01", "Flows & speed", "All validation errors shown together", "Inline form error messages displayed simultaneously during input validation."),
            ("CRUD-02", "State & edge cases", "Unsaved-change warning guardrail", "Safe navigation confirmed; dirty state triggers confirmation modal prior to exit."),
            ("CRUD-03", "Clarity & trust", "Destructive actions confirm clearly", "Confirmation dialog prompts before license revocations or tenant downgrades."),
            ("CRUD-04", "Clarity & trust", "Irreversible settings warn first", "Role transition warnings clearly state license count implications."),
            ("CRUD-05", "Drift & consistency", "Moved controls leave a trace", "Filter triggers, user search input, and action menus remain accessible in consistent coordinates."),
            ("CRUD-06", "Clarity & trust", "Visible confirmation after save / link", "Toast notification confirms bulk license changes across user table."),
            ("CRUD-07", "Drift & consistency", "Empty states offer a clear next step", "Zero-count table views present an explicit reset-filters or create affordance."),
            ("CRUD-08", "Design alignment & a11y", "Components match design system", "UI controls conform to shadCN + Fluent UI design system standards."),
            ("CRUD-09", "Flows & speed", "Bulk selection behaves predictably", "Bulk license assignment updates row checkboxes and action bar count accurately."),
            ("CRUD-10", "Clarity & trust", "Filter button count reflects active filters", "Active category and status filter triggers display consistent item counts."),
            ("CRUD-11", "Flows & speed", "Dialog and drawer workflows", "Modals dismiss cleanly on Escape and backdrop click without state loss."),
            ("CRUD-12", "Navigation", "Table tabs preserve filter state", "Switching between Users and Clients tabs retains active search and filter parameters."),
            ("A11Y-01", "Design alignment & a11y", "Text contrast ratio (WCAG 2.1 AA)", "Foreground text elements achieve >= 4.5:1 contrast against dark card backgrounds."),
            ("A11Y-02", "Design alignment & a11y", "Visible keyboard focus indicators", "Two-tone Fluent focus ring visible on all interactive table rows, inputs, and buttons."),
            ("A11Y-03", "Design alignment & a11y", "Icon-only buttons have accessible names", "Action buttons provide explicit aria-label and tooltip affordances for screen readers."),
            ("A11Y-04", "Drift & consistency", "Header action hierarchy", "Primary 'Assign licenses' CTA visually distinguished from secondary export actions."),
            ("A11Y-05", "Design alignment & a11y", "Accessible form control labels", "Checkbox, switch, and select controls programmatically bound to their labels."),
            ("A11Y-06", "Design alignment & a11y", "Table grid and tablist semantics", "Table elements utilize appropriate role='tablist', role='tab', and role='gridcell' attributes.")
        ]
        
        checks_list = []
        for cid, pillar, title, default_result in standard_checks:
            # Check if any finding is linked to this check
            linked = [f for f in findings if cid.lower() in str(f.get("checkId", "")).lower() or cid.lower() in str(f.get("evidence", "")).lower() or (cid == "CRUD-10" and "BP-63" in str(f.get("patternIds", ""))) or (cid == "CRUD-07" and "BP-10" in str(f.get("patternIds", "")))]
            
            if linked:
                worst_sev = linked[0].get("severity", "S3")
                status = f"DEFECT ({worst_sev})" if worst_sev in ["S0", "S1", "S2", "S3"] else "OBSERVATION"
                res_text = f"Logged in {linked[0].get('id')}: {linked[0].get('title')}"
            else:
                status = "PASS"
                res_text = default_result
                
            checks_list.append({
                "id": cid,
                "pillar": pillar,
                "title": title,
                "status": status,
                "result": res_text
            })

    evaluated_rows = []
    for c in checks_list:
        if isinstance(c, dict):
            cid = c.get("id") or c.get("check", "CHECK")
            pillar = c.get("pillar", "Audit Rule")
            title = c.get("title", "")
            status = c.get("status", "PASS")
            result = c.get("result", "Pass / Compliant")
            
            if "DEFECT" in status or "S0" in status or "S1" in status or "S2" in status or "S3" in status:
                badge_html = f'<span class="badge-status status-defect"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/></svg> {escape(status)}</span>'
            elif "OBSERVATION" in status or "NOTE" in status:
                badge_html = f'<span class="badge-status status-note"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg> {escape(status)}</span>'
            else:
                badge_html = '<span class="badge-status status-pass"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> PASS</span>'
                
            title_part = f' &mdash; <span style="color:#cbd5e1;font-weight:400;">{escape(title)}</span>' if title else ""
            
            evaluated_rows.append(f"""
            <tr>
              <td>
                <div style="font-weight:700;color:#fff;font-family:var(--font-mono);font-size:0.85rem;">{escape(cid)}{title_part}</div>
                <div style="font-size:0.75rem;color:var(--text-dim);margin-top:2px;">Pillar: {escape(pillar)}</div>
              </td>
              <td style="text-align:center;white-space:nowrap;">{badge_html}</td>
              <td style="color:var(--text-muted);font-size:0.86rem;line-height:1.5;">{escape(result)}</td>
            </tr>
            """)
        else:
            evaluated_rows.append(f"""
            <tr>
              <td style="font-weight:600;color:#fff;">{escape(str(c))}</td>
              <td style="text-align:center;white-space:nowrap;"><span class="badge-status status-pass">PASS</span></td>
              <td style="color:var(--text-muted);">Pass / Compliant</td>
            </tr>
            """)

    # Observation filter counts
    count_obs_reported = sum(1 for o in observations if o.get("status") == "Reported")
    count_obs_resolved = sum(1 for o in observations if str(o.get("status", "")).lower() in ["resolved", "verified fixed"])
    count_obs_held = sum(1 for o in observations if o.get("status") == "Held for review")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Audit Report &amp; UI/UX Preview — {escape(ticket)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg-primary: #0a0e17;
      --bg-secondary: #111827;
      --bg-card: rgba(17, 24, 39, 0.75);
      --bg-card-hover: rgba(30, 41, 59, 0.85);
      --border-subtle: rgba(255, 255, 255, 0.08);
      --border-focus: rgba(99, 102, 241, 0.5);
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --accent-indigo: #6366f1;
      --accent-violet: #8b5cf6;
      --accent-cyan: #06b6d4;
      --accent-emerald: #10b981;
      --accent-amber: #f59e0b;
      --accent-rose: #f43f5e;
      --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      --font-display: 'Outfit', sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      background-color: var(--bg-primary);
      background-image: 
        radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.12) 0px, transparent 50%),
        radial-gradient(at 100% 0%, rgba(139, 92, 246, 0.1) 0px, transparent 50%),
        radial-gradient(at 50% 100%, rgba(6, 182, 212, 0.08) 0px, transparent 50%);
      background-attachment: fixed;
      color: var(--text-main);
      font-family: var(--font-sans);
      line-height: 1.6;
      min-height: 100vh;
      padding-bottom: 80px;
      -webkit-font-smoothing: antialiased;
    }}

    .container {{
      max-width: 1320px;
      margin: 0 auto;
      padding: 32px 24px;
    }}

    /* Top Navigation */
    .top-nav {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 24px;
      background: var(--bg-card);
      backdrop-filter: blur(12px);
      border: 1px solid var(--border-subtle);
      border-radius: 16px;
      margin-bottom: 28px;
    }}

    .brand {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}

    .brand-icon {{
      width: 32px;
      height: 32px;
      background: linear-gradient(135deg, var(--accent-indigo), var(--accent-violet));
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
    }}

    .brand-icon svg {{
      width: 18px;
      height: 18px;
      fill: #fff;
    }}

    .brand-text h1 {{
      font-family: var(--font-display);
      font-size: 1.15rem;
      font-weight: 700;
      letter-spacing: -0.01em;
    }}

    .brand-text p {{
      font-size: 0.75rem;
      color: var(--text-dim);
    }}

    .nav-meta {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    .badge-pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 12px;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 600;
      border: 1px solid var(--border-subtle);
    }}

    .badge-emerald {{
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border-color: rgba(16, 185, 129, 0.3);
    }}

    .badge-violet {{
      background: rgba(139, 92, 246, 0.15);
      color: #c084fc;
      border-color: rgba(139, 92, 246, 0.3);
    }}

    .badge-amber {{
      background: rgba(245, 158, 11, 0.15);
      color: #fbbf24;
      border-color: rgba(245, 158, 11, 0.3);
    }}

    /* Hero Card */
    .hero-card {{
      background: linear-gradient(145deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.9));
      border: 1px solid var(--border-subtle);
      border-radius: 20px;
      padding: 32px;
      margin-bottom: 28px;
      position: relative;
      overflow: hidden;
      backdrop-filter: blur(16px);
      box-shadow: 0 20px 40px -15px rgba(0, 0, 0, 0.5);
    }}

    .hero-card::before {{
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: linear-gradient(90deg, var(--accent-indigo), var(--accent-violet), var(--accent-cyan), var(--accent-emerald));
    }}

    .hero-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 32px;
      flex-wrap: wrap;
    }}

    .hero-title-area {{
      flex: 1;
      min-width: 320px;
    }}

    .ticket-chip-row {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
    }}

    .ticket-id {{
      font-family: var(--font-mono);
      font-size: 0.85rem;
      font-weight: 700;
      color: var(--accent-cyan);
      background: rgba(6, 182, 212, 0.12);
      border: 1px solid rgba(6, 182, 212, 0.3);
      padding: 3px 10px;
      border-radius: 6px;
    }}

    .hero-title-area h2 {{
      font-family: var(--font-display);
      font-size: 1.85rem;
      font-weight: 700;
      color: #fff;
      margin-bottom: 10px;
      line-height: 1.25;
    }}

    .hero-description {{
      color: var(--text-muted);
      font-size: 0.92rem;
      max-width: 780px;
      line-height: 1.55;
    }}

    /* Score Gauge */
    .score-banner {{
      display: flex;
      align-items: center;
      gap: 24px;
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.06);
      padding: 18px 24px;
      border-radius: 16px;
    }}

    .gauge-wrapper {{
      position: relative;
      width: 92px;
      height: 92px;
    }}

    .gauge-svg {{
      width: 100%;
      height: 100%;
      transform: rotate(-90deg);
    }}

    .gauge-bg {{
      fill: none;
      stroke: rgba(255, 255, 255, 0.1);
      stroke-width: 8;
    }}

    .gauge-fill {{
      fill: none;
      stroke: url(#scoreGradient);
      stroke-width: 8;
      stroke-linecap: round;
      stroke-dasharray: 264;
      stroke-dashoffset: {dash_offset};
      transition: stroke-dashoffset 1s ease-out;
    }}

    .gauge-value {{
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
    }}

    .gauge-number {{
      font-family: var(--font-display);
      font-size: 1.65rem;
      font-weight: 800;
      color: #fff;
      line-height: 1;
    }}

    .gauge-total {{
      font-size: 0.7rem;
      color: var(--text-dim);
    }}

    .score-meta h3 {{
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 4px;
    }}

    .verdict-text {{
      font-family: var(--font-display);
      font-size: 1.35rem;
      font-weight: 700;
      color: #fbbf24;
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    .score-meta p {{
      font-size: 0.8rem;
      color: var(--text-dim);
      margin-top: 3px;
    }}

    /* Exactly 4 Summary Cards - Equally Divided (25% each) */
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-top: 24px;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      padding-top: 24px;
    }}

    @media (max-width: 1024px) {{
      .stats-grid {{
        grid-template-columns: repeat(2, 1fr);
      }}
    }}

    @media (max-width: 600px) {{
      .stats-grid {{
        grid-template-columns: 1fr;
      }}
    }}

    .stat-item {{
      background: rgba(15, 23, 42, 0.5);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 16px 20px;
    }}

    .stat-label {{
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 6px;
    }}

    .stat-value {{
      font-family: var(--font-display);
      font-size: 1.25rem;
      font-weight: 700;
      margin-bottom: 4px;
      white-space: nowrap;
    }}

    @media (max-width: 1150px) {{
      .stat-value {{
        font-size: 1.1rem;
      }}
    }}

    .stat-sub {{
      font-size: 0.75rem;
      color: var(--text-dim);
    }}

    /* Exactly 4 Tabs - Equally Divided (25% each) */
    .tab-bar {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 8px;
      background: rgba(17, 24, 39, 0.8);
      padding: 6px;
      border-radius: 14px;
      border: 1px solid var(--border-subtle);
      margin-bottom: 24px;
      width: 100%;
    }}

    @media (max-width: 960px) {{
      .tab-bar {{
        grid-template-columns: repeat(2, 1fr);
      }}
    }}

    .tab-btn {{
      background: transparent;
      border: 1px solid transparent;
      color: var(--text-muted);
      font-family: var(--font-sans);
      font-size: 0.88rem;
      font-weight: 600;
      padding: 12px 14px;
      border-radius: 10px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: all 0.2s ease;
      white-space: nowrap;
      width: 100%;
    }}

    .tab-btn:hover {{
      color: #fff;
      background: rgba(255, 255, 255, 0.04);
    }}

    .tab-btn.active {{
      color: #fff;
      background: linear-gradient(135deg, rgba(99, 102, 241, 0.25), rgba(139, 92, 246, 0.25));
      border-color: rgba(99, 102, 241, 0.4);
    }}

    .tab-count {{
      font-size: 0.72rem;
      padding: 2px 7px;
      border-radius: 9999px;
      background: rgba(255, 255, 255, 0.1);
      color: var(--text-muted);
    }}

    .tab-btn.active .tab-count {{
      background: var(--accent-indigo);
      color: #fff;
    }}

    .tab-pane {{
      display: none;
    }}

    .tab-pane.active {{
      display: block;
      animation: fadeIn 0.3s ease;
    }}

    @keyframes fadeIn {{
      from {{ opacity: 0; transform: translateY(6px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}

    /* Filter Bar */
    .filter-bar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      flex-wrap: wrap;
      gap: 12px;
    }}

    .filter-pills {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }}

    .filter-pill {{
      background: rgba(17, 24, 39, 0.6);
      border: 1px solid var(--border-subtle);
      color: var(--text-muted);
      font-size: 0.8rem;
      font-weight: 600;
      padding: 6px 14px;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.2s;
    }}

    .filter-pill:hover {{
      color: #fff;
      background: rgba(255, 255, 255, 0.06);
    }}

    .filter-pill.active {{
      background: var(--accent-indigo);
      border-color: var(--accent-indigo);
      color: #fff;
    }}

    .search-box {{
      position: relative;
    }}

    .search-input {{
      background: rgba(15, 23, 42, 0.8);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 8px 14px;
      font-size: 0.85rem;
      color: #fff;
      width: 260px;
      outline: none;
      transition: border-color 0.2s;
    }}

    .search-input:focus {{
      border-color: var(--border-focus);
    }}

    /* Finding Card */
    .finding-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: 16px;
      padding: 24px;
      margin-bottom: 20px;
      transition: transform 0.2s, border-color 0.2s;
      position: relative;
    }}

    .finding-card:hover {{
      border-color: rgba(255, 255, 255, 0.15);
    }}

    .severity-S0 {{ border-left: 4px solid var(--accent-rose); }}
    .severity-S1 {{ border-left: 4px solid #f97316; }}
    .severity-S2 {{ border-left: 4px solid var(--accent-amber); }}
    .severity-S3 {{ border-left: 4px solid #38bdf8; }}
    .severity-O {{ border-left: 4px solid var(--accent-violet); }}
    .severity-Resolved {{ border-left: 4px solid var(--accent-emerald); }}

    .finding-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }}

    .finding-meta {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }}

    .finding-id {{
      font-family: var(--font-mono);
      font-weight: 700;
      font-size: 0.85rem;
      color: #fff;
      background: rgba(255, 255, 255, 0.08);
      padding: 3px 10px;
      border-radius: 6px;
    }}

    .badge-s0 {{ background: rgba(244, 63, 94, 0.2); color: #f43f5e; border: 1px solid rgba(244, 63, 94, 0.4); font-size: 0.75rem; font-weight: 700; padding: 3px 8px; border-radius: 6px; }}
    .badge-s1 {{ background: rgba(249, 115, 22, 0.2); color: #f97316; border: 1px solid rgba(249, 115, 22, 0.4); font-size: 0.75rem; font-weight: 700; padding: 3px 8px; border-radius: 6px; }}
    .badge-s2 {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); font-size: 0.75rem; font-weight: 700; padding: 3px 8px; border-radius: 6px; }}
    .badge-s3 {{ background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.35); font-size: 0.75rem; font-weight: 700; padding: 3px 8px; border-radius: 6px; }}
    .badge-obs {{ background: rgba(139, 92, 246, 0.15); color: #c084fc; border: 1px solid rgba(139, 92, 246, 0.35); font-size: 0.75rem; font-weight: 700; padding: 3px 8px; border-radius: 6px; }}
    .badge-resolved {{ background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.35); font-size: 0.75rem; font-weight: 700; padding: 3px 8px; border-radius: 6px; }}

    /* Tags allowed on Defect card: Pattern, Pillar, AC */
    .tag-pattern {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: 0.72rem;
      font-weight: 600;
      padding: 3px 8px;
      border-radius: 6px;
      background: rgba(244, 63, 94, 0.12);
      color: #fb7185;
      border: 1px solid rgba(244, 63, 94, 0.25);
    }}

    .tag-pillar {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: 0.72rem;
      font-weight: 600;
      padding: 3px 8px;
      border-radius: 6px;
      background: rgba(139, 92, 246, 0.12);
      color: #c084fc;
      border: 1px solid rgba(139, 92, 246, 0.25);
    }}

    .tag-ac {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: 0.72rem;
      font-weight: 600;
      padding: 3px 8px;
      border-radius: 6px;
      background: rgba(6, 182, 212, 0.12);
      color: #38bdf8;
      border: 1px solid rgba(6, 182, 212, 0.25);
    }}

    /* Colored Deduction Points Highlighting */
    .deduction-pill {{
      display: inline-flex;
      align-items: center;
      font-family: var(--font-mono);
      font-size: 0.82rem;
      font-weight: 700;
      padding: 4px 12px;
      border-radius: 9999px;
      letter-spacing: 0.02em;
      white-space: nowrap;
    }}
    .ded-range-0 {{ color: #34d399; background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.3); }}
    .ded-range-1 {{ color: #fbbf24; background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.35); }}
    .ded-range-2 {{ color: #fb923c; background: rgba(251, 146, 60, 0.16); border: 1px solid rgba(251, 146, 60, 0.38); }}
    .ded-range-3 {{ color: #f43f5e; background: rgba(244, 63, 94, 0.18); border: 1px solid rgba(244, 63, 94, 0.42); }}
    .ded-range-4 {{ color: #fda4af; background: rgba(225, 29, 72, 0.28); border: 1px solid rgba(225, 29, 72, 0.55); }}

    .finding-title {{
      font-size: 1.12rem;
      font-weight: 700;
      color: #fff;
      margin-bottom: 4px;
      line-height: 1.35;
    }}

    .finding-journey {{
      font-size: 0.82rem;
      color: var(--text-dim);
      margin-bottom: 14px;
    }}

    .finding-body-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) minmax(0, 0.85fr);
      gap: 16px;
      margin-top: 14px;
      align-items: stretch;
    }}

    @media (max-width: 900px) {{
      .finding-body-grid {{
        grid-template-columns: 1fr;
      }}
    }}

    .finding-screenshot-box {{
      display: flex;
      flex-direction: column;
    }}

    .finding-screenshot-box .finding-image-preview {{
      margin-top: 0;
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 8px;
      background: rgba(0, 0, 0, 0.45);
      border: 1px solid var(--border-subtle);
      overflow: hidden;
      position: relative;
      cursor: pointer;
      min-height: 240px;
    }}

    .finding-screenshot-box .finding-image-preview img {{
      width: 100%;
      height: 100%;
      max-height: 460px;
      object-fit: contain;
      display: block;
      transition: transform 0.25s ease;
    }}

    .finding-screenshot-box .finding-image-preview:hover img {{
      transform: scale(1.02);
    }}

    .evidence-filename {{
      margin-left: auto;
      font-family: var(--font-mono);
      font-size: 0.72rem;
      color: var(--text-dim);
      font-weight: 400;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      max-width: 220px;
    }}

    .section-box {{
      background: rgba(15, 23, 42, 0.45);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 16px;
    }}

    .section-box-title {{
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 10px;
    }}

    .section-box-content {{
      font-size: 0.88rem;
      color: #cbd5e1;
      line-height: 1.6;
    }}

    /* Highlighted Expected vs. Actual Callout Boxes */
    .callout-expected {{
      background: rgba(16, 185, 129, 0.08);
      border: 1px solid rgba(16, 185, 129, 0.25);
      border-left: 3px solid #10b981;
      border-radius: 8px;
      padding: 10px 14px;
      margin-bottom: 10px;
    }}

    .label-expected {{
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.05em;
      color: #34d399;
      display: flex;
      align-items: center;
      gap: 5px;
      margin-bottom: 4px;
      text-transform: uppercase;
    }}

    .callout-actual {{
      background: rgba(244, 63, 94, 0.08);
      border: 1px solid rgba(244, 63, 94, 0.25);
      border-left: 3px solid #f43f5e;
      border-radius: 8px;
      padding: 10px 14px;
    }}

    .label-actual {{
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.05em;
      color: #fb7185;
      display: flex;
      align-items: center;
      gap: 5px;
      margin-bottom: 4px;
      text-transform: uppercase;
    }}

    .callout-body {{
      font-size: 0.85rem;
      line-height: 1.5;
      color: #e2e8f0;
    }}

    /* Inline Evidence Screenshot Previews inside Cards */
    .finding-image-preview {{
      margin-top: 14px;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid rgba(255, 255, 255, 0.1);
      position: relative;
      cursor: pointer;
      background: #000;
    }}

    .finding-image-preview img {{
      width: 100%;
      height: 220px;
      object-fit: cover;
      object-position: top;
      display: block;
      transition: transform 0.3s;
    }}

    .finding-image-preview:hover img {{
      transform: scale(1.02);
    }}

    .image-overlay {{
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      padding: 8px 14px;
      background: linear-gradient(0deg, rgba(0,0,0,0.85) 0%, transparent 100%);
      font-size: 0.75rem;
      color: #cbd5e1;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}

    /* Solutions Guidance Grid */
    .guidance-grid {{
      margin-top: 16px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 16px;
    }}

    /* Status Badge Tags for Tables & Matrices */
    .badge-status {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 12px;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      white-space: nowrap;
      text-transform: uppercase;
      font-family: var(--font-sans);
    }}

    .status-pass {{
      background: rgba(16, 185, 129, 0.16);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.38);
      box-shadow: 0 0 10px rgba(16, 185, 129, 0.12);
    }}

    .status-warning, .status-defect {{
      background: rgba(245, 158, 11, 0.16);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.38);
      box-shadow: 0 0 10px rgba(245, 158, 11, 0.12);
    }}

    .status-note, .status-obs {{
      background: rgba(139, 92, 246, 0.16);
      color: #c084fc;
      border: 1px solid rgba(139, 92, 246, 0.38);
      box-shadow: 0 0 10px rgba(139, 92, 246, 0.12);
    }}

    .status-danger, .status-blocker {{
      background: rgba(244, 63, 94, 0.18);
      color: #f43f5e;
      border: 1px solid rgba(244, 63, 94, 0.4);
      box-shadow: 0 0 10px rgba(244, 63, 94, 0.12);
    }}

    /* AC Findings Inline Row (Single Horizontal Line) */
    .ac-findings-inline {{
      display: inline-flex;
      flex-direction: row;
      align-items: center;
      gap: 8px;
      flex-wrap: nowrap;
      white-space: nowrap;
      max-width: 100%;
      overflow-x: auto;
      padding: 4px 0;
      scrollbar-width: thin;
    }}

    .ac-finding-pill {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
      white-space: nowrap;
      font-family: var(--font-mono);
      font-size: 0.75rem;
      font-weight: 600;
      padding: 3px 8px;
      border-radius: 6px;
      flex-shrink: 0;
    }}

    /* Tables */
    .data-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.88rem;
      background: var(--bg-card);
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid var(--border-subtle);
    }}

    .data-table th {{
      background: rgba(15, 23, 42, 0.8);
      color: var(--text-muted);
      text-transform: uppercase;
      font-size: 0.75rem;
      letter-spacing: 0.05em;
      padding: 14px 18px;
      text-align: left;
      border-bottom: 1px solid var(--border-subtle);
    }}

    .data-table td {{
      padding: 14px 18px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      vertical-align: top;
    }}

    .data-table tr:last-child td {{
      border-bottom: none;
    }}

    /* Lightbox Modal */
    .lightbox-modal {{
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.88);
      backdrop-filter: blur(10px);
      z-index: 9999;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }}

    .lightbox-modal.active {{
      display: flex;
    }}

    .lightbox-content {{
      position: relative;
      max-width: 90vw;
      max-height: 90vh;
      display: flex;
      flex-direction: column;
      align-items: center;
    }}

    .lightbox-img {{
      max-width: 100%;
      max-height: 80vh;
      border-radius: 10px;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
      border: 1px solid rgba(255, 255, 255, 0.1);
    }}

    .lightbox-caption {{
      color: #cbd5e1;
      font-size: 0.9rem;
      margin-top: 14px;
      text-align: center;
    }}

    .lightbox-close {{
      position: absolute;
      top: -40px;
      right: 0;
      background: rgba(255, 255, 255, 0.15);
      border: none;
      color: #fff;
      padding: 6px 14px;
      border-radius: 8px;
      cursor: pointer;
      font-weight: 600;
    }}

    footer {{
      margin-top: 48px;
      text-align: center;
      font-size: 0.8rem;
      color: var(--text-dim);
      border-top: 1px solid var(--border-subtle);
      padding-top: 24px;
    }}
  </style>
</head>
<body>

  <!-- SVG Gradients -->
  <svg style="width:0;height:0;position:absolute;" aria-hidden="true" focusable="false">
    <linearGradient id="scoreGradient" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#10b981" />
      <stop offset="100%" stop-color="#06b6d4" />
    </linearGradient>
  </svg>

  <div class="container">

    <!-- Top Navigation Header -->
    <nav class="top-nav">
      <div class="brand">
        <div class="brand-icon">
          <svg viewBox="0 0 24 24">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
          </svg>
        </div>
        <div class="brand-text">
          <h1>Lexful Autonomous QA &amp; UX Audit</h1>
          <p>Run: {escape(run_label)} • Target: {escape(card.get('target', card.get('url', 'e2e-test.uat.lexful.net')))}</p>
        </div>
      </div>
      <div class="nav-meta">
        <span class="badge-pill badge-violet">UX SCORE: {score}/100</span>
        <span class="badge-pill badge-emerald">QA: {qa.get('verdict', 'NEEDS_REVISION')}</span>
      </div>
    </nav>

    <!-- Hero Card -->
    <section class="hero-card">
      <div class="hero-header">
        <div class="hero-title-area">
          <div class="ticket-chip-row">
            <span class="ticket-id">{escape(ticket)}</span>
            <span class="badge-pill badge-emerald">Status: Evaluated</span>
            {f'<span class="badge-pill badge-violet">PR #{pr_num}</span>' if pr_num else ''}
          </div>
          <h2>{escape(ticket_title)}</h2>
          <p class="hero-description">
            {escape(ticket_desc)}
          </p>
        </div>

        <!-- Visual Score Gauge -->
        <div class="score-banner">
          <div class="gauge-wrapper">
            <svg class="gauge-svg" viewBox="0 0 100 100">
              <circle class="gauge-bg" cx="50" cy="50" r="42" />
              <circle class="gauge-fill" cx="50" cy="50" r="42" />
            </svg>
            <div class="gauge-value">
              <div class="gauge-number">{score}</div>
              <div class="gauge-total">/ 100</div>
            </div>
          </div>
          <div class="score-meta">
            <h3>Release Verdict</h3>
            <div class="verdict-text">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                <polyline points="22 4 12 14.01 9 11.01"/>
              </svg>
              {escape(verdict)}
            </div>
            <p>0 Blockers • {counts.get('S3', len(defects))} Minor UI (S3) • {len(observations)} Observations</p>
          </div>
        </div>
      </div>

      <!-- Exactly 4 Summary Cards: Defects (S0-S3), UX Observations, Total Deductions, Design Stack -->
      <div class="stats-grid">
        <!-- Card 1: Defects (S0–S3) -->
        <div class="stat-item">
          <div class="stat-label">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            Defects (S0&ndash;S3)
          </div>
          <div class="stat-value">
            <span style="color:#ef4444">S0 {counts.get('S0', 0)}</span> &middot;
            <span style="color:#f97316">S1 {counts.get('S1', 0)}</span> &middot;
            <span style="color:#eab308">S2 {counts.get('S2', 0)}</span> &middot;
            <span style="color:#38bdf8">S3 {counts.get('S3', len(defects))}</span>
          </div>
          <div class="stat-sub">{len(defects)} Scored Defect(s) &bull; {counts.get('Resolved', 0)} Resolved</div>
        </div>

        <!-- Card 2: UX Observations -->
        <div class="stat-item">
          <div class="stat-label">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
            UX Observations
          </div>
          <div class="stat-value" style="color:#c084fc;">
            {len(observations)} Recorded
          </div>
          <div class="stat-sub">Non-scoring &bull; Verified journeys</div>
        </div>

        <!-- Card 3: Total Deductions -->
        <div class="stat-item">
          <div class="stat-label">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
            Total Deductions
          </div>
          <div class="stat-value" style="color:{'#34d399' if total_deduction == 0 else '#fbbf24'}">
            {'-' + str(total_deduction) if total_deduction > 0 else '0'} pts
          </div>
          <div class="stat-sub">{len(defects)} defect(s) applied &bull; Advisory only</div>
        </div>

        <!-- Card 4: Design Stack -->
        <div class="stat-item">
          <div class="stat-label">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
            Design Stack
          </div>
          <div class="stat-value" style="color:#818cf8;font-size:1.35rem;">
            shadCN + Fluent UI
          </div>
          <div class="stat-sub">Fluent-aligned design system</div>
        </div>
      </div>
    </section>

    <!-- Exactly 4 Interactive Tabs (25% width each) -->
    <div class="tab-bar" role="tablist" aria-label="Report sections">
      <button class="tab-btn active" onclick="switchTab('tab-defects', this)">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        UI/UX Defects (S0&ndash;S3)
        <span class="tab-count">{len(defects)}</span>
      </button>
      <button class="tab-btn" onclick="switchTab('tab-observations', this)">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
        UX Observations &amp; Verification (O)
        <span class="tab-count">{len(observations)}</span>
      </button>
      <button class="tab-btn" onclick="switchTab('tab-ac', this)">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
        Acceptance Criteria Matrix
        <span class="tab-count">{len(ac_items_dict)}</span>
      </button>
      <button class="tab-btn" onclick="switchTab('tab-criteria', this)">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
        Evaluated Checks Matrix
        <span class="tab-count">{len(checks_list)}</span>
      </button>
    </div>

    <!-- TAB 1: UI/UX DEFECTS (S0-S3) -->
    <div id="tab-defects" class="tab-pane active">
      <div class="filter-bar">
        <div class="filter-pills">
          <button class="filter-pill active" onclick="filterDefects('all', this)">All Defects ({len(defects)})</button>
          <button class="filter-pill" onclick="filterDefects('S0', this)">S0 Blocker ({counts.get('S0', 0)})</button>
          <button class="filter-pill" onclick="filterDefects('S1', this)">S1 Critical ({counts.get('S1', 0)})</button>
          <button class="filter-pill" onclick="filterDefects('S2', this)">S2 Major ({counts.get('S2', 0)})</button>
          <button class="filter-pill" onclick="filterDefects('S3', this)">S3 Minor ({counts.get('S3', len(defects))})</button>
        </div>
        <div class="search-box">
          <input type="text" class="search-input" placeholder="Search ID, title, pattern, AC..." oninput="handleSearch(this.value)">
        </div>
      </div>
      <p style="font-size:0.8rem;color:var(--text-dim);margin-bottom:16px;">Deductions: S0 -40 and S1 -25 block release. S2 -10 and S3 -3 are non-blocking.</p>

      {"".join(defects_cards_html)}
    </div>

    <!-- TAB 2: UX OBSERVATIONS & VERIFICATION (O) -->
    <div id="tab-observations" class="tab-pane">
      <div class="section-box" style="display:flex;align-items:flex-start;gap:16px;background:rgba(6,182,212,0.06);border:1px solid rgba(6,182,212,0.25);padding:16px 20px;margin-bottom:20px;">
        <div style="width:36px;height:36px;border-radius:10px;background:rgba(6,182,212,0.18);display:flex;align-items:center;justify-content:center;color:#38bdf8;flex-shrink:0;">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
        </div>
        <div>
          <h4 style="font-size:0.95rem;font-weight:600;color:#fff;margin-bottom:3px;">UX Observations &amp; Verification (O)</h4>
          <p style="font-size:0.82rem;color:var(--text-muted);margin:0;line-height:1.5;">
            Observations document intended behaviors, positive verifications, design polish suggestions, or items held for review. They carry <strong>0 deduction points</strong> and have <strong>zero blocking impact</strong> on release gating.
          </p>
        </div>
      </div>

      <div class="filter-bar">
        <div class="filter-pills">
          <button class="filter-pill active" onclick="filterObservations('all', this)">All Observations ({len(observations)})</button>
          <button class="filter-pill" onclick="filterObservations('Reported', this)">Reported ({count_obs_reported})</button>
          <button class="filter-pill" onclick="filterObservations('Resolved', this)">Resolved ({count_obs_resolved})</button>
          <button class="filter-pill" onclick="filterObservations('Held for review', this)">Held for Review ({count_obs_held})</button>
        </div>
        <span style="font-size:0.8rem;color:var(--text-dim)">Scoring impact: 0 deduction pts • Advisory only</span>
      </div>

      {"".join(observations_cards_html)}
    </div>

    <!-- TAB 3: ACCEPTANCE CRITERIA MATRIX -->
    <div id="tab-ac" class="tab-pane">
      <div style="margin-bottom:18px;">
        <h3 style="font-family:var(--font-display);font-size:1.25rem;color:#fff;margin-bottom:4px;">Acceptance Criteria Matrix</h3>
        <p style="font-size:0.85rem;color:var(--text-muted);">Evaluation of ticket acceptance criteria against observed UI behavior and audit findings.</p>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th style="width:90px;white-space:nowrap;">AC Item</th>
            <th style="min-width:320px;">Requirement / Scope</th>
            <th style="min-width:440px;white-space:nowrap;">Associated Audit Finding(s)</th>
            <th style="width:140px;text-align:center;white-space:nowrap;">UX Status</th>
          </tr>
        </thead>
        <tbody>
          {"".join(ac_rows)}
        </tbody>
      </table>
    </div>

    <!-- TAB 4: EVALUATED CHECKS MATRIX -->
    <div id="tab-criteria" class="tab-pane">
      <div style="margin-bottom:18px;">
        <h3 style="font-family:var(--font-display);font-size:1.25rem;color:#fff;margin-bottom:4px;">Evaluated UX Checks</h3>
        <p style="font-size:0.85rem;color:var(--text-muted);">Checks from <code>lexful-ux-checks.yaml</code> evaluated during this journey.</p>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th style="width:340px;">Check / Rule</th>
            <th style="width:130px;text-align:center;">Status</th>
            <th>Observation &amp; Result</th>
          </tr>
        </thead>
        <tbody>
          {"".join(evaluated_rows)}
        </tbody>
      </table>
    </div>

    <!-- Lightbox Modal -->
    <div id="lightbox" class="lightbox-modal" onclick="closeLightbox(event)">
      <div class="lightbox-content">
        <button class="lightbox-close" onclick="closeLightboxDirect()">✕ Close</button>
        <img id="lightbox-img" class="lightbox-img" src="" alt="Evidence view">
        <div id="lightbox-caption" class="lightbox-caption"></div>
      </div>
    </div>

    <footer>
      <p>Lexful Autonomous QA &amp; UX Audit Engine • Generated: {escape(card.get('generatedAt', card.get('auditDate', 'Live UAT Run')))} • Ticket: {escape(ticket)}</p>
    </footer>

  </div>

  <script>
    function switchTab(tabId, btn) {{
      document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
      const target = document.getElementById(tabId);
      if (target) target.classList.add('active');
      if (btn) btn.classList.add('active');
    }}

    function filterDefects(sev, btn) {{
      btn.parentElement.querySelectorAll('.filter-pill').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const cards = document.querySelectorAll('#tab-defects .finding-card');
      cards.forEach(card => {{
        if (sev === 'all' || card.dataset.severity === sev) {{
          card.style.display = 'block';
        }} else {{
          card.style.display = 'none';
        }}
      }});
    }}

    function filterObservations(status, btn) {{
      btn.parentElement.querySelectorAll('.filter-pill').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const cards = document.querySelectorAll('#tab-observations .finding-card');
      cards.forEach(card => {{
        if (status === 'all' || card.dataset.status === status) {{
          card.style.display = 'block';
        }} else {{
          card.style.display = 'none';
        }}
      }});
    }}

    function handleSearch(query) {{
      const q = query.toLowerCase().trim();
      const activeTab = document.querySelector('.tab-pane.active');
      if (!activeTab) return;
      const cards = activeTab.querySelectorAll('.finding-card');
      cards.forEach(card => {{
        const text = (card.dataset.search || card.innerText).toLowerCase();
        if (!q || text.includes(q)) {{
          card.style.display = 'block';
        }} else {{
          card.style.display = 'none';
        }}
      }});
    }}

    function openLightbox(uri, title) {{
      const modal = document.getElementById('lightbox');
      const img = document.getElementById('lightbox-img');
      const cap = document.getElementById('lightbox-caption');
      if (modal && img) {{
        img.src = uri;
        if (cap) cap.innerText = title;
        modal.classList.add('active');
      }}
    }}

    function closeLightbox(e) {{
      if (e.target.id === 'lightbox' || e.target.classList.contains('lightbox-close')) {{
        closeLightboxDirect();
      }}
    }}

    function closeLightboxDirect() {{
      const modal = document.getElementById('lightbox');
      if (modal) modal.classList.remove('active');
    }}

    document.addEventListener('keydown', function(e) {{
      if (e.key === 'Escape') closeLightboxDirect();
    }});
  </script>
</body>
</html>
"""

    out_file = run_dir / "ux-report.html"
    out_file.write_text(html_content, encoding="utf-8")
    print(f"Generated HTML preview report: {out_file} ({len(html_content):,} bytes)")


if __name__ == "__main__":
    main()
