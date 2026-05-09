from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from . import __version__
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


def run_pipeline(
    *,
    db_path: Path,
    data_dir: Path,
    out_dir: Optional[Path],
    source_url: str = DEFAULT_SOURCE_URL,
    limit: Optional[int] = None,
    force: bool = False,
) -> Dict[str, Any]:
    init_db(db_path)
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    raw_bytes = fetch_bytes(source_url)
    catalog_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    with connect(db_path) as conn:
        existing = latest_run_for_sha(conn, catalog_sha256, limit)
        if existing and not force:
            run_id = int(existing["id"])
            report_paths = write_reports(db_path=db_path, out_dir=out_dir, run_id=run_id) if out_dir else {}
            return {"run_id": run_id, "status": "unchanged", "catalog_sha256": catalog_sha256, "report_paths": report_paths}

    catalog = json.loads(raw_bytes.decode("utf-8"))
    datasets, skipped, total_records = normalize_catalog(catalog, limit=limit)
    health_results = [score_dataset(dataset) for dataset in datasets]

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

