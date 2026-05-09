from __future__ import annotations

import csv
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .analysis import asset_group, asset_group_label, summarize_asset_groups, top_actionable_fixes
from .storage import connect, latest_run_id, report_rows, run_summary, skipped_rows

FOOTER = "Independent analysis using public City of Austin open data. Not affiliated with or endorsed by the City of Austin."
SECTION_ORDER = ("active_dataset", "measure", "story_reference")


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
    detail_dir = out_dir / "datasets"

    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "summary": summary,
        "asset_groups": summarize_asset_groups(rows),
        "skipped_records": skipped,
        "datasets": rows,
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_csv(csv_path, rows)
    write_detail_pages(detail_dir, summary, rows)
    html_text = render_html(summary, rows, skipped)
    html_path.write_text(html_text, encoding="utf-8")
    index_path.write_text(html_text, encoding="utf-8")

    return {
        "json": str(json_path),
        "csv": str(csv_path),
        "html": str(html_path),
        "index": str(index_path),
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
        "landing_url",
        "machine_url",
        "asset_type",
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
                    "landing_url": row["landing_url"],
                    "machine_url": row["machine_url"],
                    "asset_type": row.get("asset_type") or "",
                    "remediation": " ".join(row["remediation"]),
                }
            )


def render_html(summary: Dict[str, Any], rows, skipped) -> str:
    group_summary = summarize_asset_groups(rows)
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
    if not actionable_markup:
        actionable_markup = '<tr><td colspan="6">No active dataset fixes are currently ranked above the review threshold.</td></tr>'
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
      <p>Austin Open Data metadata audit generated from the public DCAT catalog. Socrata story, measure, and reference assets are separated from active dataset risk.</p>
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
      </div>
      <nav class="tabs" aria-label="Report sections">
        <a href="#active_dataset">Active datasets</a>
        <a href="#measure">Measures and indicators</a>
        <a href="#story_reference">Stories and reference</a>
        <a href="#actionable">Top fix opportunities</a>
      </nav>
    </main>
  </header>
  <main>
    <h2>Catalog Sections</h2>
    <p class="section-note">Active datasets are ranked separately from Socrata measures, story pages, and reference assets so one-time events and indicators do not distort the operational risk queue.</p>
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
        high_risk=summary["labels"]["high_risk"],
        needs_review=summary["labels"]["needs_review"],
        good=summary["labels"]["good"],
        skipped=summary["skipped_records"],
        average=summary["average_score"],
        group_metrics=group_markup,
        actionable_rows=actionable_markup,
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
    <thead><tr><th>Dataset</th><th>Score</th><th>Label</th><th>Asset</th><th>Modified</th><th>Owner</th><th>Issues</th><th>Remediation</th></tr></thead>
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


def render_dataset_row(row: Dict[str, Any]) -> str:
    remediation = " ".join(row["remediation"])
    owner = row["publisher"] or row["contact"] or "Missing"
    title = escape(row["title"] or row["dataset_id"])
    detail_href = "datasets/%s.html" % escape(row["dataset_id"])
    title = '<a href="{url}">{title}</a>'.format(url=detail_href, title=title)
    return """<tr>
  <td data-label="Dataset" class="title">{title}<div class="issues">{dataset_id}</div></td>
  <td data-label="Score">{score}</td>
  <td data-label="Label" class="label {label}">{label}</td>
  <td data-label="Asset">{asset_type}</td>
  <td data-label="Modified">{modified}</td>
  <td data-label="Owner">{owner}</td>
  <td data-label="Issues" class="issues">{issues}</td>
  <td data-label="Remediation">{remediation}</td>
</tr>""".format(
        title=title,
        dataset_id=escape(row["dataset_id"]),
        score=row["score"],
        label=escape(row["label"]),
        asset_type=escape(row.get("asset_type") or "dataset"),
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
    landing = row.get("landing_url") or ""
    machine = row.get("machine_url") or ""
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
      <p><strong>Owner:</strong> {owner}</p>
      <p><strong>Contact:</strong> {contact}</p>
      <p><strong>Category:</strong> {category}</p>
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
        asset=escape(row.get("asset_type") or "dataset"),
        modified=escape(row.get("modified") or "Missing"),
        issues=issue_items,
        remediation=remediation_items,
        dataset_id=escape(row["dataset_id"]),
        owner=escape(row.get("publisher") or "Missing"),
        contact=escape(row.get("contact") or "Missing"),
        category=escape(row.get("category") or "Missing"),
        license=escape(row.get("license") or "Missing"),
        landing=('<a href="%s">%s</a>' % (escape(landing), escape(landing))) if landing else "Missing",
        machine=('<a href="%s">%s</a>' % (escape(machine), escape(machine))) if machine else "Missing",
        run_id=summary["run_id"],
        fetched_at=escape(summary["fetched_at"]),
    )


def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)
