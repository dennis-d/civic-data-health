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
        "jurisdiction": "State of Texas",
        "title": "Texas Secretary of State business filings",
        "url": "https://www.sos.texas.gov/corp/do-business.shtml",
        "description": "Texas Secretary of State business filing resources, including formation, name availability, SOSDirect, and foreign entity registration.",
        "keywords": ["business filing", "entity", "sos", "secretary of state", "llc", "corporation", "registration"],
    },
    {
        "jurisdiction": "State of Texas",
        "title": "Texas sales tax permit requirements",
        "url": "https://comptroller.texas.gov/help/sales-tax-registration/requirements.php?category=taxes",
        "description": "Texas Comptroller sales tax registration requirements and starting point for sales and use tax permits.",
        "keywords": ["sales tax", "comptroller", "sales tax permit", "business tax", "registration"],
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
    {
        "jurisdiction": "City of Austin",
        "title": "Austin Build + Connect",
        "url": "https://www.austintexas.gov/development-services/austin-build-connect-abc",
        "description": "City of Austin online portal for some permits, inspections, fees, attachments, and public permit/case search.",
        "keywords": ["austin", "abc", "build connect", "permit portal", "inspection", "case search"],
    },
    {
        "jurisdiction": "City of Austin",
        "title": "Austin fixed food establishments",
        "url": "https://www.austintexas.gov/health/programs/fixed-food-establishments",
        "description": "Austin Public Health guidance for fixed food establishment permits, plan review, pre-opening inspection, and annual operational permits.",
        "keywords": ["food", "restaurant", "fixed food", "health permit", "plan review", "pre-opening inspection"],
    },
    {
        "jurisdiction": "City of Austin",
        "title": "Austin Property Profile",
        "url": "https://www.austintexas.gov/development-services/property-profile-overview",
        "description": "City of Austin property lookup for official records such as parcel, jurisdiction, council district, zoning, and development information.",
        "keywords": ["property", "zoning", "parcel", "address", "jurisdiction", "council district", "development"],
    },
    {
        "jurisdiction": "City of Austin",
        "title": "Austin zoning",
        "url": "https://www.austintexas.gov/planning/zoning",
        "description": "Austin Planning overview of zoning rules, rezoning, permitted uses, site regulations, and related land-use process resources.",
        "keywords": ["zoning", "rezoning", "land use", "site regulations", "planning", "property"],
    },
    {
        "jurisdiction": "City of Austin",
        "title": "Austin 3-1-1",
        "url": "https://www.austintexas.gov/department/311",
        "description": "City of Austin non-emergency information and service request starting point.",
        "keywords": ["311", "3-1-1", "service request", "complaint", "city services", "non-emergency"],
    },
    {
        "jurisdiction": "City of Austin",
        "title": "Report a code violation",
        "url": "https://www.austintexas.gov/services/report-code-violation",
        "description": "Official Austin service page for reporting code violations online, by Austin 3-1-1 app, or by phone.",
        "keywords": ["code violation", "code complaint", "complaint", "311", "property maintenance", "unsafe", "nuisance"],
    },
]

SERVICE_GUIDES: List[Dict[str, Any]] = [
    {
        "id": "start_texas_business",
        "title": "Start a Texas business",
        "jurisdictions": ["State of Texas"],
        "summary": "Formation, state tax, and license/permit starting points for a new Texas business.",
        "keywords": ["business", "start business", "llc", "corporation", "tax", "sales tax", "license", "permit", "sos"],
        "steps": [
            "Choose the business structure and check Texas Secretary of State filing requirements.",
            "Use Texas.gov and the Business Permit Office to identify state license and permit paths.",
            "Check Texas Comptroller sales tax permit requirements before selling taxable goods or services.",
            "Check industry-specific regulators such as TABC, TCEQ, TDLR, or DSHS when the business activity requires it.",
            "Check local city/county permits before opening, building out, or operating at a location.",
        ],
        "official_resources": [
            {
                "title": "Starting a Business in Texas",
                "url": "https://www.texas.gov/starting-business-texas/",
                "description": "Texas.gov guide to licenses, permits, taxes, and employer requirements.",
            },
            {
                "title": "Business Permit Office",
                "url": "https://gov.texas.gov/business/page/business-permits-office",
                "description": "State office that helps businesses navigate permitting, licensing, and regulation.",
            },
            {
                "title": "Texas Secretary of State business filings",
                "url": "https://www.sos.texas.gov/corp/do-business.shtml",
                "description": "Business filing, SOSDirect, name availability, and entity resources.",
            },
            {
                "title": "Texas sales tax permit requirements",
                "url": "https://comptroller.texas.gov/help/sales-tax-registration/requirements.php?category=taxes",
                "description": "Comptroller starting point for sales and use tax permit registration.",
            },
        ],
        "related_dataset_queries": [
            "active sales tax permit holders",
            "sales tax permits issued",
            "occupational license business permit",
            "business permits licenses",
        ],
        "caveats": [
            "Permit needs depend on business structure, taxable activity, industry, location, property use, and local rules.",
            "This guide is a public-information starting point and cannot guarantee legal or permitting requirements.",
        ],
    },
    {
        "id": "austin_building_permit",
        "title": "Start an Austin building or trade permit",
        "jurisdictions": ["City of Austin"],
        "summary": "Austin Development Services starting points for building, trade, express, and related development permits.",
        "keywords": ["building", "permit", "trade", "inspection", "abc", "build connect", "express permit", "development"],
        "steps": [
            "Identify the permit type and whether the work qualifies for an express permit or requires plan review.",
            "Create or use an Austin Build + Connect account when the permit path requires AB+C.",
            "Prepare the site address, scope, plans, owner authorization, and contractor registration details.",
            "Submit through the directed portal or web form, pay fees, and respond to review comments.",
            "After issuance, schedule required inspections before closing out the work.",
        ],
        "official_resources": [
            {
                "title": "Austin Development Services permits",
                "url": "https://www.austintexas.gov/department/development-services/permits",
                "description": "City permit types and application starting points.",
            },
            {
                "title": "Austin Build + Connect",
                "url": "https://www.austintexas.gov/development-services/austin-build-connect-abc",
                "description": "Online portal for some permits, inspections, fees, and public search.",
            },
            {
                "title": "Austin Express Permits",
                "url": "https://www.austintexas.gov/development-services/express-permits",
                "description": "Residential express building permits for qualifying minor projects.",
            },
        ],
        "related_dataset_queries": [
            "building permits issued",
            "permit applications",
            "inspections building permits",
            "development review permits",
        ],
        "caveats": [
            "Permit route depends on property jurisdiction, project scope, trade work, contractor status, and review requirements.",
            "Do not start permitted work until the City issues the required permit.",
        ],
    },
    {
        "id": "austin_food_business",
        "title": "Start an Austin food business permit",
        "jurisdictions": ["State of Texas", "City of Austin"],
        "summary": "Austin Public Health and state starting points for food establishments, restaurants, bars, and food operators.",
        "keywords": ["food", "restaurant", "bar", "food truck", "fixed food", "health", "inspection", "tabc", "permit", "license"],
        "steps": [
            "Determine whether the business is inside Austin, unincorporated Travis County, or another municipality.",
            "Use Austin Public Health fixed food establishment guidance for plan review, pre-opening inspection, and operational permit steps.",
            "If alcohol is involved, check TABC licensing and any related local requirements.",
            "Check Texas sales tax permit requirements and state business setup steps.",
            "Use public inspection or permit datasets for research, but rely on official application pages for current requirements.",
        ],
        "official_resources": [
            {
                "title": "Austin fixed food establishments",
                "url": "https://www.austintexas.gov/health/programs/fixed-food-establishments",
                "description": "Austin Public Health fixed food establishment permit and inspection process.",
            },
            {
                "title": "TABC licenses and permits",
                "url": "https://www.tabc.texas.gov/licensing/",
                "description": "Texas Alcoholic Beverage Commission licensing and permit information.",
            },
            {
                "title": "Starting a Business in Texas",
                "url": "https://www.texas.gov/starting-business-texas/",
                "description": "Texas.gov business, license, permit, tax, and employer requirement guide.",
            },
        ],
        "related_dataset_queries": [
            "food establishment inspection scores",
            "restaurant inspections",
            "food permit",
            "TABC licenses permits",
        ],
        "caveats": [
            "Food permit path depends on jurisdiction, facility type, remodel/new construction status, menu/process, and alcohol sales.",
            "Special food processes may need additional variance or HACCP review.",
        ],
    },
    {
        "id": "austin_property_zoning",
        "title": "Research Austin property, zoning, and development constraints",
        "jurisdictions": ["City of Austin"],
        "summary": "Property Profile, zoning, and verification starting points before buying, leasing, renovating, or applying for permits.",
        "keywords": ["property", "zoning", "parcel", "address", "jurisdiction", "council district", "floodplain", "development", "land use"],
        "steps": [
            "Look up the address in Property Profile to confirm parcel, jurisdiction, council district, and zoning context.",
            "Review Austin zoning resources for permitted uses, site regulations, overlays, and rezoning basics.",
            "For formal confirmation, use zoning verification resources rather than relying only on map results.",
            "Use permit/case history and relevant datasets to understand activity around the property.",
            "Ask Development Services or Planning for project-specific questions before spending on plans or applications.",
        ],
        "official_resources": [
            {
                "title": "Austin Property Profile",
                "url": "https://www.austintexas.gov/development-services/property-profile-overview",
                "description": "Official city property lookup and map tool overview.",
            },
            {
                "title": "Austin zoning",
                "url": "https://www.austintexas.gov/planning/zoning",
                "description": "Austin Planning overview of zoning, rezoning, permitted uses, and land-use resources.",
            },
            {
                "title": "Zoning Verification",
                "url": "https://www.austintexas.gov/node/426484",
                "description": "Formal zoning verification and development compliance letter options.",
            },
        ],
        "related_dataset_queries": [
            "zoning cases",
            "property profile zoning",
            "council district address",
            "building permits address",
            "code cases address",
        ],
        "caveats": [
            "Map and dataset results may lag recent changes; formal zoning verification is separate from casual lookup.",
            "Allowed use and buildability can depend on overlays, site constraints, historic status, utilities, and existing approvals.",
        ],
    },
    {
        "id": "austin_311_code_complaint",
        "title": "File or research Austin 3-1-1 and code complaints",
        "jurisdictions": ["City of Austin"],
        "summary": "Austin 3-1-1 and Code Compliance starting points for service requests, code violations, and public request data.",
        "keywords": ["311", "3-1-1", "service request", "code complaint", "code violation", "complaint", "case", "status"],
        "steps": [
            "For city service requests, use Austin 3-1-1 online, the mobile app, or phone.",
            "For code violations, use the official report-code-violation path; anonymous reporting is available.",
            "Save the service request or case number so you can check status later.",
            "Use public 3-1-1 and code datasets to research patterns, but do not rely on them to submit or update a case.",
            "For existing code case questions, use Code Connect or the case status resources listed by the City.",
        ],
        "official_resources": [
            {
                "title": "Austin 3-1-1",
                "url": "https://www.austintexas.gov/department/311",
                "description": "Official Austin 3-1-1 service request and city information starting point.",
            },
            {
                "title": "Report a code violation",
                "url": "https://www.austintexas.gov/services/report-code-violation",
                "description": "Official reporting page for Austin code violations.",
            },
            {
                "title": "Submit a 3-1-1 request",
                "url": "https://www.austintexas.gov/services/submit-3-1-1-request",
                "description": "Submit or check the status of Austin 3-1-1 service requests.",
            },
        ],
        "related_dataset_queries": [
            "311 service requests",
            "code complaints",
            "code violations",
            "service request status",
        ],
        "caveats": [
            "This app cannot submit or modify 3-1-1 requests or code complaints.",
            "Public datasets may omit confidential details and may not show the current real-time case status.",
        ],
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


def search_service_guides(query: str, *, jurisdiction: str = "all", limit: int = 5) -> List[Dict[str, Any]]:
    normalized_query = " ".join((query or "").split())
    if not normalized_query:
        raise ValueError("query is required")
    source_names = {PUBLIC_CATALOGS[source]["jurisdiction"] for source in catalog_sources(jurisdiction)}
    scored = []
    for guide in SERVICE_GUIDES:
        if not source_names.intersection(set(guide["jurisdictions"])):
            continue
        score = score_service_guide(guide, normalized_query)
        if score > 0:
            scored.append(service_guide_result(guide, normalized_query, score))
    scored.sort(key=lambda item: (-item["match_score"], item["title"].casefold()))
    return scored[: max(1, min(int(limit or 5), len(SERVICE_GUIDES)))]


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


def score_service_guide(guide: Dict[str, Any], query: str) -> int:
    text = service_guide_text(guide)
    score = 0
    for term in tokenize(query):
        if re.search(r"\b%s\b" % re.escape(term), text):
            score += 10
    normalized_query = normalize_text(query)
    title = normalize_text(str(guide.get("title") or ""))
    summary = normalize_text(str(guide.get("summary") or ""))
    if normalized_query and normalized_query in title:
        score += 35
    if normalized_query and normalized_query in summary:
        score += 15
    query_terms = tokenize(query)
    if "permit" in query_terms and "permit" in text:
        score += 20
    if "business" in query_terms and "business" in text:
        score += 15
    if "property" in query_terms and "property" in text:
        score += 15
    return score


def service_guide_result(guide: Dict[str, Any], query: str, score: int) -> Dict[str, Any]:
    return {
        "id": guide["id"],
        "title": guide["title"],
        "jurisdictions": list(guide["jurisdictions"]),
        "summary": guide["summary"],
        "steps": list(guide["steps"]),
        "official_resources": list(guide["official_resources"]),
        "related_dataset_queries": list(guide["related_dataset_queries"]),
        "caveats": list(guide["caveats"]),
        "match_score": score,
        "matched_terms": sorted(matched_terms(service_guide_text(guide), query)),
    }


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


def service_guide_text(guide: Dict[str, Any]) -> str:
    resources = guide.get("official_resources") or []
    return normalize_text(
        " ".join(
            [
                str(guide.get("id") or ""),
                str(guide.get("title") or ""),
                str(guide.get("summary") or ""),
                " ".join(str(value) for value in guide.get("jurisdictions") or []),
                " ".join(str(value) for value in guide.get("keywords") or []),
                " ".join(str(value) for value in guide.get("steps") or []),
                " ".join(str(value) for value in guide.get("related_dataset_queries") or []),
                " ".join(str(value) for value in guide.get("caveats") or []),
                " ".join(
                    "%s %s %s" % (str(resource.get("title") or ""), str(resource.get("description") or ""), str(resource.get("url") or ""))
                    for resource in resources
                    if isinstance(resource, dict)
                ),
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
