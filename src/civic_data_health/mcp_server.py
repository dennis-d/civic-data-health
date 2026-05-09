from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from . import __version__
from .storage import connect, latest_run_id, report_rows, run_summary


TOOLS = [
    {
        "name": "get_report_summary",
        "description": "Summarize the latest Austin civic data health report.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "list_high_risk_datasets",
        "description": "List the highest-risk datasets from the latest report.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}},
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_dataset_health",
        "description": "Get score, issue codes, and remediation for one dataset id.",
        "inputSchema": {
            "type": "object",
            "properties": {"dataset_id": {"type": "string"}},
            "required": ["dataset_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "search_datasets",
        "description": "Search latest report datasets by title, description, id, or issue code.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}},
            "required": ["query"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
]


class CivicMcpHandler(BaseHTTPRequestHandler):
    db_path: Path

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/health", "/mcp/health"):
            self.write_json(200, {"ok": True, "service": "civic-data-health-mcp", "version": __version__})
            return
        self.write_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path.rstrip("/") != "/mcp":
            self.write_json(404, {"error": "not_found"})
            return
        try:
            body = self.rfile.read(int(self.headers.get("content-length", "0") or "0"))
            request = json.loads(body.decode("utf-8") or "{}")
            response = self.handle_rpc(request)
        except Exception as exc:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(exc)}}
        if response is None:
            self.send_response(202)
            self.end_headers()
            return
        self.write_json(200, response)

    def handle_rpc(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        if request_id is None and method and method.startswith("notifications/"):
            return None
        if method == "initialize":
            return self.rpc_result(
                request_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "civic-data-health", "version": __version__},
                },
            )
        if method == "tools/list":
            return self.rpc_result(request_id, {"tools": TOOLS})
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            payload = call_tool(self.db_path, name, arguments)
            return self.rpc_result(
                request_id,
                {
                    "content": [{"type": "text", "text": json.dumps(payload, indent=2, sort_keys=True)}],
                    "structuredContent": payload,
                },
            )
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Unknown method"}}

    def rpc_result(self, request_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def write_json(self, status: int, payload: Dict[str, Any]) -> None:
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        return


def call_tool(db_path: Path, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    with connect(db_path) as conn:
        run_id = latest_run_id(conn)
        if run_id is None:
            return {"error": "no_report_runs", "message": "No generated report exists yet."}
        if name == "get_report_summary":
            summary = run_summary(conn, run_id)
            top = report_rows(conn, run_id, limit=10)
            return {"summary": summary, "top_risks": top}
        if name == "list_high_risk_datasets":
            limit = int(arguments.get("limit") or 20)
            rows = [row for row in report_rows(conn, run_id, limit=max(limit * 2, limit)) if row["label"] == "high_risk"]
            return {"run_id": run_id, "datasets": rows[:limit]}
        if name == "get_dataset_health":
            dataset_id = str(arguments.get("dataset_id") or "").strip().lower()
            if not dataset_id:
                raise ValueError("dataset_id is required")
            for row in report_rows(conn, run_id):
                if row["dataset_id"] == dataset_id:
                    return {"run_id": run_id, "dataset": row}
            return {"run_id": run_id, "dataset": None, "message": "Dataset id not found in latest run."}
        if name == "search_datasets":
            query = str(arguments.get("query") or "").strip().casefold()
            limit = int(arguments.get("limit") or 20)
            if not query:
                raise ValueError("query is required")
            matches = []
            for row in report_rows(conn, run_id):
                haystack = " ".join(
                    [
                        row["dataset_id"],
                        row["title"],
                        row["description"],
                        " ".join(row["issue_codes"]),
                    ]
                ).casefold()
                if query in haystack:
                    matches.append(row)
                if len(matches) >= limit:
                    break
            return {"run_id": run_id, "query": query, "datasets": matches}
    raise ValueError("Unknown tool: %s" % name)


def serve(db_path: Path, host: str, port: int) -> None:
    CivicMcpHandler.db_path = db_path
    server = ThreadingHTTPServer((host, port), CivicMcpHandler)
    print("civic-data-health MCP serving on %s:%s using %s" % (host, port, db_path), flush=True)
    server.serve_forever()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args(argv)
    serve(args.db, args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

