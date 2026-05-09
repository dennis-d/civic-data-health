from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import __version__
from .models import HealthResult, NormalizedDataset, SkippedRecord


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_at TEXT NOT NULL,
                source_url TEXT NOT NULL,
                raw_path TEXT NOT NULL,
                manifest_path TEXT NOT NULL,
                raw_bytes INTEGER NOT NULL,
                catalog_sha256 TEXT NOT NULL,
                total_records INTEGER NOT NULL,
                normalized_count INTEGER NOT NULL,
                skipped_count INTEGER NOT NULL,
                errored_count INTEGER NOT NULL DEFAULT 0,
                limit_applied INTEGER,
                tool_version TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_runs_fetched_at ON runs(fetched_at);
            CREATE INDEX IF NOT EXISTS idx_runs_sha ON runs(catalog_sha256);

            CREATE TABLE IF NOT EXISTS datasets (
                run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                dataset_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                modified TEXT,
                publisher TEXT NOT NULL,
                contact TEXT NOT NULL,
                keywords_json TEXT NOT NULL,
                license TEXT NOT NULL,
                category TEXT NOT NULL,
                accrual_periodicity TEXT NOT NULL,
                landing_url TEXT NOT NULL,
                distribution_json TEXT NOT NULL,
                machine_url TEXT NOT NULL,
                asset_type TEXT NOT NULL DEFAULT '',
                raw_json TEXT NOT NULL,
                PRIMARY KEY (run_id, dataset_id)
            );

            CREATE TABLE IF NOT EXISTS dataset_health (
                run_id INTEGER NOT NULL,
                dataset_id TEXT NOT NULL,
                score INTEGER NOT NULL,
                label TEXT NOT NULL,
                issue_codes_json TEXT NOT NULL,
                remediation_json TEXT NOT NULL,
                freshness_confidence TEXT NOT NULL,
                data_dictionary_quality_json TEXT NOT NULL,
                classification_json TEXT NOT NULL DEFAULT '{}',
                category_suggestion_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (run_id, dataset_id),
                FOREIGN KEY (run_id, dataset_id) REFERENCES datasets(run_id, dataset_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_dataset_health_score ON dataset_health(run_id, label, score);

            CREATE TABLE IF NOT EXISTS skipped_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                source_index INTEGER NOT NULL,
                title TEXT NOT NULL,
                identifier_candidate TEXT NOT NULL,
                reason_code TEXT NOT NULL,
                raw_excerpt TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS view_metadata_cache (
                dataset_id TEXT PRIMARY KEY,
                source_modified TEXT,
                fetched_at TEXT NOT NULL,
                columns_json TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                http_status INTEGER NOT NULL
            );
            """
        )
        migrate_existing_schema(conn)


def migrate_existing_schema(conn: sqlite3.Connection) -> None:
    """Keep early demo databases usable after the packaged app is deployed."""
    ensure_column(conn, "runs", "raw_path", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "runs", "manifest_path", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "runs", "raw_bytes", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, "runs", "total_records", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, "runs", "normalized_count", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, "runs", "skipped_count", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, "runs", "errored_count", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, "runs", "limit_applied", "INTEGER")
    ensure_column(conn, "runs", "tool_version", "TEXT NOT NULL DEFAULT 'pre-repo'")
    ensure_column(conn, "datasets", "asset_type", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "dataset_health", "issue_codes_json", "TEXT NOT NULL DEFAULT '[]'")
    ensure_column(conn, "dataset_health", "freshness_confidence", "TEXT NOT NULL DEFAULT 'unknown'")
    ensure_column(conn, "dataset_health", "data_dictionary_quality_json", "TEXT NOT NULL DEFAULT '{}'")
    ensure_column(conn, "dataset_health", "classification_json", "TEXT NOT NULL DEFAULT '{}'")
    ensure_column(conn, "dataset_health", "category_suggestion_json", "TEXT NOT NULL DEFAULT '{}'")


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(%s)" % table).fetchall()}
    if column not in columns:
        conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, column, definition))


def latest_run(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM runs ORDER BY fetched_at DESC, id DESC LIMIT 1").fetchone()


def latest_run_for_sha(conn: sqlite3.Connection, catalog_sha256: str, limit_applied: Optional[int]) -> Optional[sqlite3.Row]:
    if limit_applied:
        return None
    return conn.execute(
        """
        SELECT * FROM runs
        WHERE catalog_sha256 = ?
          AND limit_applied IS NULL
          AND normalized_count > 0
          AND tool_version = ?
        ORDER BY fetched_at DESC, id DESC
        LIMIT 1
        """,
        (catalog_sha256, __version__),
    ).fetchone()


def insert_run(
    conn: sqlite3.Connection,
    *,
    fetched_at: str,
    source_url: str,
    raw_path: Path,
    manifest_path: Path,
    raw_bytes: int,
    catalog_sha256: str,
    total_records: int,
    normalized_count: int,
    skipped_count: int,
    errored_count: int,
    limit_applied: Optional[int],
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO runs (
            fetched_at, source_url, raw_path, manifest_path, raw_bytes, catalog_sha256,
            total_records, normalized_count, skipped_count, errored_count, limit_applied, tool_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fetched_at,
            source_url,
            str(raw_path),
            str(manifest_path),
            raw_bytes,
            catalog_sha256,
            total_records,
            normalized_count,
            skipped_count,
            errored_count,
            limit_applied,
            __version__,
        ),
    )
    return int(cursor.lastrowid)


def insert_datasets(conn: sqlite3.Connection, run_id: int, datasets: Iterable[NormalizedDataset]) -> None:
    conn.executemany(
        """
        INSERT INTO datasets (
            run_id, dataset_id, title, description, modified, publisher, contact, keywords_json,
            license, category, accrual_periodicity, landing_url, distribution_json, machine_url, asset_type, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                run_id,
                dataset.dataset_id,
                dataset.title,
                dataset.description,
                dataset.modified,
                dataset.publisher,
                dataset.contact,
                json.dumps(dataset.keywords, sort_keys=True),
                dataset.license,
                dataset.category,
                dataset.accrual_periodicity,
                dataset.landing_url,
                json.dumps(dataset.distribution, sort_keys=True),
                dataset.machine_url,
                dataset.asset_type,
                json.dumps(dataset.raw, sort_keys=True),
            )
            for dataset in datasets
        ],
    )


def insert_health(conn: sqlite3.Connection, run_id: int, results: Iterable[HealthResult]) -> None:
    conn.executemany(
        """
        INSERT INTO dataset_health (
            run_id, dataset_id, score, label, issue_codes_json, remediation_json,
            freshness_confidence, data_dictionary_quality_json, classification_json, category_suggestion_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                run_id,
                result.dataset_id,
                result.score,
                result.label,
                json.dumps(result.issue_codes, sort_keys=True),
                json.dumps(result.remediation, sort_keys=True),
                result.freshness_confidence,
                json.dumps(result.data_dictionary_quality, sort_keys=True),
                json.dumps(result.classification, sort_keys=True),
                json.dumps(result.category_suggestion, sort_keys=True),
            )
            for result in results
        ],
    )


def insert_skipped(conn: sqlite3.Connection, run_id: int, skipped: Iterable[SkippedRecord]) -> None:
    conn.executemany(
        """
        INSERT INTO skipped_records (run_id, source_index, title, identifier_candidate, reason_code, raw_excerpt)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                run_id,
                record.source_index,
                record.title,
                record.identifier_candidate,
                record.reason_code,
                record.raw_excerpt,
            )
            for record in skipped
        ],
    )


def cached_view_metadata(conn: sqlite3.Connection, dataset_id: str, source_modified: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if source_modified is None:
        row = conn.execute(
            """
            SELECT raw_json
            FROM view_metadata_cache
            WHERE dataset_id = ?
            """,
            (dataset_id,),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT raw_json
            FROM view_metadata_cache
            WHERE dataset_id = ? AND COALESCE(source_modified, '') = COALESCE(?, '')
            """,
            (dataset_id, source_modified),
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["raw_json"])


def upsert_view_metadata(
    conn: sqlite3.Connection,
    *,
    dataset_id: str,
    source_modified: Optional[str],
    raw: Dict[str, Any],
    http_status: int = 200,
) -> None:
    conn.execute(
        """
        INSERT INTO view_metadata_cache (dataset_id, source_modified, fetched_at, columns_json, raw_json, http_status)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(dataset_id) DO UPDATE SET
            source_modified = excluded.source_modified,
            fetched_at = excluded.fetched_at,
            columns_json = excluded.columns_json,
            raw_json = excluded.raw_json,
            http_status = excluded.http_status
        """,
        (
            dataset_id,
            source_modified,
            datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            json.dumps(raw.get("columns") or [], sort_keys=True),
            json.dumps(raw, sort_keys=True),
            http_status,
        ),
    )


def report_rows(conn: sqlite3.Connection, run_id: int, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            d.dataset_id, d.title, d.description, d.modified, d.publisher, d.contact,
            d.keywords_json, d.license, d.category, d.accrual_periodicity, d.landing_url,
            d.asset_type,
            d.machine_url, h.score, h.label, h.issue_codes_json, h.remediation_json,
            h.freshness_confidence, h.data_dictionary_quality_json, h.classification_json,
            h.category_suggestion_json
        FROM datasets d
        JOIN dataset_health h ON h.run_id = d.run_id AND h.dataset_id = d.dataset_id
        WHERE d.run_id = ?
        ORDER BY
            CASE h.label WHEN 'high_risk' THEN 0 WHEN 'needs_review' THEN 1 ELSE 2 END,
            h.score ASC,
            lower(d.title) ASC
    """
    params: List[Any] = [run_id]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return [_decode_row(row) for row in conn.execute(sql, params).fetchall()]


def skipped_rows(conn: sqlite3.Connection, run_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT source_index, title, identifier_candidate, reason_code
        FROM skipped_records
        WHERE run_id = ?
        ORDER BY source_index ASC
        LIMIT ?
        """,
        (run_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def run_summary(conn: sqlite3.Connection, run_id: int) -> Dict[str, Any]:
    run = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if run is None:
        raise ValueError("run not found")
    counts = conn.execute(
        """
        SELECT label, COUNT(*) AS count
        FROM dataset_health
        WHERE run_id = ?
        GROUP BY label
        """,
        (run_id,),
    ).fetchall()
    by_label = {row["label"]: row["count"] for row in counts}
    avg = conn.execute("SELECT AVG(score) AS average_score FROM dataset_health WHERE run_id = ?", (run_id,)).fetchone()
    return {
        "run_id": run["id"],
        "fetched_at": run["fetched_at"],
        "source_url": run["source_url"],
        "catalog_sha256": run["catalog_sha256"],
        "total_records": run["total_records"],
        "analyzed_records": run["normalized_count"],
        "skipped_records": run["skipped_count"],
        "errored_records": run["errored_count"],
        "limit_applied": run["limit_applied"],
        "average_score": round(float(avg["average_score"] or 0), 2),
        "labels": {
            "high_risk": by_label.get("high_risk", 0),
            "needs_review": by_label.get("needs_review", 0),
            "good": by_label.get("good", 0),
        },
        "tool_version": run["tool_version"],
    }


def latest_run_id(conn: sqlite3.Connection) -> Optional[int]:
    row = latest_run(conn)
    return int(row["id"]) if row else None


def _decode_row(row: sqlite3.Row) -> Dict[str, Any]:
    item = dict(row)
    item["keywords"] = json.loads(item.pop("keywords_json"))
    item["issue_codes"] = json.loads(item.pop("issue_codes_json"))
    item["remediation"] = json.loads(item.pop("remediation_json"))
    item["data_dictionary_quality"] = json.loads(item.pop("data_dictionary_quality_json"))
    item["classification"] = json.loads(item.pop("classification_json") or "{}")
    item["category_suggestion"] = json.loads(item.pop("category_suggestion_json") or "{}")
    if not item["classification"].get("group"):
        item["classification"] = legacy_classification(item)
    return item


def legacy_classification(item: Dict[str, Any]) -> Dict[str, Any]:
    asset_type = str(item.get("asset_type") or "").casefold()
    issues = set(item.get("issue_codes") or [])
    if asset_type == "measure" or "socrata_measure_asset" in issues:
        group = "measure"
    elif asset_type in {"story", "href", "blob", "file"} or issues.intersection({"socrata_story_page", "socrata_reference_asset"}):
        group = "story_reference"
    elif "point_in_time_or_event_record" in issues:
        group = "archive_snapshot"
    else:
        group = "active_dataset"
    return {
        "group": group,
        "confidence": "legacy",
        "evidence": [],
        "reason": "Legacy row did not store explicit classification evidence.",
        "override_applied": False,
    }
