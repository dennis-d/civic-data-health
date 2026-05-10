from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from typing_extensions import TypedDict

from . import __version__
from .analysis import (
    asset_group,
    asset_group_label,
    draft_department_email as build_department_email,
    explain_dataset_issues,
    filter_by_asset_group,
    summarize_asset_groups,
    top_actionable_fixes,
)
from .capabilities import find_answerable, get_capabilities_for_row, search_columns
from .category_suggestions import rows_with_category_suggestions
from .discovery import answer_city_data_question, find_city_datasets
from .public_catalog import PUBLIC_CATALOGS, search_government_resources, search_public_catalogs
from .row_answer import answer_row_level_question, build_date_where, DateRange
from .socrata import (
    count_rows,
    fetch_view_metadata,
    get_dataset_schema as load_socrata_schema,
    get_sample_rows as load_socrata_sample_rows,
    query_rows as load_socrata_query_rows,
    simplify_schema,
)
from .storage import connect, latest_run_id, report_rows, run_summary

AssetGroupArg = Literal["active_dataset", "needs_manual_review", "archive_snapshot", "event_specific", "measure", "story_reference", "all"]
LabelArg = Literal["high_risk", "needs_review", "good", "all"]
JurisdictionArg = Literal["all", "texas", "austin"]
CatalogSourceArg = Literal["texas", "austin"]


class SearchResult(TypedDict):
    id: str
    title: str
    url: str


class SearchOutput(TypedDict):
    results: List[SearchResult]


class FetchOutput(TypedDict):
    id: str
    title: str
    text: str
    url: str
    metadata: Dict[str, str]


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def create_mcp(db_path: Path, host: str, port: int) -> FastMCP:
    mcp = FastMCP(
        name="civic-data-health",
        instructions=(
            "Read-only Texas and Austin public government data helper. Use these tools "
            "to find public datasets, fetch bounded public rows, summarize Austin dataset "
            "health, and route permit or government-service questions to official sources."
        ),
        website_url="https://civic.pagonya.co/",
        host=host,
        port=port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
    )

    @mcp.custom_route("/mcp/health", methods=["GET"])
    async def health(_request: Request) -> Response:
        return JSONResponse({"ok": True, "service": "civic-data-health-mcp", "version": __version__})

    @mcp.tool(
        title="Get Report Summary",
        description="Use this when you need the latest Austin civic data health summary and top risks.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def get_report_summary() -> Dict[str, Any]:
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            rows = report_rows(conn, run_id)
            groups = summarize_asset_groups(rows)
            return {
                "summary": run_summary(conn, run_id),
                "classification_groups": groups,
                "asset_groups": groups,
                "top_actionable_fixes": top_actionable_fixes(rows, limit=10, group="active_dataset"),
                "top_risks": [row for row in rows if row["label"] == "high_risk" and asset_group(row) == "active_dataset"][:10],
            }

    @mcp.tool(
        title="List High Risk Datasets",
        description="Use this when you need the highest-risk active datasets from the latest report.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def list_high_risk_datasets(limit: int = 20) -> Dict[str, Any]:
        safe_limit = clamp_limit(limit)
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            rows = [row for row in report_rows(conn, run_id) if row["label"] == "high_risk" and asset_group(row) == "active_dataset"]
            return {"run_id": run_id, "datasets": rows[:safe_limit]}

    @mcp.tool(
        title="Get Top Actionable Fixes",
        description="Use this when you need the highest-impact metadata cleanup opportunities for a city data steward.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def get_top_actionable_fixes(limit: int = 25, asset_group: AssetGroupArg = "active_dataset") -> Dict[str, Any]:
        safe_limit = clamp_limit(limit)
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            rows = report_rows(conn, run_id)
            return {
                "run_id": run_id,
                "asset_group": asset_group,
                "asset_group_label": asset_group_label(asset_group),
                "fixes": top_actionable_fixes(rows, limit=safe_limit, group=asset_group),
            }

    @mcp.tool(
        title="Compare Asset Types",
        description="Use this when you need to compare active datasets, archives, event records, Socrata measures, and story/reference assets.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def compare_asset_types() -> Dict[str, Any]:
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            rows = report_rows(conn, run_id)
            groups = summarize_asset_groups(rows)
            return {"run_id": run_id, "classification_groups": groups, "asset_groups": groups}

    @mcp.tool(
        title="List Classification Review Candidates",
        description="Use this when you need records that require human classification before they are treated as active risks.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def list_classification_review_candidates(limit: int = 25) -> Dict[str, Any]:
        safe_limit = clamp_limit(limit)
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            rows = filter_by_asset_group(report_rows(conn, run_id), "needs_manual_review")
            return {"run_id": run_id, "datasets": rows[:safe_limit]}

    @mcp.tool(
        title="Get Classification Methodology",
        description="Use this when you need to explain how the report classifies active datasets, archives, events, measures, and story assets.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def get_classification_methodology() -> Dict[str, Any]:
        return {
            "groups": {
                "active_dataset": "Ongoing machine-readable data or records with clear active-dataset evidence.",
                "needs_manual_review": "Dated records without enough cadence or asset evidence for automatic classification.",
                "archive_snapshot": "Month, quarter, year, or bounded-year snapshots.",
                "event_specific": "Records tied to a specific incident or event.",
                "measure": "Socrata measure or indicator assets.",
                "story_reference": "Socrata stories, files, links, and other reference assets.",
            },
            "evidence_codes": {
                "known_cadence": "accrualPeriodicity is present.",
                "machine_readable_distribution": "A distribution exposes downloadURL or accessURL.",
                "socrata_story_asset": "Socrata view metadata identifies a story page.",
                "socrata_measure_asset": "Socrata view metadata identifies a measure asset.",
                "socrata_reference_asset": "Socrata view metadata identifies another non-table reference asset.",
                "month_quarter_snapshot": "Title or description names a dated month, quarter, or month range.",
                "bounded_year_range": "Title or description names a single year or bounded year range with snapshot/statistics language.",
                "event_keyword": "Title or description names an incident such as a flood, storm, hurricane, or pandemic.",
                "manual_override": "classification_overrides.json supplied a human-reviewed classification.",
            },
            "hard_override": "Active-like records with no distribution or no downloadURL/accessURL are labelled high_risk.",
            "methodology_url": "https://civic.pagonya.co/methodology.html",
        }

    @mcp.tool(
        title="List Datasets By Asset Group",
        description="Use this when you need examples from one report section, optionally filtered by label.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def list_datasets_by_asset_group(
        asset_group: AssetGroupArg = "active_dataset",
        label: LabelArg = "needs_review",
        limit: int = 20,
    ) -> Dict[str, Any]:
        safe_limit = clamp_limit(limit)
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            rows = filter_by_asset_group(report_rows(conn, run_id), asset_group)
            if label != "all":
                rows = [row for row in rows if row["label"] == label]
            return {
                "run_id": run_id,
                "asset_group": asset_group,
                "asset_group_label": asset_group_label(asset_group),
                "label": label,
                "datasets": rows[:safe_limit],
            }

    @mcp.tool(
        title="Get Dataset Health",
        description="Use this when you have a Socrata dataset id and need its score, issue codes, and remediation.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def get_dataset_health(dataset_id: str) -> Dict[str, Any]:
        normalized_id = dataset_id.strip().lower()
        if not normalized_id:
            raise ValueError("dataset_id is required")
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            row = find_dataset(report_rows(conn, run_id), normalized_id)
            if row:
                return {"run_id": run_id, "dataset": row}
        return {"run_id": run_id, "dataset": None, "message": "Dataset id not found in latest run."}

    @mcp.tool(
        title="Suggest Dataset Category",
        description="Use this when a dataset has a missing category and you need the trained category suggestion with evidence.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def suggest_dataset_category(dataset_id: str) -> Dict[str, Any]:
        normalized_id = dataset_id.strip().lower()
        if not normalized_id:
            raise ValueError("dataset_id is required")
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            row = find_dataset(report_rows(conn, run_id), normalized_id)
            if row is None:
                raise ValueError("Dataset id not found in latest run: %s" % normalized_id)
            return {
                "run_id": run_id,
                "dataset_id": row["dataset_id"],
                "title": row["title"],
                "catalog_category": row.get("category") or "",
                "keywords": row.get("keywords") or [],
                "category_suggestion": row.get("category_suggestion") or {},
            }

    @mcp.tool(
        title="List Missing Category Suggestions",
        description="Use this when you need missing-category records with trained category suggestions, confidence, and evidence.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def list_missing_category_suggestions(limit: int = 25) -> Dict[str, Any]:
        safe_limit = clamp_limit(limit)
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            rows = rows_with_category_suggestions(report_rows(conn, run_id), limit=safe_limit)
            return {
                "run_id": run_id,
                "datasets": [
                    {
                        "dataset_id": row["dataset_id"],
                        "title": row["title"],
                        "label": row["label"],
                        "issue_codes": row.get("issue_codes") or [],
                        "keywords": row.get("keywords") or [],
                        "landing_url": row.get("landing_url") or "",
                        "category_suggestion": row.get("category_suggestion") or {},
                    }
                    for row in rows
                ],
            }

    @mcp.tool(
        title="Explain Dataset Issue",
        description="Use this when you need plain-English explanations and recommended actions for one dataset's issue codes.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def explain_dataset_issue(dataset_id: str, issue_code: Optional[str] = None) -> Dict[str, Any]:
        normalized_id = dataset_id.strip().lower()
        if not normalized_id:
            raise ValueError("dataset_id is required")
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            row = find_dataset(report_rows(conn, run_id), normalized_id)
            if row is None:
                raise ValueError("Dataset id not found in latest run: %s" % normalized_id)
            return {"run_id": run_id, "explanation": explain_dataset_issues(row, issue_code)}

    @mcp.tool(
        title="Draft Department Email",
        description="Use this when you need a draft outreach email for a department owner; this only drafts text and does not send anything.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def draft_department_email(dataset_id: str, contact_name: str = "", sender_name: str = "") -> Dict[str, Any]:
        normalized_id = dataset_id.strip().lower()
        if not normalized_id:
            raise ValueError("dataset_id is required")
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            row = find_dataset(report_rows(conn, run_id), normalized_id)
            if row is None:
                raise ValueError("Dataset id not found in latest run: %s" % normalized_id)
            return {"run_id": run_id, "dataset_id": row["dataset_id"], "draft": build_department_email(row, contact_name=contact_name, sender_name=sender_name)}

    @mcp.tool(
        title="Search Datasets",
        description="Use this when you need to search Austin report rows by title, description, id, asset type, or issue code.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def search_datasets(query: str, limit: int = 20) -> Dict[str, Any]:
        return {"run_id": _latest_run_id(db_path), "query": query, "datasets": search_report(db_path, query, clamp_limit(limit))}

    @mcp.tool(
        title="Ask City Data Question",
        description="Use this when a person asks a plain-English question and needs the best Austin open datasets to answer it.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def ask_city_data_question(question: str, limit: int = 8) -> Dict[str, Any]:
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question is required")
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            rows = report_rows(conn, run_id)
            row_answer = answer_row_level_question(conn, rows, normalized_question)
            if row_answer is not None:
                return {"run_id": run_id, **row_answer}
            answer = answer_city_data_question(rows, normalized_question, limit=clamp_limit(limit))
            return {"run_id": run_id, **answer}

    @mcp.tool(
        title="Ask Texas Government Question",
        description="Use this when a person asks for State of Texas or Austin government data, permit starting points, licenses, public services, governance information, or dataset-backed examples.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def ask_texas_government_question(
        question: str,
        jurisdiction: JurisdictionArg = "all",
        limit: int = 5,
        include_rows: bool = True,
    ) -> Dict[str, Any]:
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question is required")
        return answer_public_government_question(normalized_question, jurisdiction=jurisdiction, limit=limit, include_rows=include_rows)

    @mcp.tool(
        title="Ask Civic Data Question",
        description="Use this when a person asks for Texas or Austin service, permit, governance, or open-data information and needs official links plus dataset-backed public rows.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def ask_civic_data_question(question: str, limit: int = 5, include_rows: bool = True) -> Dict[str, Any]:
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question is required")
        return answer_public_government_question(normalized_question, jurisdiction="all", limit=limit, include_rows=include_rows)

    @mcp.tool(
        title="Search Public Data Catalogs",
        description="Use this when you need matching State of Texas or Austin public open-data catalog records for a topic, service, permit, agency, or governance question.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def search_public_data_catalogs(query: str, jurisdiction: JurisdictionArg = "all", limit: int = 10) -> Dict[str, Any]:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query is required")
        return {
            "query": normalized_query,
            "source_scope": public_source_scope(jurisdiction),
            "datasets": search_public_catalogs(normalized_query, jurisdiction=jurisdiction, limit=clamp_limit(limit)),
        }

    @mcp.tool(
        title="Find Government Service Resources",
        description="Use this when a person asks where to start a Texas or Austin permit, license, business, or government-service process.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def find_government_service_resources(query: str, jurisdiction: JurisdictionArg = "all", limit: int = 8) -> Dict[str, Any]:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query is required")
        return {
            "query": normalized_query,
            "source_scope": public_source_scope(jurisdiction),
            "resources": search_government_resources(normalized_query, jurisdiction=jurisdiction, limit=clamp_limit(limit)),
        }

    @mcp.tool(
        title="Query Public Dataset Rows",
        description="Use this when you need actual public rows from a known State of Texas or Austin Socrata dataset. This is read-only, validates selected columns, and returns a bounded row set.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def query_public_dataset_rows(
        source: CatalogSourceArg,
        dataset_id: str,
        limit: int = 10,
        columns: str = "",
        date_column: str = "",
        start: str = "",
        end: str = "",
        search: str = "",
    ) -> Dict[str, Any]:
        normalized_id = dataset_id.strip().lower()
        if not normalized_id:
            raise ValueError("dataset_id is required")
        safe_limit = max(1, min(int(limit or 10), 50))
        source_info = PUBLIC_CATALOGS[source]
        schema = load_public_schema(normalized_id, source_info["socrata_domain"])
        selected_columns = parse_column_list(columns)
        valid_columns = {column["field_name"] for column in schema["columns"]}
        unknown_columns = [column for column in selected_columns if column not in valid_columns]
        if unknown_columns:
            raise ValueError("columns are not present in schema: %s" % ", ".join(unknown_columns))
        where = ""
        if bool(start.strip()) != bool(end.strip()):
            raise ValueError("start and end must be supplied together")
        if start.strip() and end.strip():
            if not date_column.strip():
                raise ValueError("date_column is required when start/end are supplied")
            if date_column.strip() not in valid_columns:
                raise ValueError("date_column is not present in schema: %s" % date_column)
            where = build_date_where(date_column.strip(), DateRange("custom", start.strip(), end.strip())) or ""
        rows = load_socrata_query_rows(
            normalized_id,
            limit=safe_limit,
            select_columns=selected_columns or None,
            where=where or None,
            search=search,
            domain=source_info["socrata_domain"],
        )
        return {
            "source": source,
            "jurisdiction": source_info["jurisdiction"],
            "dataset_id": normalized_id,
            "schema": schema,
            "query": {
                "limit": safe_limit,
                "columns": selected_columns,
                "date_column": date_column.strip(),
                "where": where,
                "search": " ".join(search.split()),
            },
            "rows": rows,
            "row_count": len(rows),
            "source_url": "https://%s/resource/%s.json" % (source_info["socrata_domain"], normalized_id),
        }

    @mcp.tool(
        title="Ask Austin Data Question",
        description="Use this when a person specifically asks an Austin open-data question and needs Austin report ranking, schema checks, and bounded live public rows.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def ask_austin_data_question(question: str, limit: int = 3, sample_rows: int = 5) -> Dict[str, Any]:
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question is required")
        safe_limit = max(1, min(int(limit or 3), 5))
        safe_sample_rows = max(1, min(int(sample_rows or 5), 10))
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            rows = report_rows(conn, run_id)
            row_answer = answer_row_level_question(conn, rows, normalized_question)
            if row_answer is not None:
                return {"run_id": run_id, "source_scope": public_source_scope("austin"), **row_answer}
            answerable = find_answerable(conn, rows, normalized_question, limit=safe_limit)
            packages = []
            errors = []
            for candidate in answerable["datasets"]:
                if not candidate["answerable"]:
                    continue
                row = find_dataset(rows, candidate["dataset_id"])
                if row is None or asset_group(row) != "active_dataset" or not row.get("machine_url"):
                    continue
                try:
                    live_rows = load_socrata_query_rows(row["dataset_id"], limit=safe_sample_rows)
                except Exception as exc:
                    errors.append({"dataset_id": candidate["dataset_id"], "reason": str(exc)})
                    continue
                packages.append(
                    {
                        "dataset": dataset_brief(row),
                        "why": candidate["why"],
                        "matched_columns": candidate["matched_columns"],
                        "capabilities": candidate["capabilities"],
                        "rows": live_rows,
                        "row_count": len(live_rows),
                        "source": "https://data.austintexas.gov/resource/%s.json" % row["dataset_id"],
                    }
                )
                if len(packages) >= safe_limit:
                    break
            return {
                "run_id": run_id,
                "question": normalized_question,
                "answer": "I found Austin open-data candidates and included bounded live public rows for dataset-backed analysis."
                if packages
                else "I found candidate Austin datasets, but no live row sample could be retrieved for the strongest matches.",
                "source_scope": public_source_scope("austin"),
                "requires": answerable["requires"],
                "datasets": answerable["datasets"],
                "data_packages": packages,
                "row_errors": errors,
                "method": "Ranked Austin catalog matches, inspected Socrata schemas, and fetched bounded live public rows from answerable datasets.",
            }

    @mcp.tool(
        title="Find City Datasets",
        description="Use this when you need ranked Austin open datasets for a civic topic, service, department, or question.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def find_city_datasets_for_question(question: str, limit: int = 10) -> Dict[str, Any]:
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question is required")
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            matches = find_city_datasets(report_rows(conn, run_id), normalized_question, limit=clamp_limit(limit))
            return {
                "run_id": run_id,
                "question": normalized_question,
                "datasets": [match.to_result() for match in matches],
            }

    @mcp.tool(
        title="Get Dataset Capabilities",
        description="Use this when you need to know whether a dataset has date, geography, numeric, text, or categorical fields.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def get_dataset_capabilities(dataset_id: str) -> Dict[str, Any]:
        normalized_id = dataset_id.strip().lower()
        if not normalized_id:
            raise ValueError("dataset_id is required")
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            row = find_dataset(report_rows(conn, run_id), normalized_id)
            if row is None:
                raise ValueError("Dataset id not found in latest run: %s" % normalized_id)
            return {"run_id": run_id, "capabilities": get_capabilities_for_row(conn, row)}

    @mcp.tool(
        title="Search Dataset Columns",
        description="Use this when you need datasets whose schema has fields like council district, issue date, latitude, status, amount, or permit type.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def search_dataset_columns(query: str, limit: int = 20) -> Dict[str, Any]:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query is required")
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            result = search_columns(conn, report_rows(conn, run_id), normalized_query, limit=clamp_limit(limit))
            return {"run_id": run_id, **result}

    @mcp.tool(
        title="Find Answerable Datasets",
        description="Use this when you need datasets that can answer a question based on schema capabilities like date, geography, and count support.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def find_answerable_datasets(question: str, limit: int = 8) -> Dict[str, Any]:
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question is required")
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            result = find_answerable(conn, report_rows(conn, run_id), normalized_question, limit=clamp_limit(limit))
            return {"run_id": run_id, **result}

    @mcp.tool(
        title="Search City Knowledge",
        description="Use this for a combined city-data knowledge search over catalog records and matching dataset columns.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def search_city_knowledge(query: str, limit: int = 10) -> Dict[str, Any]:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query is required")
        safe_limit = clamp_limit(limit)
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            rows = report_rows(conn, run_id)
            dataset_matches = [match.to_result() for match in find_city_datasets(rows, normalized_query, limit=safe_limit)]
            column_result = search_columns(conn, rows, normalized_query, limit=safe_limit, candidate_limit=safe_limit)
            return {
                "run_id": run_id,
                "query": normalized_query,
                "datasets": dataset_matches,
                "column_matches": column_result["matches"],
                "inspected": column_result["inspected"],
                "method": "Combined catalog search with on-demand Socrata schema search.",
            }

    @mcp.tool(
        title="Fetch City Knowledge",
        description="Use this when you need the full health, classification, category suggestion, and schema capabilities for one city dataset.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def fetch_city_knowledge(id: str) -> Dict[str, Any]:
        normalized_id = id.strip().lower()
        if not normalized_id:
            raise ValueError("id is required")
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            row = find_dataset(report_rows(conn, run_id), normalized_id)
            if row is None:
                raise ValueError("Dataset id not found in latest run: %s" % normalized_id)
            capabilities = None
            schema_status = "not_checked"
            if asset_group(row) == "active_dataset" and row.get("machine_url"):
                capabilities = get_capabilities_for_row(conn, row)
                schema_status = "checked"
            else:
                schema_status = "skipped: not an active machine-readable dataset"
            return {
                "run_id": run_id,
                "id": row["dataset_id"],
                "title": row["title"],
                "url": dataset_url(row),
                "dataset": row,
                "schema_status": schema_status,
                "capabilities": capabilities,
                "recommended_tools": [
                    "get_dataset_health",
                    "get_dataset_schema",
                    "get_sample_rows",
                    "query_dataset_count",
                ]
                if capabilities
                else ["get_dataset_health"],
            }

    @mcp.tool(
        title="Get Dataset Schema",
        description="Use this when you need column names and types for a known Austin Socrata dataset id.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def get_dataset_schema(dataset_id: str) -> Dict[str, Any]:
        normalized_id = dataset_id.strip().lower()
        if not normalized_id:
            raise ValueError("dataset_id is required")
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            row = find_dataset(report_rows(conn, run_id), normalized_id)
            if row is None:
                raise ValueError("Dataset id not found in latest run: %s" % normalized_id)
            return {"run_id": run_id, "schema": load_socrata_schema(conn, normalized_id, row.get("modified"))}

    @mcp.tool(
        title="Get Sample Rows",
        description="Use this when you need a small live sample from a known Austin Socrata dataset id.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def get_sample_rows(dataset_id: str, limit: int = 5) -> Dict[str, Any]:
        normalized_id = dataset_id.strip().lower()
        if not normalized_id:
            raise ValueError("dataset_id is required")
        safe_limit = max(1, min(int(limit or 5), 20))
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            row = find_dataset(report_rows(conn, run_id), normalized_id)
            if row is None:
                raise ValueError("Dataset id not found in latest run: %s" % normalized_id)
            return {
                "run_id": run_id,
                "dataset": {"dataset_id": row["dataset_id"], "title": row["title"], "label": row["label"], "classification": row.get("classification") or {}},
                "rows": load_socrata_sample_rows(normalized_id, safe_limit),
            }

    @mcp.tool(
        title="Query Dataset Rows",
        description="Use this when you need actual public rows from a known Austin Socrata dataset for a service, governance, or operational question. This is read-only, validates selected columns, and returns a bounded row set.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def query_dataset_rows(
        dataset_id: str,
        limit: int = 10,
        columns: str = "",
        date_column: str = "",
        start: str = "",
        end: str = "",
        search: str = "",
    ) -> Dict[str, Any]:
        normalized_id = dataset_id.strip().lower()
        if not normalized_id:
            raise ValueError("dataset_id is required")
        safe_limit = max(1, min(int(limit or 10), 50))
        if bool(start.strip()) != bool(end.strip()):
            raise ValueError("start and end must be supplied together")
        selected_columns = parse_column_list(columns)
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            row = find_dataset(report_rows(conn, run_id), normalized_id)
            if row is None:
                raise ValueError("Dataset id not found in latest run: %s" % normalized_id)
            schema = load_socrata_schema(conn, normalized_id, row.get("modified"))
        valid_columns = {column["field_name"] for column in schema["columns"]}
        unknown_columns = [column for column in selected_columns if column not in valid_columns]
        if unknown_columns:
            raise ValueError("columns are not present in schema: %s" % ", ".join(unknown_columns))
        where = ""
        if start.strip() and end.strip():
            if not date_column.strip():
                raise ValueError("date_column is required when start/end are supplied")
            if date_column.strip() not in valid_columns:
                raise ValueError("date_column is not present in schema: %s" % date_column)
            where = build_date_where(date_column.strip(), DateRange("custom", start.strip(), end.strip())) or ""
        rows = load_socrata_query_rows(
            normalized_id,
            limit=safe_limit,
            select_columns=selected_columns or None,
            where=where or None,
            search=search,
        )
        return {
            "run_id": run_id,
            "dataset": {"dataset_id": row["dataset_id"], "title": row["title"], "label": row["label"], "url": dataset_url(row)},
            "query": {
                "limit": safe_limit,
                "columns": selected_columns,
                "date_column": date_column.strip(),
                "where": where,
                "search": " ".join(search.split()),
            },
            "rows": rows,
            "row_count": len(rows),
            "source": "https://data.austintexas.gov/resource/%s.json" % normalized_id,
        }

    @mcp.tool(
        title="Query Dataset Count",
        description="Use this for a safe read-only count over one known Austin Socrata dataset, optionally bounded by a validated date column.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def query_dataset_count(dataset_id: str, date_column: str = "", start: str = "", end: str = "") -> Dict[str, Any]:
        normalized_id = dataset_id.strip().lower()
        if not normalized_id:
            raise ValueError("dataset_id is required")
        if bool(start.strip()) != bool(end.strip()):
            raise ValueError("start and end must be supplied together")
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            row = find_dataset(report_rows(conn, run_id), normalized_id)
            if row is None:
                raise ValueError("Dataset id not found in latest run: %s" % normalized_id)
            schema = load_socrata_schema(conn, normalized_id, row.get("modified"))
        where = ""
        if start.strip() and end.strip():
            if not date_column.strip():
                raise ValueError("date_column is required when start/end are supplied")
            field_names = {column["field_name"] for column in schema["columns"]}
            if date_column.strip() not in field_names:
                raise ValueError("date_column is not present in schema: %s" % date_column)
            where = build_date_where(date_column.strip(), DateRange("custom", start.strip(), end.strip())) or ""
        count = count_rows(normalized_id, where or None)
        return {
            "run_id": run_id,
            "dataset_id": normalized_id,
            "title": row["title"],
            "count": count,
            "where": where,
            "source": "https://data.austintexas.gov/resource/%s.json" % normalized_id,
        }

    @mcp.tool(
        name="search",
        title="Search Civic Data Health",
        description="Use this when ChatGPT needs citation-friendly search results from the civic data health report.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def search(query: str) -> SearchOutput:
        rows = search_report(db_path, query, 10)
        return {
            "results": [
                {
                    "id": row["dataset_id"],
                    "title": row["title"] or row["dataset_id"],
                    "url": dataset_url(row),
                }
                for row in rows
            ]
        }

    @mcp.tool(
        name="fetch",
        title="Fetch Civic Data Health Record",
        description="Use this when ChatGPT needs the full citation-friendly text for one dataset health record.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def fetch(id: str) -> FetchOutput:
        normalized_id = id.strip().lower()
        if not normalized_id:
            raise ValueError("id is required")
        with connect(db_path) as conn:
            run_id = require_latest_run_id(conn)
            for row in report_rows(conn, run_id):
                if row["dataset_id"] == normalized_id:
                    return {
                        "id": row["dataset_id"],
                        "title": row["title"] or row["dataset_id"],
                        "text": dataset_text(row),
                        "url": dataset_url(row),
                        "metadata": {
                            "score": str(row["score"]),
                            "label": row["label"],
                            "asset_type": row.get("asset_type") or "",
                            "classification_group": str((row.get("classification") or {}).get("group") or ""),
                            "classification_confidence": str((row.get("classification") or {}).get("confidence") or ""),
                            "suggested_category": str((row.get("category_suggestion") or {}).get("suggested_category") or ""),
                            "suggested_category_confidence": str((row.get("category_suggestion") or {}).get("confidence") or ""),
                            "run_id": str(run_id),
                        },
                    }
        raise ValueError("Dataset id not found in latest run: %s" % normalized_id)

    return mcp


def serve(db_path: Path, host: str, port: int) -> None:
    create_mcp(db_path, host, port).run(transport="streamable-http")


def require_latest_run_id(conn) -> int:
    run_id = latest_run_id(conn)
    if run_id is None:
        raise ValueError("No generated report exists yet.")
    return run_id


def _latest_run_id(db_path: Path) -> int:
    with connect(db_path) as conn:
        return require_latest_run_id(conn)


def answer_public_government_question(question: str, *, jurisdiction: str, limit: int, include_rows: bool) -> Dict[str, Any]:
    safe_limit = max(1, min(int(limit or 5), 10))
    resources = search_government_resources(question, jurisdiction=jurisdiction, limit=safe_limit)
    datasets = search_public_catalogs(question, jurisdiction=jurisdiction, limit=safe_limit)
    packages = []
    errors = []
    if include_rows:
        for dataset in datasets:
            if not dataset["queryable"]:
                continue
            try:
                live_rows = load_socrata_query_rows(
                    dataset["dataset_id"],
                    limit=3,
                    domain=dataset["socrata_domain"],
                )
            except Exception as exc:
                errors.append({"source": dataset["source"], "dataset_id": dataset["dataset_id"], "reason": str(exc)})
                continue
            packages.append(
                {
                    "source": dataset["source"],
                    "jurisdiction": dataset["jurisdiction"],
                    "dataset": dataset,
                    "rows": live_rows,
                    "row_count": len(live_rows),
                }
            )
            if len(packages) >= 2:
                break
    return {
        "question": question,
        "answer": build_public_government_answer(resources, datasets, packages),
        "source_scope": public_source_scope(jurisdiction),
        "official_resources": resources,
        "datasets": datasets,
        "data_packages": packages,
        "row_errors": errors,
        "method": "Searched official Texas and Austin service links plus public Socrata data catalogs; fetched bounded public rows from matching queryable datasets when requested.",
    }


def build_public_government_answer(resources: List[Dict[str, Any]], datasets: List[Dict[str, Any]], packages: List[Dict[str, Any]]) -> str:
    pieces = []
    if resources:
        pieces.append("I found official government starting points for this request.")
    if datasets:
        pieces.append("I found matching public open-data catalog records.")
    if packages:
        pieces.append("I included bounded live public rows from the strongest queryable dataset matches.")
    if not pieces:
        return "I did not find a strong official resource or public-data catalog match. Try naming the agency, permit type, location, or service."
    return " ".join(pieces)


def public_source_scope(jurisdiction: str) -> Dict[str, Any]:
    normalized = normalize_search_text(jurisdiction or "all")
    sources = ["texas", "austin"] if normalized in {"all", "auto"} else [normalized]
    catalog_sources = []
    for source in sources:
        if source not in PUBLIC_CATALOGS:
            continue
        info = PUBLIC_CATALOGS[source]
        catalog_sources.append(
            {
                "source": source,
                "jurisdiction": info["jurisdiction"],
                "catalog_url": info["catalog_url"],
                "socrata_domain": info["socrata_domain"],
            }
        )
    return {
        "sources": catalog_sources,
        "note": "Public catalog and service-link search only; permit requirements still depend on the agency, locality, business activity, property, and project scope.",
    }


def load_public_schema(dataset_id: str, domain: str) -> Dict[str, Any]:
    metadata = fetch_view_metadata(dataset_id, domain=domain)
    return simplify_schema(dataset_id, metadata, domain=domain)


def dataset_brief(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "dataset_id": row["dataset_id"],
        "title": row["title"],
        "url": dataset_url(row),
        "label": row["label"],
        "score": row["score"],
        "modified": row.get("modified") or "",
        "publisher": row.get("publisher") or "",
        "asset_group": asset_group(row),
    }


def parse_column_list(value: str) -> List[str]:
    return [column.strip() for column in value.split(",") if column.strip()]


def search_report(db_path: Path, query: str, limit: int) -> List[Dict[str, Any]]:
    normalized_query = normalize_search_text(query)
    if not normalized_query:
        raise ValueError("query is required")
    with connect(db_path) as conn:
        run_id = require_latest_run_id(conn)
        matches = find_city_datasets(report_rows(conn, run_id), query, limit=limit)
    return [match.row for match in matches]


def normalize_search_text(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def find_dataset(rows: List[Dict[str, Any]], dataset_id: str) -> Optional[Dict[str, Any]]:
    for row in rows:
        if row["dataset_id"] == dataset_id:
            return row
    return None


def dataset_url(row: Dict[str, Any]) -> str:
    return row.get("landing_url") or "https://data.austintexas.gov/d/%s" % row["dataset_id"]


def dataset_text(row: Dict[str, Any]) -> str:
    details = {
        "dataset_id": row["dataset_id"],
        "title": row["title"],
        "score": row["score"],
        "label": row["label"],
        "asset_type": row.get("asset_type") or "",
        "asset_group": asset_group(row),
        "asset_group_label": asset_group_label(asset_group(row)),
        "classification": row.get("classification") or {},
        "modified": row.get("modified") or "",
        "publisher": row.get("publisher") or "",
        "contact": row.get("contact") or "",
        "keywords": row.get("keywords") or [],
        "category": row.get("category") or "",
        "category_suggestion": row.get("category_suggestion") or {},
        "issue_codes": row["issue_codes"],
        "remediation": row["remediation"],
        "landing_url": dataset_url(row),
    }
    return json.dumps(details, indent=2, sort_keys=True)


def clamp_limit(limit: int) -> int:
    return max(1, min(int(limit or 20), 100))
