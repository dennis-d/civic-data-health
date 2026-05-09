from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from . import __version__
from .classification import load_classification_overrides
from .normalize import normalize_catalog
from .reports import write_reports
from .scoring import score_dataset
from .storage import (
    connect,
    init_db,
    insert_datasets,
    insert_health,
    insert_run,
    insert_skipped,
    latest_run_for_sha,
)

DEFAULT_SOURCE_URL = "https://data.austintexas.gov/data.json"
SOCRATA_VIEW_URL = "https://data.austintexas.gov/api/views/{dataset_id}"


def fetch_bytes(url: str, timeout: float = 60.0) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "civic-data-health/0.1 (+https://civic.pagonya.co)",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        if status >= 400:
            raise RuntimeError("HTTP %s fetching %s" % (status, url))
        return response.read()


def fetch_json(url: str, timeout: float = 30.0) -> Dict[str, Any]:
    return json.loads(fetch_bytes(url, timeout=timeout).decode("utf-8"))


def run_pipeline(
    *,
    db_path: Path,
    data_dir: Path,
    out_dir: Optional[Path],
    source_url: str = DEFAULT_SOURCE_URL,
    limit: Optional[int] = None,
    force: bool = False,
    classification_overrides_path: Optional[Path] = Path("classification_overrides.json"),
) -> Dict[str, Any]:
    init_db(db_path)
    classification_overrides = load_classification_overrides(classification_overrides_path)
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    raw_bytes = fetch_bytes(source_url)
    catalog_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    with connect(db_path) as conn:
        existing = latest_run_for_sha(conn, catalog_sha256, limit)
        if existing and not force and not classification_overrides:
            run_id = int(existing["id"])
            report_paths = write_reports(db_path=db_path, out_dir=out_dir, run_id=run_id) if out_dir else {}
            return {"run_id": run_id, "status": "unchanged", "catalog_sha256": catalog_sha256, "report_paths": report_paths}

    catalog = json.loads(raw_bytes.decode("utf-8"))
    datasets, skipped, total_records = normalize_catalog(catalog, limit=limit)
    enrich_asset_types(db_path, datasets)
    health_results = [score_dataset(dataset, classification_overrides=classification_overrides) for dataset in datasets]

    snapshot_dir = data_dir / "raw" / fetched_at.replace(":", "-")
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    raw_path = snapshot_dir / "data.json"
    raw_path.write_bytes(raw_bytes)
    manifest_path = snapshot_dir / "manifest.json"
    manifest = {
        "source_url": source_url,
        "fetched_at": fetched_at,
        "raw_sha256": catalog_sha256,
        "raw_bytes": len(raw_bytes),
        "record_count": {
            "total": total_records,
            "normalized": len(datasets),
            "skipped": len(skipped),
            "errored": 0,
        },
        "limit_applied": limit,
        "tool_version": __version__,
        "classification_overrides": {
            "path": str(classification_overrides_path) if classification_overrides_path else "",
            "count": len(classification_overrides),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    processed_dir = data_dir / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    processed_path = processed_dir / ("datasets.%s.json" % fetched_at.replace(":", "-"))
    processed_payload = {
        "manifest": str(manifest_path),
        "datasets": [dataset.raw for dataset in datasets],
    }
    processed_path.write_text(json.dumps(processed_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    latest_processed = processed_dir / "datasets.json"
    if latest_processed.exists() or latest_processed.is_symlink():
        latest_processed.unlink()
    try:
        latest_processed.symlink_to(processed_path.name)
    except OSError:
        shutil.copy2(processed_path, latest_processed)

    with connect(db_path) as conn:
        run_id = insert_run(
            conn,
            fetched_at=fetched_at,
            source_url=source_url,
            raw_path=raw_path,
            manifest_path=manifest_path,
            raw_bytes=len(raw_bytes),
            catalog_sha256=catalog_sha256,
            total_records=total_records,
            normalized_count=len(datasets),
            skipped_count=len(skipped),
            errored_count=0,
            limit_applied=limit,
        )
        insert_datasets(conn, run_id, datasets)
        insert_health(conn, run_id, health_results)
        insert_skipped(conn, run_id, skipped)

    report_paths = write_reports(db_path=db_path, out_dir=out_dir, run_id=run_id) if out_dir else {}
    return {"run_id": run_id, "status": "processed", "catalog_sha256": catalog_sha256, "report_paths": report_paths}


def enrich_asset_types(db_path: Path, datasets, max_workers: int = 8) -> None:
    candidates = [dataset for dataset in datasets if not dataset.distribution or not dataset.machine_url]
    if not candidates:
        return

    cached = {}
    with connect(db_path) as conn:
        for dataset in candidates:
            row = conn.execute(
                """
                SELECT raw_json
                FROM view_metadata_cache
                WHERE dataset_id = ? AND COALESCE(source_modified, '') = COALESCE(?, '')
                """,
                (dataset.dataset_id, dataset.modified),
            ).fetchone()
            if row:
                try:
                    cached[dataset.dataset_id] = json.loads(row["raw_json"])
                except json.JSONDecodeError:
                    pass

    for dataset in candidates:
        raw = cached.get(dataset.dataset_id)
        if raw:
            dataset.asset_type = extract_asset_type(raw)

    missing = [dataset for dataset in candidates if not dataset.asset_type]
    if not missing:
        return

    fetched = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_dataset = {
            executor.submit(fetch_view_metadata, dataset.dataset_id): dataset
            for dataset in missing
        }
        for future in as_completed(future_to_dataset):
            dataset = future_to_dataset[future]
            try:
                raw = future.result()
            except Exception:
                continue
            dataset.asset_type = extract_asset_type(raw)
            fetched[dataset.dataset_id] = (dataset, raw)

    if not fetched:
        return
    with connect(db_path) as conn:
        conn.executemany(
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
            [
                (
                    dataset.dataset_id,
                    dataset.modified,
                    datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    json.dumps(raw.get("columns") or [], sort_keys=True),
                    json.dumps(raw, sort_keys=True),
                    200,
                )
                for dataset, raw in fetched.values()
            ],
        )


def fetch_view_metadata(dataset_id: str) -> Dict[str, Any]:
    return fetch_json(SOCRATA_VIEW_URL.format(dataset_id=dataset_id), timeout=30.0)


def extract_asset_type(raw: Dict[str, Any]) -> str:
    for key in ("assetType", "viewType", "displayType"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return ""
