from __future__ import annotations

import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from .analysis import asset_group
from .discovery import DiscoveryMatch, find_city_datasets, normalize_text, tokenize
from .row_answer import choose_date_column, parse_date_range, is_count_question
from .socrata import get_dataset_schema

SchemaLoader = Callable[[Any, Dict[str, Any]], Dict[str, Any]]

DATE_TYPES = {"calendar_date", "date", "floating_timestamp", "fixed_timestamp"}
NUMERIC_TYPES = {"number", "money", "double", "floating_number", "percent", "integer"}
TEXT_TYPES = {"text", "html", "url", "email"}
DATE_TERMS = {
    "calendar",
    "created",
    "date",
    "issued",
    "modified",
    "month",
    "reported",
    "time",
    "updated",
    "year",
}
GEO_TERMS = {
    "address",
    "boundary",
    "census",
    "council",
    "district",
    "geocode",
    "geo",
    "geom",
    "latitude",
    "location",
    "longitude",
    "map",
    "neighborhood",
    "precinct",
    "tract",
    "ward",
    "watershed",
    "zip",
}
NUMERIC_TERMS = {"amount", "count", "cost", "number", "percent", "rate", "revenue", "score", "total", "value"}
CATEGORY_TERMS = {"category", "class", "code", "description", "group", "name", "status", "type"}


def get_capabilities_for_row(conn: Any, row: Dict[str, Any], *, schema_loader: Optional[SchemaLoader] = None) -> Dict[str, Any]:
    schema = load_schema(conn, row, schema_loader=schema_loader)
    return summarize_capabilities(row, schema)


def search_columns(
    conn: Any,
    rows: Iterable[Dict[str, Any]],
    query: str,
    *,
    limit: int = 20,
    candidate_limit: int = 12,
    schema_loader: Optional[SchemaLoader] = None,
) -> Dict[str, Any]:
    normalized_query = " ".join((query or "").split())
    if not normalized_query:
        raise ValueError("query is required")
    matches = find_city_datasets(rows, normalized_query, limit=max(1, min(int(candidate_limit or 12), 30)))
    column_matches: List[Dict[str, Any]] = []
    inspected = []
    for match in matches:
        row = match.row
        if not is_schema_search_candidate(row):
            inspected.append({"dataset_id": row["dataset_id"], "status": "skipped", "reason": "not an active machine-readable dataset"})
            continue
        try:
            schema = load_schema(conn, row, schema_loader=schema_loader)
        except Exception as exc:
            inspected.append({"dataset_id": row["dataset_id"], "status": "error", "reason": str(exc)})
            continue
        inspected.append({"dataset_id": row["dataset_id"], "status": "checked", "column_count": schema.get("column_count", 0)})
        for column in schema.get("columns") or []:
            score = score_column(column, normalized_query)
            if score <= 0:
                continue
            column_matches.append(
                {
                    "dataset_id": row["dataset_id"],
                    "title": row["title"],
                    "landing_url": row.get("landing_url") or "",
                    "machine_url": row.get("machine_url") or "",
                    "label": row["label"],
                    "catalog_match_score": match.score,
                    "column": column_summary(column),
                    "column_roles": column_roles(column),
                    "match_score": score,
                    "why_this_matches": explain_column_match(column, normalized_query),
                }
            )
    column_matches.sort(key=lambda item: (-item["match_score"], -item["catalog_match_score"], item["title"].casefold(), item["column"]["field_name"]))
    return {
        "query": normalized_query,
        "matches": column_matches[: max(1, min(int(limit or 20), 100))],
        "inspected": inspected,
        "method": "Searched Socrata schemas for the strongest matching active datasets and used cached schemas when available.",
    }


def find_answerable(
    conn: Any,
    rows: Iterable[Dict[str, Any]],
    question: str,
    *,
    limit: int = 8,
    candidate_limit: int = 12,
    schema_loader: Optional[SchemaLoader] = None,
) -> Dict[str, Any]:
    normalized_question = " ".join((question or "").split())
    if not normalized_question:
        raise ValueError("question is required")
    matches = find_city_datasets(rows, normalized_question, limit=max(1, min(int(candidate_limit or 12), 30)))
    date_range = parse_date_range(normalized_question)
    requires_date = date_range is not None
    requires_geo = question_requires_geo(normalized_question)
    count_question = is_count_question(normalized_question)
    answerable_rows = []
    inspected = []
    for match in matches:
        row = match.row
        if not is_schema_search_candidate(row):
            inspected.append({"dataset_id": row["dataset_id"], "answerable": False, "reason": "not an active machine-readable dataset"})
            continue
        try:
            schema = load_schema(conn, row, schema_loader=schema_loader)
            capabilities = summarize_capabilities(row, schema)
        except Exception as exc:
            inspected.append({"dataset_id": row["dataset_id"], "answerable": False, "reason": str(exc)})
            continue
        date_column = choose_date_column(schema, normalized_question) if requires_date else None
        matched_columns = top_matching_columns(schema, normalized_question)
        reasons = []
        blockers = []
        if count_question:
            reasons.append("supports read-only row counts")
        if requires_date:
            if date_column:
                reasons.append("has a date column for the requested time period: %s" % date_column)
            else:
                blockers.append("no date column matched the requested time period")
        elif capabilities["has_date_column"]:
            reasons.append("has date/time columns")
        if requires_geo:
            if capabilities["has_geo_column"]:
                reasons.append("has geography/location columns")
            else:
                blockers.append("no geography/location column matched the question")
        elif capabilities["has_geo_column"]:
            reasons.append("has geography/location columns")
        if matched_columns:
            reasons.append("matched columns: %s" % ", ".join(column["field_name"] for column in matched_columns[:5]))
        answerable = not blockers
        result = {
            "dataset_id": row["dataset_id"],
            "title": row["title"],
            "landing_url": row.get("landing_url") or "",
            "machine_url": row.get("machine_url") or "",
            "label": row["label"],
            "score": row["score"],
            "catalog_match_score": match.score,
            "answerable": answerable,
            "why": reasons,
            "blockers": blockers,
            "date_column": date_column or "",
            "matched_columns": matched_columns,
            "capabilities": capabilities,
            "recommended_tools": recommended_tools(count_question, requires_date),
        }
        answerable_rows.append(result)
        inspected.append({"dataset_id": row["dataset_id"], "answerable": answerable, "blockers": blockers})
    answerable_rows.sort(key=lambda item: (not item["answerable"], -item["catalog_match_score"], -int(item["score"]), item["title"].casefold()))
    return {
        "question": normalized_question,
        "requires": {
            "count": count_question,
            "date_filter": requires_date,
            "geography": requires_geo,
        },
        "datasets": answerable_rows[: max(1, min(int(limit or 8), 50))],
        "inspected": inspected,
        "method": "Ranked catalog matches, inspected cached/fetchable Socrata schemas, and checked required date/geography capabilities.",
    }


def summarize_capabilities(row: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
    columns = schema.get("columns") or []
    date_columns = [column_summary(column) for column in columns if "date" in column_roles(column)]
    geo_columns = [column_summary(column) for column in columns if "geography" in column_roles(column)]
    numeric_columns = [column_summary(column) for column in columns if "numeric" in column_roles(column)]
    categorical_columns = [column_summary(column) for column in columns if "categorical" in column_roles(column)]
    text_columns = [column_summary(column) for column in columns if "text" in column_roles(column)]
    return {
        "dataset_id": row["dataset_id"],
        "title": row["title"],
        "row_count": schema.get("row_count"),
        "column_count": schema.get("column_count", len(columns)),
        "has_schema": bool(columns),
        "has_date_column": bool(date_columns),
        "has_geo_column": bool(geo_columns),
        "has_numeric_column": bool(numeric_columns),
        "has_categorical_column": bool(categorical_columns),
        "supports_row_count": asset_group(row) == "active_dataset" and bool(row.get("machine_url")),
        "date_columns": date_columns[:12],
        "geo_columns": geo_columns[:12],
        "numeric_columns": numeric_columns[:12],
        "categorical_columns": categorical_columns[:20],
        "text_columns": text_columns[:12],
        "source_url": schema.get("source_url") or "",
    }


def load_schema(conn: Any, row: Dict[str, Any], *, schema_loader: Optional[SchemaLoader] = None) -> Dict[str, Any]:
    if schema_loader is not None:
        return schema_loader(conn, row)
    return get_dataset_schema(conn, row["dataset_id"], row.get("modified"))


def is_schema_search_candidate(row: Dict[str, Any]) -> bool:
    return asset_group(row) == "active_dataset" and bool(row.get("machine_url"))


def column_roles(column: Dict[str, Any]) -> List[str]:
    field_name = str(column.get("field_name") or "")
    data_type = str(column.get("data_type") or "").casefold()
    text = normalize_text(" ".join([field_name, str(column.get("name") or ""), str(column.get("description") or "")]))
    terms = set(tokenize(text))
    roles = []
    if data_type in DATE_TYPES or terms.intersection(DATE_TERMS) or re.search(r"\b(?:date|time|year|month)\b", text):
        roles.append("date")
    if data_type in NUMERIC_TYPES or terms.intersection(NUMERIC_TERMS):
        roles.append("numeric")
    if data_type in TEXT_TYPES:
        roles.append("text")
    if terms.intersection(GEO_TERMS) or data_type in {"location", "point", "multipolygon", "polygon", "line"}:
        roles.append("geography")
    if terms.intersection(CATEGORY_TERMS) or "text" in roles:
        roles.append("categorical")
    return sorted(set(roles))


def score_column(column: Dict[str, Any], query: str) -> int:
    query_terms = tokenize(query)
    if not query_terms:
        return 0
    field_text = normalize_text(str(column.get("field_name") or ""))
    name_text = normalize_text(str(column.get("name") or ""))
    description_text = normalize_text(str(column.get("description") or ""))
    type_text = normalize_text(str(column.get("data_type") or ""))
    role_text = " ".join(column_roles(column))
    score = 0
    phrase = normalize_text(query)
    if phrase and phrase in " ".join([field_text, name_text, description_text]):
        score += 18
    for term in query_terms:
        if re.search(r"\b%s\b" % re.escape(term), field_text):
            score += 12
        if re.search(r"\b%s\b" % re.escape(term), name_text):
            score += 10
        if re.search(r"\b%s\b" % re.escape(term), description_text):
            score += 5
        if re.search(r"\b%s\b" % re.escape(term), type_text):
            score += 3
        if re.search(r"\b%s\b" % re.escape(term), role_text):
            score += 8
    roles = set(column_roles(column))
    if query_terms.intersection(DATE_TERMS) and "date" in roles:
        score += 10
    if query_terms.intersection(GEO_TERMS) and "geography" in roles:
        score += 10
    if query_terms.intersection(NUMERIC_TERMS) and "numeric" in roles:
        score += 8
    if query_terms.intersection(CATEGORY_TERMS) and "categorical" in roles:
        score += 6
    return score


def top_matching_columns(schema: Dict[str, Any], question: str, *, limit: int = 8) -> List[Dict[str, Any]]:
    scored = [
        (score_column(column, question), column)
        for column in schema.get("columns") or []
    ]
    scored = [(score, column) for score, column in scored if score > 0]
    scored.sort(key=lambda item: (-item[0], str(item[1].get("field_name") or "")))
    return [
        {
            **column_summary(column),
            "roles": column_roles(column),
            "match_score": score,
        }
        for score, column in scored[: max(1, min(int(limit or 8), 25))]
    ]


def column_summary(column: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "field_name": str(column.get("field_name") or ""),
        "name": str(column.get("name") or ""),
        "data_type": str(column.get("data_type") or ""),
        "description": str(column.get("description") or ""),
    }


def explain_column_match(column: Dict[str, Any], query: str) -> str:
    roles = column_roles(column)
    pieces = []
    if roles:
        pieces.append("roles: %s" % ", ".join(roles))
    matching_terms = sorted(tokenize(query).intersection(tokenize(" ".join([str(column.get("field_name") or ""), str(column.get("name") or ""), str(column.get("description") or "")]))))
    if matching_terms:
        pieces.append("matched terms: %s" % ", ".join(matching_terms[:8]))
    return "; ".join(pieces) or "Column matched query semantics."


def question_requires_geo(question: str) -> bool:
    terms = tokenize(question)
    return bool(terms.intersection(GEO_TERMS))


def recommended_tools(count_question: bool, requires_date: bool) -> List[str]:
    tools = ["get_dataset_capabilities", "get_dataset_schema", "get_sample_rows"]
    if count_question:
        tools.append("query_dataset_count")
    if requires_date and "query_dataset_count" not in tools:
        tools.append("query_dataset_count")
    return tools
