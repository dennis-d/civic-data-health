from __future__ import annotations

import argparse
import json
from pathlib import Path

from .mcp_server import serve
from .pipeline import DEFAULT_SOURCE_URL, run_pipeline
from .reports import write_reports
from .storage import connect, init_db, latest_run_id, run_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="civic-health")
    parser.add_argument("--db", type=Path, default=Path("data/civic_health.sqlite"))
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Fetch Austin catalog, cache to SQLite, score, and write reports.")
    add_pipeline_args(run_parser)

    fetch_parser = subparsers.add_parser("fetch", help="Fetch Austin catalog and cache normalized/scored rows.")
    add_pipeline_args(fetch_parser, include_out=False)

    report_parser = subparsers.add_parser("report", help="Write static CSV/JSON/HTML reports from SQLite.")
    report_parser.add_argument("--out-dir", type=Path, default=Path("out"))
    report_parser.add_argument("--run-id", type=int)

    summary_parser = subparsers.add_parser("summary", help="Print latest run summary as JSON.")
    summary_parser.add_argument("--run-id", type=int)

    mcp_parser = subparsers.add_parser("mcp", help="Serve read-only MCP HTTP endpoint.")
    mcp_parser.add_argument("--host", default="127.0.0.1")
    mcp_parser.add_argument("--port", type=int, default=8787)

    return parser


def add_pipeline_args(parser: argparse.ArgumentParser, include_out: bool = True) -> None:
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    if include_out:
        parser.add_argument("--out-dir", type=Path, default=Path("out"))
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        result = run_pipeline(
            db_path=args.db,
            data_dir=args.data_dir,
            out_dir=args.out_dir,
            source_url=args.source_url,
            limit=args.limit,
            force=args.force,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "fetch":
        result = run_pipeline(
            db_path=args.db,
            data_dir=args.data_dir,
            out_dir=None,
            source_url=args.source_url,
            limit=args.limit,
            force=args.force,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "report":
        init_db(args.db)
        paths = write_reports(db_path=args.db, out_dir=args.out_dir, run_id=args.run_id)
        print(json.dumps(paths, indent=2, sort_keys=True))
        return 0

    if args.command == "summary":
        with connect(args.db) as conn:
            run_id = args.run_id or latest_run_id(conn)
            if run_id is None:
                raise SystemExit("No runs found in SQLite database")
            print(json.dumps(run_summary(conn, run_id), indent=2, sort_keys=True))
        return 0

    if args.command == "mcp":
        serve(args.db, args.host, args.port)
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

