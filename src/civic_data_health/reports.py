from __future__ import annotations

import csv
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .analysis import asset_group, asset_group_label, summarize_asset_groups, top_actionable_fixes
from .category_suggestions import rows_with_category_suggestions
from .storage import connect, latest_run_id, report_rows, run_summary, skipped_rows

FOOTER = "Prepared by Pagonya LLC using public City of Austin open data. Not affiliated with or endorsed by the City of Austin."
SECTION_ORDER = ("active_dataset", "needs_manual_review", "archive_snapshot", "event_specific", "measure", "story_reference")
PUBLIC_SITE_URL = "https://civic.pagonya.co"
PUBLIC_MCP_URL = PUBLIC_SITE_URL + "/mcp"
OPENAI_CONNECT_DOC_URL = "https://developers.openai.com/apps-sdk/deploy/connect-chatgpt"


def write_reports(*, db_path: Path, out_dir: Optional[Path], run_id: Optional[int] = None) -> Dict[str, str]:
    if out_dir is None:
        raise ValueError("out_dir is required")
    out_dir.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        selected_run_id = run_id or latest_run_id(conn)
        if selected_run_id is None:
            raise ValueError("No runs found in SQLite database")
        summary = run_summary(conn, selected_run_id)
        rows = report_rows(conn, selected_run_id)
        skipped = skipped_rows(conn, selected_run_id)

    json_path = out_dir / "austin_dataset_health.json"
    csv_path = out_dir / "austin_dataset_health.csv"
    html_path = out_dir / "austin_dataset_health.html"
    index_path = out_dir / "index.html"
    methodology_path = out_dir / "methodology.html"
    help_path = out_dir / "help.html"
    detail_dir = out_dir / "datasets"
    group_summary = summarize_asset_groups(rows)

    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "summary": summary,
        "classification_groups": group_summary,
        "asset_groups": group_summary,
        "skipped_records": skipped,
        "datasets": rows,
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_csv(csv_path, rows)
    write_detail_pages(detail_dir, summary, rows)
    html_text = render_html(summary, rows, skipped)
    html_path.write_text(html_text, encoding="utf-8")
    index_path.write_text(html_text, encoding="utf-8")
    methodology_path.write_text(render_methodology_page(summary), encoding="utf-8")
    help_path.write_text(render_help_page(summary), encoding="utf-8")

    return {
        "json": str(json_path),
        "csv": str(csv_path),
        "html": str(html_path),
        "index": str(index_path),
        "methodology": str(methodology_path),
        "help": str(help_path),
        "details": str(detail_dir),
    }


def write_csv(path: Path, rows) -> None:
    fields = [
        "dataset_id",
        "title",
        "score",
        "label",
        "issue_codes",
        "modified",
        "publisher",
        "contact",
        "license",
        "category",
        "tags",
        "suggested_category",
        "suggested_category_confidence",
        "suggested_category_status",
        "suggested_category_evidence",
        "landing_url",
        "machine_url",
        "asset_type",
        "classification_group",
        "classification_confidence",
        "classification_evidence",
        "classification_reason",
        "remediation",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "dataset_id": row["dataset_id"],
                    "title": row["title"],
                    "score": row["score"],
                    "label": row["label"],
                    "issue_codes": ";".join(row["issue_codes"]),
                    "modified": row["modified"] or "",
                    "publisher": row["publisher"],
                    "contact": row["contact"],
                    "license": row["license"],
                    "category": row["category"],
                    "tags": ";".join(row.get("keywords") or []),
                    "suggested_category": (row.get("category_suggestion") or {}).get("suggested_category", ""),
                    "suggested_category_confidence": (row.get("category_suggestion") or {}).get("confidence", ""),
                    "suggested_category_status": (row.get("category_suggestion") or {}).get("status", ""),
                    "suggested_category_evidence": ";".join((row.get("category_suggestion") or {}).get("evidence", [])),
                    "landing_url": row["landing_url"],
                    "machine_url": row["machine_url"],
                    "asset_type": row.get("asset_type") or "",
                    "classification_group": (row.get("classification") or {}).get("group", ""),
                    "classification_confidence": (row.get("classification") or {}).get("confidence", ""),
                    "classification_evidence": ";".join((row.get("classification") or {}).get("evidence", [])),
                    "classification_reason": (row.get("classification") or {}).get("reason", ""),
                    "remediation": " ".join(row["remediation"]),
                }
            )


def render_html(summary: Dict[str, Any], rows, skipped) -> str:
    group_summary = summarize_asset_groups(rows)
    active_summary = group_summary["active_dataset"]
    actionable = top_actionable_fixes(rows, limit=25, group="active_dataset")
    skipped_markup = "".join(
        "<li>#{idx}: {title} ({identifier}) - {reason}</li>".format(
            idx=record["source_index"],
            title=escape(record["title"] or "untitled"),
            identifier=escape(record["identifier_candidate"] or "no identifier"),
            reason=escape(record["reason_code"]),
        )
        for record in skipped[:20]
    )
    if not skipped_markup:
        skipped_markup = "<li>No skipped records in this run.</li>"

    section_markup = "\n".join(render_asset_section(group, rows, group_summary[group]) for group in SECTION_ORDER)
    group_markup = "\n".join(render_group_metric(group_summary[group]) for group in SECTION_ORDER)
    actionable_markup = "\n".join(render_actionable_row(item) for item in actionable)
    suggestion_markup = "\n".join(render_category_suggestion_row(row) for row in rows_with_category_suggestions(rows, limit=25))
    if not actionable_markup:
        actionable_markup = '<tr><td colspan="6">No active dataset fixes are currently ranked above the review threshold.</td></tr>'
    if not suggestion_markup:
        suggestion_markup = '<tr><td colspan="6">No missing-category suggestions are available in this run.</td></tr>'
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Civic Data Health - Austin Open Data</title>
  <style>
    :root {{ color-scheme: light; --ink:#18212f; --muted:#5f6b7a; --line:#d8dee8; --bg:#f4f6f8; --panel:#ffffff; --risk:#b42318; --warn:#9a6700; --good:#146c43; --accent:#0f5f7a; }}
    body {{ margin:0; font-family: Georgia, "Times New Roman", serif; color:var(--ink); background:var(--bg); }}
    header {{ padding:34px 28px 24px; background:#e8eef2; border-bottom:1px solid var(--line); }}
    main {{ max-width:1180px; margin:0 auto; padding:24px 18px 44px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(30px, 5vw, 54px); letter-spacing:0; }}
    h2 {{ margin:28px 0 12px; font-size:24px; }}
    p {{ line-height:1.5; }}
    .summary {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:10px; margin-top:20px; }}
    .group-summary {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:12px; margin:18px 0; }}
    .metric {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; }}
    .metric strong {{ display:block; font-size:28px; }}
    .metric span {{ color:var(--muted); font-size:14px; }}
    .tabs {{ display:flex; flex-wrap:wrap; gap:10px; margin:22px 0 0; }}
    .tabs a {{ border:1px solid #bfd0d9; border-radius:6px; padding:9px 12px; background:#fff; color:var(--accent); text-decoration:none; font-family: ui-sans-serif, system-ui, sans-serif; font-weight:700; }}
    .actions {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:18px; }}
    .actions a {{ color:#fff; background:var(--accent); text-decoration:none; border-radius:6px; padding:9px 12px; font-family: ui-sans-serif, system-ui, sans-serif; }}
    table {{ width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--line); }}
    th, td {{ padding:10px; border-bottom:1px solid var(--line); vertical-align:top; text-align:left; }}
    th {{ font-family: ui-sans-serif, system-ui, sans-serif; font-size:13px; color:#2f3b49; background:#f9fafb; position:sticky; top:0; }}
    td {{ font-size:14px; }}
    .title {{ min-width:240px; font-weight:700; }}
    .issues {{ color:var(--muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size:12px; }}
    .label {{ font-family: ui-sans-serif, system-ui, sans-serif; font-weight:700; }}
    .high_risk {{ color:var(--risk); }}
    .needs_review {{ color:var(--warn); }}
    .good {{ color:var(--good); }}
    .section-note {{ color:var(--muted); margin-top:-4px; }}
    footer {{ color:var(--muted); border-top:1px solid var(--line); padding-top:18px; margin-top:28px; }}
    @media (max-width:760px) {{ table, thead, tbody, th, td, tr {{ display:block; }} thead {{ display:none; }} tr {{ border-bottom:1px solid var(--line); padding:10px; }} td {{ border:0; padding:5px 0; }} td::before {{ content:attr(data-label) ": "; font-weight:700; }} }}
  </style>
</head>
<body>
  <header>
    <main>
      <h1>Civic Data Health</h1>
      <p>Austin Open Data metadata audit generated from the public DCAT catalog. Active datasets, archives, event records, measures, and story assets are classified before risk ranking.</p>
      <div class="summary">
        <div class="metric"><strong>{analyzed}</strong><span>Analyzed of {total} catalog records</span></div>
        <div class="metric"><strong>{high_risk}</strong><span>High-risk active datasets</span></div>
        <div class="metric"><strong>{needs_review}</strong><span>Needs review</span></div>
        <div class="metric"><strong>{good}</strong><span>Good</span></div>
        <div class="metric"><strong>{skipped}</strong><span>Skipped normalization records</span></div>
        <div class="metric"><strong>{average}</strong><span>Average score</span></div>
      </div>
      <div class="actions">
        <a href="austin_dataset_health.csv">Download CSV</a>
        <a href="austin_dataset_health.json">Download JSON</a>
        <a href="methodology.html">Methodology</a>
        <a href="help.html">Connect to ChatGPT</a>
      </div>
      <nav class="tabs" aria-label="Report sections">
        <a href="#active_dataset">Active datasets</a>
        <a href="#needs_manual_review">Needs classification review</a>
        <a href="#archive_snapshot">Archive snapshots</a>
        <a href="#event_specific">Event records</a>
        <a href="#measure">Measures and indicators</a>
        <a href="#story_reference">Stories and reference</a>
        <a href="#actionable">Top fix opportunities</a>
        <a href="#category-suggestions">Category suggestions</a>
      </nav>
    </main>
  </header>
  <main>
    <h2>Catalog Sections</h2>
    <p class="section-note">Active datasets are ranked separately from archives, one-time events, Socrata measures, story pages, and ambiguous dated records so the operational risk queue stays credible.</p>
    <div class="group-summary">
      {group_metrics}
    </div>
    <h2 id="actionable">Top Active Dataset Fix Opportunities</h2>
    <p class="section-note">Ranked by metadata impact, label severity, and ease of remediation. This is the practical cleanup queue for a city data steward.</p>
    <table>
      <thead><tr><th>Dataset</th><th>Priority</th><th>Score</th><th>Label</th><th>Owner</th><th>Actions</th></tr></thead>
      <tbody>
        {actionable_rows}
      </tbody>
    </table>
    <h2 id="category-suggestions">Missing Category Suggestions</h2>
    <p class="section-note">Suggestions are trained from catalog rows that already publish categories. They do not overwrite Austin's metadata; they are review hints for missing-category records.</p>
    <table>
      <thead><tr><th>Dataset</th><th>Suggested Category</th><th>Confidence</th><th>Status</th><th>Evidence</th><th>Issues</th></tr></thead>
      <tbody>
        {suggestion_rows}
      </tbody>
    </table>
    {sections}
    <h2>Skipped Records</h2>
    <p>Skipped {skipped_count} records due to normalization errors. Showing up to 20.</p>
    <ul>{skipped_markup}</ul>
    <footer>{footer}<br />Run {run_id} fetched at {fetched_at}. Data dictionary quality is reported separately and not included in global ranking.</footer>
  </main>
</body>
</html>
""".format(
        analyzed=summary["analyzed_records"],
        total=summary["total_records"],
        high_risk=active_summary["labels"]["high_risk"],
        needs_review=summary["labels"]["needs_review"],
        good=summary["labels"]["good"],
        skipped=summary["skipped_records"],
        average=summary["average_score"],
        group_metrics=group_markup,
        actionable_rows=actionable_markup,
        suggestion_rows=suggestion_markup,
        sections=section_markup,
        skipped_count=summary["skipped_records"],
        skipped_markup=skipped_markup,
        footer=escape(FOOTER),
        run_id=summary["run_id"],
        fetched_at=escape(summary["fetched_at"]),
    )


def render_group_metric(summary: Dict[str, Any]) -> str:
    return """<div class="metric">
  <strong>{count}</strong>
  <span>{label}</span>
  <p class="section-note">Needs review: {needs_review} | Good: {good} | High risk: {high_risk}</p>
</div>""".format(
        count=summary["count"],
        label=escape(summary["label"]),
        needs_review=summary["labels"]["needs_review"],
        good=summary["labels"]["good"],
        high_risk=summary["labels"]["high_risk"],
    )


def render_asset_section(group: str, rows, summary: Dict[str, Any]) -> str:
    group_rows = [row for row in rows if asset_group(row) == group][:75]
    body = "\n".join(render_dataset_row(row) for row in group_rows)
    if not body:
        body = '<tr><td colspan="8">No records in this section.</td></tr>'
    top_issues = ", ".join("%s (%s)" % (issue["title"], issue["count"]) for issue in summary["top_issues"][:4]) or "No recurring issues"
    return """<section id="{group}">
  <h2>{label}</h2>
  <p class="section-note">{count} records. Showing top {shown} by label, score, and title. Frequent issues: {issues}.</p>
  <table>
    <thead><tr><th>Dataset</th><th>Score</th><th>Label</th><th>Classification</th><th>Modified</th><th>Owner</th><th>Issues</th><th>Remediation</th></tr></thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</section>""".format(
        group=escape(group),
        label=escape(asset_group_label(group)),
        count=summary["count"],
        shown=len(group_rows),
        issues=escape(top_issues),
        rows=body,
    )


def render_actionable_row(item: Dict[str, Any]) -> str:
    title = escape(item["title"] or item["dataset_id"])
    detail_href = "datasets/%s.html" % escape(item["dataset_id"])
    title = '<a href="{url}">{title}</a>'.format(url=detail_href, title=title)
    return """<tr>
  <td data-label="Dataset" class="title">{title}<div class="issues">{dataset_id}</div></td>
  <td data-label="Priority">{priority}</td>
  <td data-label="Score">{score}</td>
  <td data-label="Label" class="label {label}">{label}</td>
  <td data-label="Owner">{owner}</td>
  <td data-label="Actions">{actions}</td>
</tr>""".format(
        title=title,
        dataset_id=escape(item["dataset_id"]),
        priority=item["priority"],
        score=item["score"],
        label=escape(item["label"]),
        owner=escape(item["owner"]),
        actions=escape(" ".join(item["recommended_actions"])),
    )


def render_category_suggestion_row(row: Dict[str, Any]) -> str:
    suggestion = row.get("category_suggestion") or {}
    title = escape(row["title"] or row["dataset_id"])
    detail_href = "datasets/%s.html" % escape(row["dataset_id"])
    title = '<a href="{url}">{title}</a>'.format(url=detail_href, title=title)
    return """<tr>
  <td data-label="Dataset" class="title">{title}<div class="issues">{dataset_id}</div></td>
  <td data-label="Suggested Category">{suggested_category}</td>
  <td data-label="Confidence">{confidence}</td>
  <td data-label="Status">{status}</td>
  <td data-label="Evidence" class="issues">{evidence}</td>
  <td data-label="Issues" class="issues">{issues}</td>
</tr>""".format(
        title=title,
        dataset_id=escape(row["dataset_id"]),
        suggested_category=escape(suggestion.get("suggested_category") or ""),
        confidence=escape(format_confidence(suggestion)),
        status=escape(suggestion.get("status") or ""),
        evidence=escape(", ".join(suggestion.get("evidence") or [])),
        issues=escape(", ".join(row.get("issue_codes") or [])),
    )


def render_dataset_row(row: Dict[str, Any]) -> str:
    remediation = " ".join(row["remediation"])
    owner = row["publisher"] or row["contact"] or "Missing"
    classification = row.get("classification") or {}
    evidence = ", ".join(classification.get("evidence") or [])
    classification_text = "%s (%s)" % (asset_group_label(asset_group(row)), classification.get("confidence") or "unknown")
    if evidence:
        classification_text += " - %s" % evidence
    title = escape(row["title"] or row["dataset_id"])
    detail_href = "datasets/%s.html" % escape(row["dataset_id"])
    title = '<a href="{url}">{title}</a>'.format(url=detail_href, title=title)
    return """<tr>
  <td data-label="Dataset" class="title">{title}<div class="issues">{dataset_id}</div></td>
  <td data-label="Score">{score}</td>
  <td data-label="Label" class="label {label}">{label}</td>
  <td data-label="Classification">{classification}</td>
  <td data-label="Modified">{modified}</td>
  <td data-label="Owner">{owner}</td>
  <td data-label="Issues" class="issues">{issues}</td>
  <td data-label="Remediation">{remediation}</td>
</tr>""".format(
        title=title,
        dataset_id=escape(row["dataset_id"]),
        score=row["score"],
        label=escape(row["label"]),
        classification=escape(classification_text),
        modified=escape(row["modified"] or "Missing"),
        owner=escape(owner),
        issues=escape(", ".join(row["issue_codes"])),
        remediation=escape(remediation),
    )


def write_detail_pages(detail_dir: Path, summary: Dict[str, Any], rows) -> None:
    detail_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        path = detail_dir / ("%s.html" % row["dataset_id"])
        path.write_text(render_detail_page(summary, row), encoding="utf-8")


def render_detail_page(summary: Dict[str, Any], row: Dict[str, Any]) -> str:
    issue_items = "".join("<li>%s</li>" % escape(issue) for issue in row["issue_codes"])
    remediation_items = "".join("<li>%s</li>" % escape(item) for item in row["remediation"])
    classification = row.get("classification") or {}
    classification_evidence = ", ".join(classification.get("evidence") or []) or "No stored evidence"
    landing = row.get("landing_url") or ""
    machine = row.get("machine_url") or ""
    tags = format_tags(row)
    category_suggestion = render_category_suggestion_detail(row)
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} - Civic Data Health</title>
  <style>
    :root {{ color-scheme: light; --ink:#18212f; --muted:#5f6b7a; --line:#d8dee8; --bg:#f4f6f8; --panel:#ffffff; --accent:#0f5f7a; }}
    body {{ margin:0; font-family: Georgia, "Times New Roman", serif; color:var(--ink); background:var(--bg); }}
    main {{ max-width:940px; margin:0 auto; padding:28px 18px 44px; }}
    a {{ color:var(--accent); }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:18px; margin:14px 0; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; }}
    .metric strong {{ display:block; font-size:26px; }}
    .metric span, .muted {{ color:var(--muted); }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    li {{ margin:7px 0; }}
  </style>
</head>
<body>
  <main>
    <p><a href="../index.html">Back to report</a></p>
    <h1>{title}</h1>
    <div class="panel grid">
      <div class="metric"><strong>{score}</strong><span>Score</span></div>
      <div class="metric"><strong>{label}</strong><span>Label</span></div>
      <div class="metric"><strong>{classification_group}</strong><span>Classification</span></div>
      <div class="metric"><strong>{asset}</strong><span>Socrata asset type</span></div>
      <div class="metric"><strong>{modified}</strong><span>Modified</span></div>
    </div>
    <div class="panel">
      <h2>Why It Was Flagged</h2>
      <ul>{issues}</ul>
    </div>
    <div class="panel">
      <h2>Recommended Fix</h2>
      <ul>{remediation}</ul>
    </div>
    <div class="panel">
      <h2>Evidence</h2>
      <p><strong>Dataset id:</strong> <code>{dataset_id}</code></p>
      <p><strong>Classification confidence:</strong> {classification_confidence}</p>
      <p><strong>Classification evidence:</strong> <code>{classification_evidence}</code></p>
      <p><strong>Classification reason:</strong> {classification_reason}</p>
      <p><strong>Owner:</strong> {owner}</p>
      <p><strong>Contact:</strong> {contact}</p>
      <p><strong>Category:</strong> {category}</p>
      <p><strong>Tags:</strong> {tags}</p>
      {category_suggestion}
      <p><strong>License:</strong> {license}</p>
      <p><strong>Landing page:</strong> {landing}</p>
      <p><strong>Machine URL:</strong> {machine}</p>
      <p class="muted">Run {run_id}, fetched {fetched_at}.</p>
    </div>
  </main>
</body>
</html>
""".format(
        title=escape(row["title"] or row["dataset_id"]),
        score=row["score"],
        label=escape(row["label"]),
        classification_group=escape(asset_group_label(asset_group(row))),
        asset=escape(row.get("asset_type") or "dataset"),
        modified=escape(row.get("modified") or "Missing"),
        issues=issue_items,
        remediation=remediation_items,
        dataset_id=escape(row["dataset_id"]),
        classification_confidence=escape(classification.get("confidence") or "unknown"),
        classification_evidence=escape(classification_evidence),
        classification_reason=escape(classification.get("reason") or ""),
        owner=escape(row.get("publisher") or "Missing"),
        contact=escape(row.get("contact") or "Missing"),
        category=format_category(row),
        tags=tags,
        category_suggestion=category_suggestion,
        license=escape(row.get("license") or "Missing"),
        landing=('<a href="%s">%s</a>' % (escape(landing), escape(landing))) if landing else "Missing",
        machine=('<a href="%s">%s</a>' % (escape(machine), escape(machine))) if machine else "Missing",
        run_id=summary["run_id"],
        fetched_at=escape(summary["fetched_at"]),
    )


def format_category(row: Dict[str, Any]) -> str:
    category = row.get("category") or ""
    if category:
        return escape(category)
    keywords = row.get("keywords") or []
    if keywords:
        return "Missing (tags available: %s)" % format_tags(row)
    return "Missing"


def format_tags(row: Dict[str, Any]) -> str:
    keywords = row.get("keywords") or []
    if not keywords:
        return "Missing"
    return escape(", ".join(str(keyword) for keyword in keywords))


def render_category_suggestion_detail(row: Dict[str, Any]) -> str:
    suggestion = row.get("category_suggestion") or {}
    suggested_category = suggestion.get("suggested_category") or ""
    if not suggested_category:
        return ""
    evidence = ", ".join(suggestion.get("evidence") or []) or "No shared tokens"
    return (
        "<p><strong>Suggested category:</strong> {category} "
        "({confidence}, {status}). <strong>Evidence:</strong> {evidence}</p>"
    ).format(
        category=escape(suggested_category),
        confidence=escape(format_confidence(suggestion)),
        status=escape(suggestion.get("status") or "unknown"),
        evidence=escape(evidence),
    )


def format_confidence(suggestion: Dict[str, Any]) -> str:
    confidence = suggestion.get("confidence")
    if confidence is None or confidence == "":
        return "unknown confidence"
    try:
        return "%d%% confidence" % round(float(confidence) * 100)
    except (TypeError, ValueError):
        return "%s confidence" % confidence


def render_methodology_page(summary: Dict[str, Any]) -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Methodology - Civic Data Health</title>
  <style>
    :root {{ color-scheme: light; --ink:#18212f; --muted:#5f6b7a; --line:#d8dee8; --bg:#f4f6f8; --panel:#ffffff; --accent:#0f5f7a; }}
    body {{ margin:0; font-family: Georgia, "Times New Roman", serif; color:var(--ink); background:var(--bg); }}
    main {{ max-width:940px; margin:0 auto; padding:28px 18px 44px; }}
    a {{ color:var(--accent); }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:18px; margin:14px 0; }}
    .muted {{ color:var(--muted); }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    li {{ margin:7px 0; }}
  </style>
</head>
<body>
  <main>
    <p><a href="index.html">Back to report</a> | <a href="help.html">Connect to ChatGPT</a></p>
    <h1>Methodology</h1>
    <div class="panel">
      <h2>Classification First</h2>
      <p>Each catalog record is classified before risk ranking. Active datasets are the only records promoted into the operational high-risk queue. Archives, event-specific records, Socrata measures, and story/reference assets remain visible but do not receive active freshness expectations.</p>
      <ul>
        <li><code>active_dataset</code>: ongoing machine-readable data or records with clear cadence evidence.</li>
        <li><code>needs_manual_review</code>: dated records without enough cadence or asset evidence for automatic classification.</li>
        <li><code>archive_snapshot</code>: month, quarter, year, or bounded-year snapshots.</li>
        <li><code>event_specific</code>: records tied to a specific incident or event.</li>
        <li><code>measure</code>: Socrata measure or indicator assets.</li>
        <li><code>story_reference</code>: Socrata stories, files, links, and other reference assets.</li>
      </ul>
    </div>
    <div class="panel">
      <h2>Evidence Codes</h2>
      <p>Classification evidence is stored on every row and exported to JSON, CSV, detail pages, and MCP tools.</p>
      <ul>
        <li><code>known_cadence</code>: <code>accrualPeriodicity</code> is present.</li>
        <li><code>machine_readable_distribution</code>: a distribution exposes <code>downloadURL</code> or <code>accessURL</code>.</li>
        <li><code>socrata_story_asset</code>, <code>socrata_measure_asset</code>, <code>socrata_reference_asset</code>: Socrata view metadata identifies a non-table asset.</li>
        <li><code>month_quarter_snapshot</code>: title or description names a dated month, quarter, or month range.</li>
        <li><code>bounded_year_range</code>: title or description names a single year or bounded year range with snapshot/statistics language.</li>
        <li><code>event_keyword</code>: title or description names an incident such as a flood, storm, hurricane, or pandemic.</li>
      </ul>
    </div>
    <div class="panel">
      <h2>Scoring</h2>
      <p>Scores start at 100. Missing modified dates, weak descriptions, missing owner/contact metadata, and missing license/category/tags reduce the score. Known-cadence datasets get a full stale penalty when modified dates are past 1.5x the expected period. Unknown-cadence active records get only a low-confidence freshness issue.</p>
      <p>Active-like records without a distribution or machine-readable URL are hard-labelled high risk. Archive, event, measure, and reference records keep those issues visible but are not promoted into the active high-risk queue.</p>
    </div>
    <div class="panel">
      <h2>Category Suggestions</h2>
      <p>Records with missing categories receive a trained suggestion when the current catalog has enough labeled examples. The model uses title, description, tags, publisher/contact text, and Socrata asset type. Suggestions are review hints only and do not overwrite City of Austin catalog metadata.</p>
    </div>
    <div class="panel">
      <h2>Manual Overrides</h2>
      <p>Manual corrections live in <code>classification_overrides.json</code>. Each override must name a Socrata dataset id and one allowed classification group. Override evidence is exported with <code>manual_override</code> so demo reviewers can see which calls were human-reviewed.</p>
      <p class="muted">Run {run_id}, fetched {fetched_at}. {footer}</p>
    </div>
  </main>
</body>
</html>
""".format(
        run_id=summary["run_id"],
        fetched_at=escape(summary["fetched_at"]),
        footer=escape(FOOTER),
    )


def render_help_page(summary: Dict[str, Any]) -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Connect to ChatGPT - Civic Data Health</title>
  <style>
    :root {{ color-scheme: light; --ink:#18212f; --muted:#5f6b7a; --line:#d8dee8; --bg:#f4f6f8; --panel:#ffffff; --accent:#0f5f7a; --soft:#e8eef2; }}
    body {{ margin:0; font-family: Georgia, "Times New Roman", serif; color:var(--ink); background:var(--bg); }}
    header {{ background:var(--soft); border-bottom:1px solid var(--line); }}
    main {{ max-width:940px; margin:0 auto; padding:28px 18px 44px; }}
    h1 {{ margin:0 0 10px; font-size:clamp(30px, 5vw, 48px); letter-spacing:0; }}
    h2 {{ margin:0 0 10px; }}
    p {{ line-height:1.5; }}
    a {{ color:var(--accent); }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:18px; margin:14px 0; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; }}
    .muted {{ color:var(--muted); }}
    code, pre {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    pre {{ overflow:auto; background:#101820; color:#f7fbff; border-radius:8px; padding:14px; }}
    li {{ margin:8px 0; }}
    .endpoint {{ display:block; font-size:16px; margin-top:6px; word-break:break-all; }}
  </style>
</head>
<body>
  <header>
    <main>
      <p><a href="index.html">Back to report</a> | <a href="methodology.html">Methodology</a></p>
      <h1>Connect Civic Data Health to ChatGPT</h1>
      <p>This page is for a live demo. The MCP server is public, HTTPS, and read-only, so ChatGPT can connect to it directly without a localhost tunnel.</p>
    </main>
  </header>
  <main>
    <div class="panel grid">
      <div>
        <h2>MCP URL</h2>
        <code class="endpoint">{mcp_url}</code>
      </div>
      <div>
        <h2>Health Check</h2>
        <code class="endpoint">{mcp_url}/health</code>
      </div>
      <div>
        <h2>Public Report</h2>
        <code class="endpoint">{site_url}/</code>
      </div>
    </div>
    <div class="panel">
      <h2>ChatGPT Setup</h2>
      <ol>
        <li>Open ChatGPT web and go to <strong>Settings -&gt; Apps &amp; Connectors -&gt; Advanced settings</strong>.</li>
        <li>Turn on <strong>Developer mode</strong>. If your workspace disables it, an admin needs to allow developer mode first.</li>
        <li>Go back to <strong>Settings -&gt; Apps &amp; Connectors</strong> and click <strong>Create</strong>.</li>
        <li>Use <strong>Civic Data Health</strong> as the connector name.</li>
        <li>Use this description: <em>Ask questions about Austin open data, find relevant datasets, inspect dataset health, schemas, sample rows, and data quality issues.</em></li>
        <li>Use <code>{mcp_url}</code> as the connector URL.</li>
        <li>Use no authentication for the demo. This server only exposes public, read-only Austin open data tools.</li>
        <li>Click <strong>Create</strong>. ChatGPT should show the tool list advertised by the MCP server.</li>
      </ol>
    </div>
    <div class="panel">
      <h2>Demo Prompts</h2>
      <ul>
        <li>Find Austin datasets about building permits and tell me which one is best for answering permit volume questions.</li>
        <li>How many building permits were issued in 2025?</li>
        <li>Which active Austin datasets have the most actionable metadata fixes?</li>
        <li>Find datasets related to homelessness services and show data quality caveats.</li>
        <li>Show the schema and a few sample rows for a relevant public safety dataset.</li>
      </ul>
    </div>
    <div class="panel">
      <h2>Smoke Test</h2>
      <p>If ChatGPT cannot create the connector, verify the endpoint from a terminal:</p>
      <pre>curl {mcp_url}/health

curl -sS -X POST {mcp_url} \\
  -H 'content-type: application/json' \\
  -H 'accept: application/json, text/event-stream' \\
  --data '{{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{{}}}}'</pre>
      <p class="muted">MCP tool probes need the <code>Accept: application/json, text/event-stream</code> header. ChatGPT also requires a public HTTPS endpoint; <code>localhost</code> is not reachable from ChatGPT web.</p>
    </div>
    <div class="panel">
      <h2>After Changes</h2>
      <p>When tools, descriptions, or schemas change, redeploy this server and refresh the connector metadata in ChatGPT under <strong>Settings -&gt; Apps &amp; Connectors</strong>.</p>
      <p>Official setup reference: <a href="{docs_url}">OpenAI Apps SDK - Connect from ChatGPT</a>.</p>
      <p class="muted">Run {run_id}, fetched {fetched_at}. {footer}</p>
    </div>
  </main>
</body>
</html>
""".format(
        mcp_url=escape(PUBLIC_MCP_URL),
        site_url=escape(PUBLIC_SITE_URL),
        docs_url=escape(OPENAI_CONNECT_DOC_URL),
        run_id=summary["run_id"],
        fetched_at=escape(summary["fetched_at"]),
        footer=escape(FOOTER),
    )


def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)
