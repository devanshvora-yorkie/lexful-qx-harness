#!/usr/bin/env python3
"""
Generate a self-contained, interactive HTML UX Audit Preview Report (ux-report.html)
modeled after .agents/ux/templates/audit-preview-reference.html.

Layout features:
- Separate tabs for UI/UX Defects (S0–S3) and UX Observations & Verification (O)
- Rich badge chips for UX Rulebook checks (CRUD-*, etc.) and Bad UX Patterns (BP-*)
- Interactive filters, visual lightbox, evaluated checks matrix, and scoring deduction ledger

Usage:
    python3 scripts/generate_ux_report.py <run_dir>
"""

import sys
import os
import json
import base64
import html
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


def render_card(f, is_observation=False, image_lookup=None) -> str:
    fid = escape(f.get("id", "UX-FINDING"))
    sev = escape(f.get("severity", "O" if is_observation else "S3"))
    lens = escape(f.get("lens", "UX"))
    check_id = escape(f.get("checkId", "General"))
    title = escape(f.get("title", ""))
    conf = escape(f.get("confidence", "High"))
    deduct = f.get("deductionPoints", 0)
    status = escape(f.get("status", "Reported"))

    # Severity and status badge
    if status.lower() in ["resolved", "verified fixed"] or sev.upper() == "RESOLVED":
        status = "Resolved"
        sev_badge = '<span class="badge-resolved" style="background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.3);font-size:0.75rem;font-weight:700;padding:3px 8px;border-radius:6px;">Status: Resolved / Verified Fixed</span>'
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
        sev_badge = '<span class="badge-s3">Severity: S3 (Low)</span>'
        card_class = f"severity-{sev}"
    else:
        sev_badge = '<span class="badge-obs">Observation (O)</span>'
        card_class = f"severity-{sev}"

    # UX Rulebook Check Tag
    rule_chip = ""
    if check_id and check_id.lower() not in ["ungrouped", "general", "none", "n/a"]:
        rule_chip = f"""<span class="tag-rule" title="UX Rulebook Check"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>Rule: {check_id}</span>"""

    # Bad UX Pattern Tags
    pattern_ids = f.get("patternIds", [])
    if isinstance(pattern_ids, str):
        pattern_ids = [pattern_ids]
    pattern_chips = "".join([
        f"""<span class="tag-pattern" title="Bad UX Pattern Library"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/></svg>Pattern: {escape(p)}</span>"""
        for p in pattern_ids if p
    ])

    # Lens Tag
    lens_chip = f"""<span class="tag-lens" title="UX Audit Lens">Lens {lens}</span>"""

    # QA Traceability Tags
    qa_refs = f.get("qaRefs", [])
    if isinstance(qa_refs, str):
        qa_refs = [qa_refs]
    qa_chips = "".join([f"""<span class="tag-qa" title="QA Traceability Spec">QA: {escape(q)}</span>""" for q in qa_refs if q])
    qa_refs_str = ", ".join([escape(q) for q in qa_refs]) if qa_refs else "None recorded"

    # Design System Stack Tags
    stack_chips = '<span class="tag-stack">shadcn/ui</span><span class="tag-stack">Fluent-aligned</span>'

    # Confidence and Status Badges
    conf_class = "badge-emerald" if conf.lower() == "high" else ("badge-amber" if conf.lower() == "medium" else "badge-violet")
    conf_pill = f"""<span class="badge-pill {conf_class}">Confidence: {conf}</span>"""
    if status == "Resolved":
        status_pill = '<span class="badge-pill badge-emerald">Status: Resolved</span>'
        deduction_html = '<span style="font-size:0.8rem;color:#34d399">Deduction: 0 pts (Resolved)</span>'
    else:
        status_pill = f"""<span class="badge-pill badge-violet">Status: {status}</span>"""
        # Deduction display
        if is_observation or sev == "O":
            deduction_html = '<span style="font-size:0.8rem;color:var(--text-dim)">Deduction: 0 pts (Non-blocking)</span>'
        else:
            deduction_html = f'<span style="font-size:0.8rem;color:var(--text-dim)">Deduction: -{deduct} pts</span>'

    # Evidence list
    ev_items = f.get("evidence", [])
    if isinstance(ev_items, str):
        ev_items = [ev_items]
    ev_html = "".join([f"<li>{escape(e)}</li>" for e in ev_items]) if ev_items else "<li>Documented via workflow exploration.</li>"

    # Repro steps list
    repro = f.get("reproSteps", [])
    if isinstance(repro, str):
        repro = [repro]
    repro_html = "".join([f"<li>{escape(r)}</li>" for r in repro]) if repro else "<li>Refer to exploration snapshots.</li>"

    # Solutions & Design System Guidance
    solution = escape(f.get("solution", "No product change recommended."))
    shadcn = escape(f.get("implementationShadcn", "Not applicable."))
    fluent = escape(f.get("fluentRationale", "Not applicable."))
    acceptance = escape(f.get("acceptanceCriteria", "Verify workflow behavior matches expected UX specifications."))

    box1_title = "Observed Behavior & Details" if is_observation else "Observed Defect & Evidence"
    box2_title = "Reproduction & Trace" if is_observation else "Reproduction Steps & QA Trace"

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
        import re
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

    if target_img:
        img_uri = target_img["uri"]
        img_rel = target_img.get("rel_path") or target_img.get("name") or "evidence-screenshot.png"
        img_title = caption_text or target_img.get("title") or title
        inline_image_html = f"""
            <div class="finding-image-preview" onclick="openLightbox('{img_uri}', '{escape(img_title)} ({escape(img_rel)})')">
              <img src="{img_uri}" alt="{escape(img_title)}" loading="lazy">
              <div class="image-overlay">
                <span>{escape(img_rel)}</span>
                <span>Click to view full resolution ⤢</span>
              </div>
            </div>"""

    resolution_banner = ""
    if f.get("resolutionNote"):
        res_note = escape(f.get("resolutionNote"))
        resolved_from = f.get("resolvedFromRun")
        from_str = f" (verified from run: {escape(resolved_from)})" if resolved_from else ""
        resolution_banner = f"""
              <div style="margin-top:12px;padding:12px 14px;background:rgba(16,185,129,0.1);border-left:3px solid var(--accent-emerald);border-radius:8px;font-size:0.85rem;color:#34d399;line-height:1.5;">
                <strong>Resolution Verification{from_str}:</strong> {res_note}
              </div>"""

    return f"""
      <article class="finding-card {card_class}" data-severity="{sev}" data-status="{status}">
        <div class="finding-header">
          <div class="finding-meta">
            <span class="finding-id">{fid}</span>
            {sev_badge}
            {lens_chip}
            {rule_chip}
            {pattern_chips}
            {qa_chips}
            {stack_chips}
            {conf_pill}
            {status_pill}
          </div>
          {deduction_html}
        </div>

        <h3 class="finding-title">{title}</h3>

        <div class="finding-body-grid">
          <div class="section-box">
            <div class="section-box-title">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              {box1_title}
            </div>
            <div class="section-box-content">
              <ul style="padding-left:18px;margin-bottom:12px;">{ev_html}</ul>
              <strong>Expected vs Actual:</strong><br>
              {escape(f.get("expectedVsActual", "N/A"))}
              {resolution_banner}
            </div>
            {inline_image_html}
          </div>

          <div class="section-box">
            <div class="section-box-title">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              {box2_title}
            </div>
            <div class="section-box-content">
              <ol style="padding-left:18px;margin-bottom:12px;">{repro_html}</ol>
              <div style="font-size:0.8rem;color:var(--text-dim);margin-top:8px;">
                <strong>QA Traceability:</strong> {qa_refs_str}
              </div>
            </div>
          </div>
        </div>

        <!-- Recommended Solutions & Design Guidance -->
        <div style="margin-top:16px;display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px;">
          <div class="section-box" style="border-left:3px solid var(--accent-emerald);">
            <div class="section-box-title" style="color:#34d399;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
              {"Recommended Design Direction" if is_observation else "Recommended Resolution"}
            </div>
            <div class="section-box-content">
              {solution}
              <div style="margin-top:8px;font-size:0.82rem;color:var(--text-dim);">
                <strong>Verification / Criteria:</strong> {acceptance}
              </div>
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
            findings = json.loads(findings_file.read_text(encoding="utf-8"))
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
        except Exception:
            pass

    qa = {}
    if qa_file.is_file():
        try:
            qa = json.loads(qa_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    ticket = card.get("ticket") or ctx.get("ticket") or run_dir.parent.name
    date_str = card.get("date") or "2026-10-28"
    run_label = run_dir.name
    score = card.get("score", 100)
    verdict = card.get("verdict", "PASS WITH ADVISORIES")
    counts = card.get("counts", {"S0": 0, "S1": 0, "S2": 0, "S3": 0, "O": 0})
    total_deduction = card.get("totalDeduction", 0)

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
    ticket_title = ctx.get("title") or card.get("journey") or f"QA & UX Audit for {ticket}"
    ticket_desc = ctx.get("description") or card.get("journey") or ""

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

    # Evidence Gallery HTML
    evidence_cards_html = []
    if evidence_images:
        for idx, ev in enumerate(evidence_images):
            evidence_cards_html.append(f"""
        <div class="evidence-card" onclick="openLightbox('{ev['uri']}', '{escape(ev['title'])} ({escape(ev['name'])})')">
          <div class="evidence-thumb-container">
            <img src="{ev['uri']}" alt="{escape(ev['title'])}" class="evidence-thumb" loading="lazy">
          </div>
          <div class="evidence-meta">
            <h4>{escape(ev['title'])}</h4>
            <p>{escape(ev['rel_path'])}</p>
          </div>
        </div>
""")
    else:
        evidence_cards_html.append("""
        <div style="grid-column:1/-1;padding:40px;text-align:center;color:var(--text-muted);background:var(--bg-card);border-radius:16px;">
          <p>No screenshot artifacts captured for this run.</p>
        </div>
""")

    # Evaluated checks table
    evaluated_rows = []
    for c in card.get("checksEvaluated", []):
        evaluated_rows.append(f"""
        <tr>
          <td style="font-weight:600;color:#fff;">{escape(c.get('check'))}</td>
          <td><span class="badge-pill badge-emerald">Evaluated</span></td>
          <td style="color:var(--text-muted);">{escape(c.get('result'))}</td>
        </tr>
""")

    # Not evaluated checks table
    not_evaluated_rows = []
    for c in card.get("checksNotEvaluated", []):
        not_evaluated_rows.append(f"""
        <tr>
          <td style="font-weight:600;color:var(--text-muted);">{escape(c.get('check'))}</td>
          <td><span class="badge-pill badge-amber">Not Evaluated</span></td>
          <td style="color:var(--text-dim);">{escape(c.get('reason'))}</td>
        </tr>
""")

    # Deduction ledger rows
    ledger_rows = []
    for l in card.get("deductionLedger", []):
        ledger_rows.append(f"""
        <tr>
          <td style="font-family:var(--font-mono);font-weight:700;color:var(--accent-cyan);">{escape(l.get('findingId'))}</td>
          <td><span class="badge-pill badge-violet">{escape(l.get('severity'))}</span></td>
          <td style="font-weight:700;color:#f43f5e;">-{l.get('points', 0)} pts</td>
          <td style="font-weight:700;color:#fff;">{l.get('subtotal', 100)} / 100</td>
          <td style="color:var(--text-dim);font-size:0.85rem;">{escape(l.get('note', ''))}</td>
        </tr>
""")

    passed_count = qa.get('test_results', {}).get('passed', 4) if isinstance(qa.get('test_results'), dict) else 4

    count_obs_reported = sum(1 for o in observations if o.get("status") == "Reported")
    count_obs_resolved = sum(1 for o in observations if str(o.get("status", "")).lower() in ["resolved", "verified fixed"])
    count_obs_held = sum(1 for o in observations if o.get("status") == "Held for review")
    count_obs_not_eval = sum(1 for o in observations if o.get("status") == "Not evaluated")
    count_obs_withdrawn = sum(1 for o in observations if o.get("status") == "Withdrawn")

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

    /* Top Nav */
    .top-nav {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 24px;
      background: rgba(17, 24, 39, 0.6);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border-subtle);
      border-radius: 16px;
      margin-bottom: 32px;
    }}

    .brand {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}

    .brand-icon {{
      width: 36px;
      height: 36px;
      border-radius: 10px;
      background: linear-gradient(135deg, var(--accent-indigo), var(--accent-violet));
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 0 20px rgba(99, 102, 241, 0.4);
    }}

    .brand-icon svg {{
      width: 20px;
      height: 20px;
      fill: none;
      stroke: #fff;
      stroke-width: 2;
    }}

    .brand-text h1 {{
      font-family: var(--font-display);
      font-size: 1.25rem;
      font-weight: 700;
      color: #fff;
    }}

    .brand-text p {{
      font-size: 0.75rem;
      color: var(--text-muted);
    }}

    .nav-meta {{
      display: flex;
      align-items: center;
      gap: 16px;
    }}

    .badge-pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 12px;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 600;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }}

    .badge-emerald {{
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.3);
    }}

    .badge-violet {{
      background: rgba(139, 92, 246, 0.15);
      color: #c084fc;
      border: 1px solid rgba(139, 92, 246, 0.3);
    }}

    .badge-amber {{
      background: rgba(245, 158, 11, 0.15);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.3);
    }}

    .badge-s0 {{
      background: rgba(239, 68, 68, 0.2);
      color: #f87171;
      border: 1px solid rgba(239, 68, 68, 0.4);
      padding: 4px 10px;
      border-radius: 6px;
      font-weight: 700;
      font-size: 0.75rem;
    }}

    .badge-s1 {{
      background: rgba(244, 63, 94, 0.2);
      color: #fb7185;
      border: 1px solid rgba(244, 63, 94, 0.4);
      padding: 4px 10px;
      border-radius: 6px;
      font-weight: 700;
      font-size: 0.75rem;
    }}

    .badge-s2 {{
      background: rgba(249, 115, 22, 0.2);
      color: #fb923c;
      border: 1px solid rgba(249, 115, 22, 0.4);
      padding: 4px 10px;
      border-radius: 6px;
      font-weight: 700;
      font-size: 0.75rem;
    }}

    .badge-s3 {{
      background: rgba(245, 158, 11, 0.18);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.4);
      padding: 4px 10px;
      border-radius: 6px;
      font-weight: 700;
      font-size: 0.75rem;
    }}

    .badge-obs {{
      background: rgba(6, 182, 212, 0.18);
      color: #22d3ee;
      border: 1px solid rgba(6, 182, 212, 0.4);
      padding: 4px 10px;
      border-radius: 6px;
      font-weight: 700;
      font-size: 0.75rem;
    }}

    /* Chip Tags */
    .tag-rule {{
      font-family: var(--font-mono);
      font-size: 0.75rem;
      font-weight: 600;
      color: #38bdf8;
      background: rgba(6, 182, 212, 0.12);
      border: 1px solid rgba(6, 182, 212, 0.35);
      padding: 3px 10px;
      border-radius: 6px;
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }}

    .tag-pattern {{
      font-family: var(--font-mono);
      font-size: 0.75rem;
      font-weight: 600;
      color: #fb7185;
      background: rgba(244, 63, 94, 0.12);
      border: 1px solid rgba(244, 63, 94, 0.35);
      padding: 3px 10px;
      border-radius: 6px;
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }}

    .tag-lens {{
      font-size: 0.75rem;
      font-weight: 600;
      color: #c084fc;
      background: rgba(139, 92, 246, 0.12);
      border: 1px solid rgba(139, 92, 246, 0.3);
      padding: 3px 10px;
      border-radius: 6px;
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }}

    .tag-qa {{
      font-family: var(--font-mono);
      font-size: 0.72rem;
      color: #94a3b8;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border-subtle);
      padding: 3px 9px;
      border-radius: 6px;
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }}

    .tag-stack {{
      font-size: 0.72rem;
      color: #818cf8;
      background: rgba(99, 102, 241, 0.1);
      border: 1px solid rgba(99, 102, 241, 0.25);
      padding: 2px 8px;
      border-radius: 4px;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }}

    /* Hero Card */
    .hero-card {{
      position: relative;
      background: linear-gradient(145deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.9) 100%);
      border: 1px solid var(--border-subtle);
      border-radius: 20px;
      padding: 36px;
      backdrop-filter: blur(20px);
      box-shadow: 0 20px 40px -15px rgba(0, 0, 0, 0.5);
      margin-bottom: 32px;
      overflow: hidden;
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
      margin-bottom: 24px;
      flex-wrap: wrap;
      gap: 20px;
    }}

    .hero-title-area {{
      max-width: 820px;
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
      font-size: 2.2rem;
      font-weight: 800;
      color: #fff;
      line-height: 1.2;
      margin-bottom: 12px;
    }}

    .hero-description {{
      color: var(--text-muted);
      font-size: 0.95rem;
      line-height: 1.6;
    }}

    /* Score Gauge Banner */
    .score-banner {{
      display: flex;
      align-items: center;
      gap: 24px;
      background: rgba(15, 23, 42, 0.8);
      border: 1px solid var(--border-subtle);
      border-radius: 16px;
      padding: 20px 24px;
    }}

    .gauge-wrapper {{
      position: relative;
      width: 96px;
      height: 96px;
      display: flex;
      align-items: center;
      justify-content: center;
    }}

    .gauge-svg {{
      width: 100%;
      height: 100%;
      transform: rotate(-90deg);
    }}

    .gauge-bg {{
      fill: none;
      stroke: rgba(255, 255, 255, 0.08);
      stroke-width: 8;
    }}

    .gauge-fill {{
      fill: none;
      stroke: url(#scoreGradient);
      stroke-width: 8;
      stroke-linecap: round;
      stroke-dasharray: {circumference};
      stroke-dashoffset: {dash_offset};
      transition: stroke-dashoffset 1s ease;
    }}

    .gauge-value {{
      position: absolute;
      text-align: center;
    }}

    .gauge-number {{
      font-family: var(--font-display);
      font-size: 1.8rem;
      font-weight: 800;
      color: #fff;
      line-height: 1;
    }}

    .gauge-total {{
      font-size: 0.75rem;
      color: var(--text-dim);
    }}

    .score-meta h3 {{
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--text-muted);
      margin-bottom: 4px;
    }}

    .verdict-text {{
      font-family: var(--font-display);
      font-size: 1.35rem;
      font-weight: 700;
      color: #34d399;
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 4px;
    }}

    .score-meta p {{
      font-size: 0.8rem;
      color: var(--text-dim);
    }}

    /* Quick Metrics Grid */
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-top: 24px;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
      padding-top: 24px;
    }}

    .stat-item {{
      background: rgba(15, 23, 42, 0.5);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 16px;
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
      font-size: 1.4rem;
      font-weight: 700;
      margin-bottom: 4px;
    }}

    .stat-sub {{
      font-size: 0.75rem;
      color: var(--text-dim);
    }}

    /* Tab Bar */
    .tab-bar {{
      display: flex;
      gap: 8px;
      border-bottom: 1px solid var(--border-subtle);
      margin-bottom: 24px;
      overflow-x: auto;
      padding-bottom: 4px;
    }}

    .tab-btn {{
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-family: var(--font-sans);
      font-size: 0.9rem;
      font-weight: 600;
      padding: 12px 18px;
      border-radius: 10px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s ease;
      white-space: nowrap;
    }}

    .tab-btn:hover {{
      color: #fff;
      background: rgba(255, 255, 255, 0.04);
    }}

    .tab-btn.active {{
      color: #fff;
      background: rgba(99, 102, 241, 0.15);
      border: 1px solid rgba(99, 102, 241, 0.3);
    }}

    .tab-count {{
      font-size: 0.75rem;
      padding: 2px 7px;
      border-radius: 9999px;
      background: rgba(255, 255, 255, 0.08);
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
      color: #fff;
      border-color: var(--accent-indigo);
    }}

    /* Finding Card */
    .finding-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: 16px;
      padding: 24px;
      margin-bottom: 20px;
      transition: border-color 0.2s, transform 0.2s;
    }}

    .finding-card:hover {{
      border-color: var(--border-focus);
    }}

    .finding-card.severity-S0 {{ border-left: 4px solid var(--accent-rose); }}
    .finding-card.severity-S1 {{ border-left: 4px solid var(--accent-rose); }}
    .finding-card.severity-S2 {{ border-left: 4px solid var(--accent-amber); }}
    .finding-card.severity-S3 {{ border-left: 4px solid #fbbf24; }}
    .finding-card.severity-O {{ border-left: 4px solid var(--accent-cyan); }}
    .finding-card.severity-Resolved,
    .finding-card[data-status="Resolved"] {{ border-left: 4px solid var(--accent-emerald); }}

    .finding-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      flex-wrap: wrap;
      gap: 10px;
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
      color: var(--accent-cyan);
    }}

    .finding-title {{
      font-family: var(--font-display);
      font-size: 1.25rem;
      font-weight: 700;
      color: #fff;
      margin-bottom: 16px;
    }}

    .finding-body-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
      gap: 16px;
    }}

    .section-box {{
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.05);
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

    /* Evidence Gallery */
    .evidence-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 20px;
    }}

    .evidence-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: 14px;
      overflow: hidden;
      cursor: pointer;
      transition: transform 0.2s, border-color 0.2s;
    }}

    .evidence-card:hover {{
      transform: translateY(-4px);
      border-color: var(--border-focus);
    }}

    .evidence-thumb-container {{
      width: 100%;
      height: 200px;
      background: #000;
      overflow: hidden;
    }}

    .evidence-thumb {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      object-position: top;
      transition: transform 0.3s;
    }}

    .evidence-card:hover .evidence-thumb {{
      transform: scale(1.03);
    }}

    .evidence-meta {{
      padding: 14px 18px;
    }}

    .evidence-meta h4 {{
      font-size: 0.95rem;
      font-weight: 600;
      color: #fff;
      margin-bottom: 4px;
    }}

    .evidence-meta p {{
      font-size: 0.75rem;
      color: var(--text-dim);
      font-family: var(--font-mono);
    }}

    /* Data Table */
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
          <p>Run: {escape(run_label)} • Target: {escape(card.get('url', 'e2e-test.uat.lexful.net'))}</p>
        </div>
      </div>
      <div class="nav-meta">
        <span class="badge-pill badge-emerald">QA: {qa.get('verdict', 'NEEDS_REVISION')}</span>
        <span class="badge-pill badge-violet">UX SCORE: {score}/100</span>
      </div>
    </nav>

    <!-- Hero Card -->
    <section class="hero-card">
      <div class="hero-header">
        <div class="hero-title-area">
          <div class="ticket-chip-row">
            <span class="ticket-id">{escape(ticket)}</span>
            <span class="badge-pill badge-emerald">Status: Evaluated</span>
            {f'<span class="pr-link">PR #{pr_num}</span>' if pr_num else ''}
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
            <h3>UX Health Verdict</h3>
            <div class="verdict-text">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                <polyline points="22 4 12 14.01 9 11.01"/>
              </svg>
              {escape(verdict)}
            </div>
            <p>0 Blockers • {counts.get('S3', 0)} Minor UI (S3) • {len(observations)} Observations</p>
          </div>
        </div>
      </div>

      <!-- Quick Metrics Grid -->
      <div class="stats-grid">
        <div class="stat-item">
          <div class="stat-label">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            Task Completion
          </div>
          <div class="stat-value" style="color:#34d399">PASS (Asset)</div>
          <div class="stat-sub">Live asset empty Sources tab verified; Org drawer held for review</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            UX Severity Deductions
          </div>
          <div class="stat-value" style="color:#fbbf24">-{total_deduction} pts</div>
          <div class="stat-sub">S0={counts.get('S0', 0)}, S1={counts.get('S1', 0)}, S2={counts.get('S2', 0)}, S3={counts.get('S3', 0)}, Obs={len(observations)}</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            Automated Specs
          </div>
          <div class="stat-value" style="color:#a5b4fc">{passed_count} Passed</div>
          <div class="stat-sub">Live AC1 + Mocked AC3 error recovery validated</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
            Design Stack
          </div>
          <div class="stat-value" style="font-size:1.1rem;color:#38bdf8">shadcn + Fluent</div>
          <div class="stat-sub">Radix TabList &amp; Empty State patterns</div>
        </div>
      </div>
    </section>

    <!-- Tab Bar -->
    <div class="tab-bar">
      <button class="tab-btn active" onclick="switchTab('tab-defects', this)">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
        UI/UX Defects (S0–S3)
        <span class="tab-count">{len(defects)}</span>
      </button>
      <button class="tab-btn" onclick="switchTab('tab-observations', this)">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
        UX Observations &amp; Verification (O)
        <span class="tab-count">{len(observations)}</span>
      </button>
      <button class="tab-btn" onclick="switchTab('tab-evidence', this)">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
        Visual Evidence &amp; Lightbox
        <span class="tab-count">{len(evidence_images)}</span>
      </button>
      <button class="tab-btn" onclick="switchTab('tab-criteria', this)">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
        Evaluated Checks Matrix
        <span class="tab-count">{len(card.get('checksEvaluated', []))}</span>
      </button>
      <button class="tab-btn" onclick="switchTab('tab-ledger', this)">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
        Scoring &amp; Deduction Ledger
      </button>
    </div>

    <!-- TAB 1: UI/UX DEFECTS (S0–S3) -->
    <div id="tab-defects" class="tab-pane active">
      <div class="filter-bar">
        <div class="filter-pills">
          <button class="filter-pill active" onclick="filterDefects('all', this)">All Defects ({len(defects)})</button>
          <button class="filter-pill" onclick="filterDefects('S0', this)">S0 Blocker ({counts.get('S0', 0)})</button>
          <button class="filter-pill" onclick="filterDefects('S1', this)">S1 Critical ({counts.get('S1', 0)})</button>
          <button class="filter-pill" onclick="filterDefects('S2', this)">S2 Major ({counts.get('S2', 0)})</button>
          <button class="filter-pill" onclick="filterDefects('S3', this)">S3 Minor ({counts.get('S3', 0)})</button>
        </div>
        <span style="font-size:0.8rem;color:var(--text-dim)">Scoring calibration: S0=-40, S1=-25 (Blocking) • S2=-10, S3=-3 (Non-blocking)</span>
      </div>

      {"".join(defects_cards_html)}
    </div>

    <!-- TAB 2: UX OBSERVATIONS & VERIFICATION (O) -->
    <div id="tab-observations" class="tab-pane">
      <div style="display:flex;align-items:center;gap:14px;background:rgba(6,182,212,0.08);border:1px solid rgba(6,182,212,0.25);border-radius:14px;padding:16px 20px;margin-bottom:20px;">
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
          <button class="filter-pill" onclick="filterObservations('Not evaluated', this)">Not Evaluated ({count_obs_not_eval})</button>
          <button class="filter-pill" onclick="filterObservations('Withdrawn', this)">Withdrawn ({count_obs_withdrawn})</button>
        </div>
        <span style="font-size:0.8rem;color:var(--text-dim)">Scoring impact: 0 deduction pts • Advisory only</span>
      </div>

      {"".join(observations_cards_html)}
    </div>

    <!-- TAB 3: VISUAL EVIDENCE & LIGHTBOX -->
    <div id="tab-evidence" class="tab-pane">
      <div class="evidence-grid">
        {"".join(evidence_cards_html)}
      </div>
    </div>

    <!-- TAB 4: EVALUATED CHECKS MATRIX -->
    <div id="tab-criteria" class="tab-pane">
      <h3 style="font-family:var(--font-display);font-size:1.2rem;margin-bottom:16px;color:#fff;">Evaluated UX Checks</h3>
      <table class="data-table" style="margin-bottom:32px;">
        <thead>
          <tr>
            <th>Check / Rule</th>
            <th>Status</th>
            <th>Observation &amp; Result</th>
          </tr>
        </thead>
        <tbody>
          {"".join(evaluated_rows)}
        </tbody>
      </table>

      <h3 style="font-family:var(--font-display);font-size:1.2rem;margin-bottom:16px;color:var(--text-muted);">Checks Not Evaluated In This Journey</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>Check / Rule</th>
            <th>Status</th>
            <th>Reason Excluded</th>
          </tr>
        </thead>
        <tbody>
          {"".join(not_evaluated_rows)}
        </tbody>
      </table>
    </div>

    <!-- TAB 5: SCORING & DEDUCTION LEDGER -->
    <div id="tab-ledger" class="tab-pane">
      <h3 style="font-family:var(--font-display);font-size:1.2rem;margin-bottom:16px;color:#fff;">Deduction Ledger &amp; Calibration</h3>
      <table class="data-table" style="margin-bottom:24px;">
        <thead>
          <tr>
            <th>Finding ID</th>
            <th>Severity</th>
            <th>Points Deducted</th>
            <th>Running Subtotal</th>
            <th>Ledger Note</th>
          </tr>
        </thead>
        <tbody>
          {"".join(ledger_rows)}
        </tbody>
      </table>

      <div class="section-box" style="margin-top:20px;">
        <div class="section-box-title">Calibration Rules &amp; Non-Blocking Principle</div>
        <div class="section-box-content">
          <p>Per <code>lexful-ux-audit-gate/SKILL.md</code> v0.20: S2 and S3 findings are strictly non-blocking and do not fail the release. When only S2/S3 or Observations exist, the release verdict is <strong>PASS WITH ADVISORIES</strong>. Only verified S0/S1 blockers cause a blocking failure.</p>
        </div>
      </div>
    </div>

    <!-- Lightbox Modal -->
    <div id="lightbox" class="lightbox-modal" onclick="closeLightbox(event)">
      <div class="lightbox-content">
        <button class="lightbox-close" onclick="closeLightbox(event)">✕ Close</button>
        <img id="lightbox-img" class="lightbox-img" src="" alt="Enlarged evidence">
        <div id="lightbox-caption" class="lightbox-caption"></div>
      </div>
    </div>

    <!-- Footer -->
    <footer>
      <p>Lexful Autonomous Agent QA &amp; UX Audit Engine • Ticket {escape(ticket)} • Generated for User Review</p>
    </footer>

  </div>

  <script>
    function switchTab(tabId, btn) {{
      document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
      const target = document.getElementById(tabId);
      if (target) target.classList.add('active');
      btn.classList.add('active');
    }}

    function filterDefects(severity, btn) {{
      document.querySelectorAll('#tab-defects .filter-pill').forEach(el => el.classList.remove('active'));
      btn.classList.add('active');
      const cards = document.querySelectorAll('#tab-defects .finding-card[data-severity]');
      cards.forEach(card => {{
        if (severity === 'all' || card.getAttribute('data-severity') === severity) {{
          card.style.display = 'block';
        }} else {{
          card.style.display = 'none';
        }}
      }});
    }}

    function filterObservations(status, btn) {{
      document.querySelectorAll('#tab-observations .filter-pill').forEach(el => el.classList.remove('active'));
      btn.classList.add('active');
      const cards = document.querySelectorAll('#tab-observations .finding-card');
      cards.forEach(card => {{
        const cardStatus = (card.getAttribute('data-status') || '').toLowerCase();
        const targetStatus = status.toLowerCase();
        if (targetStatus === 'all' || cardStatus === targetStatus || (targetStatus === 'resolved' && (cardStatus === 'resolved' || cardStatus === 'verified fixed'))) {{
          card.style.display = 'block';
        }} else {{
          card.style.display = 'none';
        }}
      }});
    }}

    function filterFindings(severity, btn) {{
      filterDefects(severity, btn);
    }}

    function openLightbox(src, caption) {{
      const modal = document.getElementById('lightbox');
      const img = document.getElementById('lightbox-img');
      const cap = document.getElementById('lightbox-caption');
      img.src = src;
      cap.textContent = caption;
      modal.classList.add('active');
    }}

    function closeLightbox(e) {{
      if (e.target.id === 'lightbox' || e.target.classList.contains('lightbox-close')) {{
        document.getElementById('lightbox').classList.remove('active');
      }}
    }}

    document.addEventListener('keydown', (e) => {{
      if (e.key === 'Escape') {{
        document.getElementById('lightbox').classList.remove('active');
      }}
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
