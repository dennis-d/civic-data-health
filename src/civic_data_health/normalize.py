from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit

from .models import NormalizedDataset, SkippedRecord

DATASET_ID_RE = re.compile(r"^[a-z0-9]{4}-[a-z0-9]{4}$", re.IGNORECASE)
DATASET_ID_ANYWHERE_RE = re.compile(r"(?i)(?:^|[/=])([a-z0-9]{4}-[a-z0-9]{4})(?:$|[/?#&])")


def ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("name", "fn", "label", "title", "value", "@value"):
            found = text_value(value.get(key))
            if found:
                return found
        return ""
    if isinstance(value, list):
        return ", ".join(part for part in (text_value(item) for item in value) if part)
    return str(value).strip()


def extract_dataset_id(*candidates: Any) -> Optional[str]:
    for candidate in _flatten_candidates(candidates):
        value = text_value(candidate)
        if not value:
            continue
        cleaned = _clean_candidate(value)
        if DATASET_ID_RE.match(cleaned):
            return cleaned.lower()
        match = DATASET_ID_ANYWHERE_RE.search(value)
        if match:
            return match.group(1).lower()
    return None


def _flatten_candidates(values: Iterable[Any]) -> Iterable[Any]:
    for value in values:
        if isinstance(value, list):
            yield from _flatten_candidates(value)
        elif isinstance(value, dict):
            for key in ("identifier", "@id", "id", "url", "accessURL", "downloadURL", "landingPage"):
                if key in value:
                    yield value[key]
        else:
            yield value


def _clean_candidate(value: str) -> str:
    parts = urlsplit(value)
    path = parts.path.rstrip("/") if parts.scheme or parts.netloc else value.rstrip("/")
    return path.rsplit("/", 1)[-1].split("?", 1)[0].split("#", 1)[0].strip()


def normalize_catalog(catalog: Dict[str, Any], limit: Optional[int] = None) -> Tuple[List[NormalizedDataset], List[SkippedRecord], int]:
    records = catalog.get("dataset")
    if not isinstance(records, list):
        raise ValueError("Catalog JSON does not contain a dataset list")

    normalized: List[NormalizedDataset] = []
    skipped: List[SkippedRecord] = []
    selected = records[:limit] if limit else records

    for index, record in enumerate(selected):
        if not isinstance(record, dict):
            skipped.append(SkippedRecord(index, "", "", "record_not_object", json.dumps(record)[:1000]))
            continue
        try:
            dataset = normalize_record(record)
        except ValueError as exc:
            skipped.append(
                SkippedRecord(
                    source_index=index,
                    title=text_value(record.get("title")),
                    identifier_candidate=text_value(record.get("identifier") or record.get("@id")),
                    reason_code=str(exc),
                    raw_excerpt=json.dumps(record, sort_keys=True)[:1000],
                )
            )
            continue
        normalized.append(dataset)

    return normalized, skipped, len(records)


def normalize_record(record: Dict[str, Any]) -> NormalizedDataset:
    distributions = [item for item in ensure_list(record.get("distribution")) if isinstance(item, dict)]
    landing_url = text_value(record.get("landingPage") or record.get("@id"))
    dataset_id = extract_dataset_id(
        record.get("identifier"),
        record.get("@id"),
        landing_url,
        distributions,
    )
    if not dataset_id:
        raise ValueError("unstable_identifier")

    keywords = [text_value(item) for item in ensure_list(record.get("keyword"))]
    keywords = [item for item in keywords if item]
    category = text_value(record.get("theme") or record.get("category"))
    license_value = text_value(record.get("license"))
    publisher = text_value(record.get("publisher"))
    contact = text_value(record.get("contactPoint") or record.get("contact") or record.get("mbox"))
    machine_url = first_machine_url(distributions)

    return NormalizedDataset(
        dataset_id=dataset_id,
        title=text_value(record.get("title")),
        description=text_value(record.get("description")),
        modified=text_value(record.get("modified")) or None,
        publisher=publisher,
        contact=contact,
        keywords=keywords,
        license=license_value,
        category=category,
        accrual_periodicity=text_value(record.get("accrualPeriodicity")),
        landing_url=landing_url,
        distribution=distributions,
        machine_url=machine_url,
        raw=record,
    )


def first_machine_url(distributions: List[Dict[str, Any]]) -> str:
    for distribution in distributions:
        for key in ("downloadURL", "accessURL"):
            value = text_value(distribution.get(key))
            if value:
                return value
    return ""

