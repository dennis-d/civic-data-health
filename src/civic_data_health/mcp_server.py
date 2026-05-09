from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from . import __version__
from .storage import connect, latest_run_id, report_rows, run_summary

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
            "Read-only Austin open data health report. Use these tools to summarize "
            "dataset health, search report findings, and fetch cited dataset details."
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
            return {"summary": run_summary(conn, run_id), "top_risks": report_rows(conn, run_id, limit=10)}

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
            rows = [row for row in report_rows(conn, run_id, limit=max(safe_limit * 3, safe_limit)) if row["label"] == "high_risk"]
            return {"run_id": run_id, "datasets": rows[:safe_limit]}

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
            for row in report_rows(conn, run_id):
                if row["dataset_id"] == normalized_id:
                    return {"run_id": run_id, "dataset": row}
        return {"run_id": run_id, "dataset": None, "message": "Dataset id not found in latest run."}

    @mcp.tool(
        title="Search Datasets",
        description="Use this when you need to search Austin report rows by title, description, id, asset type, or issue code.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def search_datasets(query: str, limit: int = 20) -> Dict[str, Any]:
        return {"run_id": _latest_run_id(db_path), "query": query, "datasets": search_report(db_path, query, clamp_limit(limit))}

    @mcp.tool(
        name="search",
        title="Search Civic Data Health",
        description="Use this when ChatGPT needs citation-friendly search results from the civic data health report.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    def search(query: str) -> Dict[str, Any]:
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
    def fetch(id: str) -> Dict[str, Any]:
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


def search_report(db_path: Path, query: str, limit: int) -> List[Dict[str, Any]]:
    normalized_query = query.strip().casefold()
    if not normalized_query:
        raise ValueError("query is required")
    with connect(db_path) as conn:
        run_id = require_latest_run_id(conn)
        matches = []
        for row in report_rows(conn, run_id):
            haystack = " ".join(
                [
                    row["dataset_id"],
                    row["title"],
                    row["description"],
                    row.get("asset_type") or "",
                    " ".join(row["issue_codes"]),
                ]
            ).casefold()
            if normalized_query in haystack:
                matches.append(row)
            if len(matches) >= limit:
                break
    return matches


def dataset_url(row: Dict[str, Any]) -> str:
    return row.get("landing_url") or "https://data.austintexas.gov/d/%s" % row["dataset_id"]


def dataset_text(row: Dict[str, Any]) -> str:
    details = {
        "dataset_id": row["dataset_id"],
        "title": row["title"],
        "score": row["score"],
        "label": row["label"],
        "asset_type": row.get("asset_type") or "",
        "modified": row.get("modified") or "",
        "publisher": row.get("publisher") or "",
        "contact": row.get("contact") or "",
        "issue_codes": row["issue_codes"],
        "remediation": row["remediation"],
        "landing_url": dataset_url(row),
    }
    return json.dumps(details, indent=2, sort_keys=True)


def clamp_limit(limit: int) -> int:
    return max(1, min(int(limit or 20), 100))

