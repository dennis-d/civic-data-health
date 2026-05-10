from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from .storage import cached_view_metadata, upsert_view_metadata

SOCRATA_DOMAIN = "data.austintexas.gov"
ALLOWED_SOCRATA_DOMAINS = {"data.austintexas.gov", "data.texas.gov"}
VIEW_URL = "https://{domain}/api/views/{dataset_id}"
RESOURCE_URL = "https://{domain}/resource/{dataset_id}.json"
DATASET_ID_RE = re.compile(r"^[a-z0-9]{4}-[a-z0-9]{4}$")
SAFE_FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_dataset_id(dataset_id: str) -> str:
    normalized = dataset_id.strip().lower()
    if not DATASET_ID_RE.fullmatch(normalized):
        raise ValueError("invalid Socrata dataset id: %s" % dataset_id)
    return normalized


def validate_socrata_domain(domain: str = SOCRATA_DOMAIN) -> str:
    normalized = domain.strip().lower()
    if normalized not in ALLOWED_SOCRATA_DOMAINS:
        raise ValueError("unsupported Socrata domain: %s" % domain)
    return normalized


def fetch_json(url: str, params: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Any:
    if params:
        query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
        url = "%s?%s" % (url, query)
    headers = {
        "Accept": "application/json",
        "User-Agent": "civic-data-health/0.4 (+https://civic.pagonya.co)",
    }
    token = os.environ.get("SOCRATA_APP_TOKEN")
    if token:
        headers["X-App-Token"] = token
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        if status >= 400:
            raise RuntimeError("HTTP %s fetching %s" % (status, url))
        return json.loads(response.read().decode("utf-8"))


def fetch_view_metadata(dataset_id: str, domain: str = SOCRATA_DOMAIN) -> Dict[str, Any]:
    normalized = validate_dataset_id(dataset_id)
    safe_domain = validate_socrata_domain(domain)
    payload = fetch_json(VIEW_URL.format(domain=safe_domain, dataset_id=normalized))
    if not isinstance(payload, dict):
        raise ValueError("Socrata view metadata response was not an object for %s" % normalized)
    return payload


def get_dataset_schema(conn, dataset_id: str, source_modified: Optional[str] = None) -> Dict[str, Any]:
    normalized = validate_dataset_id(dataset_id)
    cached = cached_view_metadata(conn, normalized, source_modified)
    if cached is None:
        cached = fetch_view_metadata(normalized)
        upsert_view_metadata(conn, dataset_id=normalized, source_modified=source_modified, raw=cached)
    return simplify_schema(normalized, cached)


def simplify_schema(dataset_id: str, raw: Dict[str, Any], domain: str = SOCRATA_DOMAIN) -> Dict[str, Any]:
    safe_domain = validate_socrata_domain(domain)
    columns = [simplify_column(column) for column in raw.get("columns") or [] if isinstance(column, dict)]
    queryable = [column for column in columns if column["field_name"] and not column["field_name"].startswith(":")]
    return {
        "dataset_id": dataset_id,
        "name": raw.get("name") or raw.get("title") or "",
        "asset_type": raw.get("assetType") or raw.get("viewType") or raw.get("displayType") or "",
        "columns": queryable,
        "column_count": len(queryable),
        "row_count": raw.get("rowCount"),
        "source_url": VIEW_URL.format(domain=safe_domain, dataset_id=dataset_id),
    }


def simplify_column(column: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "field_name": str(column.get("fieldName") or ""),
        "name": str(column.get("name") or ""),
        "data_type": str(column.get("dataTypeName") or column.get("renderTypeName") or ""),
        "description": str(column.get("description") or ""),
        "position": column.get("position"),
    }


def get_sample_rows(dataset_id: str, limit: int = 5, domain: str = SOCRATA_DOMAIN) -> List[Dict[str, Any]]:
    normalized = validate_dataset_id(dataset_id)
    safe_domain = validate_socrata_domain(domain)
    safe_limit = max(1, min(int(limit or 5), 20))
    payload = fetch_json(RESOURCE_URL.format(domain=safe_domain, dataset_id=normalized), {"$limit": safe_limit})
    if not isinstance(payload, list):
        raise ValueError("Socrata sample response was not a list for %s" % normalized)
    return payload


def query_rows(
    dataset_id: str,
    *,
    limit: int = 10,
    select_columns: Optional[List[str]] = None,
    where: Optional[str] = None,
    search: str = "",
    domain: str = SOCRATA_DOMAIN,
) -> List[Dict[str, Any]]:
    normalized = validate_dataset_id(dataset_id)
    safe_domain = validate_socrata_domain(domain)
    safe_limit = max(1, min(int(limit or 10), 50))
    params: Dict[str, Any] = {"$limit": safe_limit}
    if select_columns:
        cleaned_columns = [validate_field_name(column) for column in select_columns if str(column).strip()]
        if cleaned_columns:
            params["$select"] = ", ".join(cleaned_columns)
    if where:
        params["$where"] = where
    normalized_search = " ".join(str(search or "").split())
    if normalized_search:
        params["$q"] = normalized_search[:160]
    payload = fetch_json(RESOURCE_URL.format(domain=safe_domain, dataset_id=normalized), params)
    if not isinstance(payload, list):
        raise ValueError("Socrata row query response was not a list for %s" % normalized)
    return payload


def count_rows(dataset_id: str, where: Optional[str] = None, domain: str = SOCRATA_DOMAIN) -> int:
    normalized = validate_dataset_id(dataset_id)
    safe_domain = validate_socrata_domain(domain)
    params = {"$select": "count(*)"}
    if where:
        params["$where"] = where
    payload = fetch_json(RESOURCE_URL.format(domain=safe_domain, dataset_id=normalized), params)
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise ValueError("Socrata count response was not a row object for %s" % normalized)
    value = payload[0].get("count")
    if value is None:
        value = next(iter(payload[0].values()))
    return int(float(str(value)))


def validate_field_name(field_name: str) -> str:
    cleaned = field_name.strip()
    if not SAFE_FIELD_RE.fullmatch(cleaned):
        raise ValueError("unsafe Socrata field name: %s" % field_name)
    return cleaned
