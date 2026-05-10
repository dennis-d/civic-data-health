from __future__ import annotations

import re
from typing import Any, Callable, Dict, Iterable, List, Sequence

from .discovery import normalize_text, tokenize
from .socrata import fetch_json

CatalogLoader = Callable[[str], Dict[str, Any]]

DATASET_ID_RE = re.compile(r"\b[a-z0-9]{4}-[a-z0-9]{4}\b", re.I)

PUBLIC_CATALOGS: Dict[str, Dict[str, str]] = {
    "texas": {
        "jurisdiction": "State of Texas",
        "catalog_url": "https://data.texas.gov/data.json",
        "socrata_domain": "data.texas.gov",
    },
    "austin": {
        "jurisdiction": "City of Austin",
        "catalog_url": "https://data.austintexas.gov/data.json",
        "socrata_domain": "data.austintexas.gov",
    },
}

GOVERNMENT_RESOURCES: List[Dict[str, Any]] = [
    {
        "jurisdiction": "State of Texas",
        "title": "Texas.gov official state services",
        "url": "https://www.texas.gov/",
        "description": "Official State of Texas portal for resident, business, and government services.",
        "keywords": ["state services", "government", "agency", "texas", "governance"],
    },
    {
        "jurisdiction": "State of Texas",
        "title": "Starting a Business in Texas",
        "url": "https://www.texas.gov/starting-business-texas/",
        "description": "Texas.gov guide to starting a business, including licenses, permits, taxes, and employer requirements.",
        "keywords": ["business", "start business", "license", "permit", "tax"],
    },
    {
        "jurisdiction": "State of Texas",
        "title": "Business Permit Office",
        "url": "https://gov.texas.gov/business/page/business-permits-office",
        "description": "Texas Economic Development office that helps businesses navigate permitting, licensing, and regulation.",
        "keywords": ["business permit", "license", "permits", "regulatory", "ombudsman"],
    },
    {
        "jurisdiction": "State of Texas",
        "title": "Occupational and Professional Licenses",
        "url": "https://www.texas.gov/occupational-professional-licenses-in-texas/",
        "description": "Texas.gov directory for applying for, managing, and renewing occupational and professional licenses.",
        "keywords": ["professional license", "occupational license", "tdlr", "renew license", "permit"],
    },
    {
        "jurisdiction": "State of Texas",
        "title": "TCEQ permits and licenses",
        "url": "https://www.tceq.texas.gov/permitting/business_types/",
        "description": "Texas Commission on Environmental Quality guide to environmental permits, licenses, registrations, and authorizations.",
        "keywords": ["environment", "tceq", "air", "water", "waste", "permit", "license"],
    },
    {
        "jurisdiction": "State of Texas",
        "title": "TABC licenses and permits",
        "url": "https://www.tabc.texas.gov/licensing/",
        "description": "Texas Alcoholic Beverage Commission licensing and permit information.",
        "keywords": ["alcohol", "tabc", "license", "permit", "restaurant", "bar", "event"],
    },
    {
        "jurisdiction": "City of Austin",
        "title": "Austin Development Services permits",
        "url": "https://www.austintexas.gov/department/development-services/permits",
        "description": "City of Austin permit types for development, building, land use, special events, and related work.",
        "keywords": ["austin", "building permit", "development", "land use", "special event", "permit"],
    },
    {
        "jurisdiction": "City of Austin",
        "title": "Austin Express Permits",
        "url": "https://www.austintexas.gov/development-services/express-permits",
        "description": "Austin residential express building permits for qualifying minor repairs and small projects.",
        "keywords": ["austin", "express permit", "residential", "minor repair", "building permit"],
    },
]


def search_public_catalogs(
    query: str,
    *,
    jurisdiction: str = "all",
    limit: int = 10,
    catalog_loader: CatalogLoader | None = None,
) -> List[Dict[str, Any]]:
    normalized_query = " ".join((query or "").split())
    if not normalized_query:
        raise ValueError("query is required")
    loader = catalog_loader or load_catalog
    matches = []
    for source_key in catalog_sources(jurisdiction):
        source = PUBLIC_CATALOGS[source_key]
        payload = loader(source_key)
        datasets = payload.get("dataset") or []
        for record in datasets:
            if not isinstance(record, dict):
                continue
            score = score_catalog_record(record, normalized_query)
            if score <= 0:
                continue
            matches.append(catalog_record_result(source_key, source, record, score, normalized_query))
    matches.sort(key=lambda item: (-item["match_score"], item["jurisdiction"], item["title"].casefold()))
    return matches[: max(1, min(int(limit or 10), 50))]


def search_government_resources(query: str, *, jurisdiction: str = "all", limit: int = 8) -> List[Dict[str, Any]]:
    normalized_query = " ".join((query or "").split())
    if not normalized_query:
        raise ValueError("query is required")
    source_names = {PUBLIC_CATALOGS[source]["jurisdiction"] for source in catalog_sources(jurisdiction)}
    scored = []
    for resource in GOVERNMENT_RESOURCES:
        if resource["jurisdiction"] not in source_names:
            continue
        score = score_resource(resource, normalized_query)
        if score > 0:
            scored.append({**resource, "match_score": score, "matched_terms": sorted(matched_terms(resource_text(resource), normalized_query))})
    scored.sort(key=lambda item: (-item["match_score"], item["jurisdiction"], item["title"].casefold()))
    return scored[: max(1, min(int(limit or 8), len(GOVERNMENT_RESOURCES)))]


def load_catalog(source_key: str) -> Dict[str, Any]:
    source = PUBLIC_CATALOGS[source_key]
    payload = fetch_json(source["catalog_url"])
    if not isinstance(payload, dict):
        raise ValueError("Catalog response was not an object for %s" % source_key)
    return payload


def catalog_sources(jurisdiction: str) -> List[str]:
    normalized = normalize_text(jurisdiction or "all")
    if normalized in {"all", "auto", "texas and austin", "austin and texas"}:
        return ["texas", "austin"]
    if normalized in {"texas", "state", "state of texas", "tx"}:
        return ["texas"]
    if normalized in {"austin", "city", "city of austin"}:
        return ["austin"]
    raise ValueError("jurisdiction must be one of: all, texas, austin")


def score_catalog_record(record: Dict[str, Any], query: str) -> int:
    fields = {
        "title": normalize_text(str(record.get("title") or "")),
        "description": normalize_text(str(record.get("description") or "")),
        "keywords": normalize_text(" ".join(str(value) for value in record.get("keyword") or [])),
        "publisher": normalize_text(extract_publisher(record)),
        "identifier": normalize_text(str(record.get("identifier") or "")),
    }
    weights = {"title": 14, "keywords": 9, "description": 4, "publisher": 4, "identifier": 2}
    score = 0
    for term in tokenize(query):
        pattern = r"\b%s\b" % re.escape(term)
        for field, value in fields.items():
            if re.search(pattern, value):
                score += weights[field]
    phrase = normalize_text(query)
    if phrase and phrase in fields["title"]:
        score += 35
    if extract_dataset_id(record):
        score += 3
    return score


def catalog_record_result(source_key: str, source: Dict[str, str], record: Dict[str, Any], score: int, query: str) -> Dict[str, Any]:
    dataset_id = extract_dataset_id(record)
    text = catalog_record_text(record)
    return {
        "source": source_key,
        "jurisdiction": source["jurisdiction"],
        "dataset_id": dataset_id,
        "title": str(record.get("title") or dataset_id or "Untitled dataset"),
        "description": str(record.get("description") or ""),
        "url": str(record.get("landingPage") or record.get("identifier") or ""),
        "modified": str(record.get("modified") or ""),
        "publisher": extract_publisher(record),
        "keywords": [str(value) for value in record.get("keyword") or []],
        "queryable": bool(dataset_id),
        "socrata_domain": source["socrata_domain"] if dataset_id else "",
        "resource_api": "https://%s/resource/%s.json" % (source["socrata_domain"], dataset_id) if dataset_id else "",
        "match_score": score,
        "matched_terms": sorted(matched_terms(text, query)),
    }


def extract_dataset_id(record: Dict[str, Any]) -> str:
    parts = [str(record.get("identifier") or ""), str(record.get("landingPage") or "")]
    for distribution in record.get("distribution") or []:
        if isinstance(distribution, dict):
            parts.extend(str(distribution.get(key) or "") for key in ("accessURL", "downloadURL", "mediaType"))
    match = DATASET_ID_RE.search(" ".join(parts))
    return match.group(0).lower() if match else ""


def extract_publisher(record: Dict[str, Any]) -> str:
    publisher = record.get("publisher") or {}
    if isinstance(publisher, dict):
        return str(publisher.get("name") or publisher.get("identifier") or "")
    return str(publisher or "")


def score_resource(resource: Dict[str, Any], query: str) -> int:
    text = resource_text(resource)
    score = 0
    for term in tokenize(query):
        if re.search(r"\b%s\b" % re.escape(term), text):
            score += 10
    if "permit" in tokenize(query) and "permit" in text:
        score += 25
    if "license" in tokenize(query) and "license" in text:
        score += 20
    if normalize_text(query) in text:
        score += 25
    return score


def resource_text(resource: Dict[str, Any]) -> str:
    return normalize_text(
        " ".join(
            [
                str(resource.get("jurisdiction") or ""),
                str(resource.get("title") or ""),
                str(resource.get("description") or ""),
                " ".join(str(value) for value in resource.get("keywords") or []),
            ]
        )
    )


def catalog_record_text(record: Dict[str, Any]) -> str:
    return normalize_text(
        " ".join(
            [
                str(record.get("title") or ""),
                str(record.get("description") or ""),
                " ".join(str(value) for value in record.get("keyword") or []),
                extract_publisher(record),
                str(record.get("identifier") or ""),
            ]
        )
    )


def matched_terms(text: str, query: str) -> Sequence[str]:
    return sorted(tokenize(query).intersection(tokenize(text)))
