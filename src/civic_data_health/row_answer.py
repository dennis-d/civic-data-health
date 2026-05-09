from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, Optional

from .analysis import asset_group
from .discovery import find_city_datasets
from .socrata import count_rows, get_dataset_schema, validate_field_name

SchemaLoader = Callable[[Any, Dict[str, Any]], Dict[str, Any]]
CountLoader = Callable[[str, Optional[str]], int]

COUNT_RE = re.compile(r"\b(?:how many|count|number of|total number of|total)\b", re.I)
DATE_LITERAL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2})?$")
DATE_TYPES = {"calendar_date", "date", "floating_timestamp", "fixed_timestamp"}
DATE_HINTS = {
    "issued": {"issue", "issued"},
    "created": {"create", "created"},
    "reported": {"report", "reported"},
    "closed": {"close", "closed"},
    "updated": {"update", "updated", "modified"},
}


@dataclass(frozen=True)
class DateRange:
    label: str
    start: str
    end: str


def answer_row_level_question(
    conn,
    rows: Iterable[Dict[str, Any]],
    question: str,
    *,
    now: Optional[datetime] = None,
    schema_loader: SchemaLoader = None,
    count_loader: CountLoader = count_rows,
) -> Optional[Dict[str, Any]]:
    if not is_count_question(question):
        return None
    schema_loader = schema_loader or load_schema_for_row
    date_range = parse_date_range(question, now=now)
    inspected = []
    for match in find_city_datasets(rows, question, limit=8):
        row = match.row
        if not is_queryable_row(row):
            inspected.append({"dataset_id": row["dataset_id"], "reason": "not an active machine-readable dataset"})
            continue
        try:
            schema = schema_loader(conn, row)
            date_column = choose_date_column(schema, question) if date_range else None
            if date_range and date_column is None:
                inspected.append({"dataset_id": row["dataset_id"], "reason": "no date column matched the question"})
                continue
            where = build_date_where(date_column, date_range) if date_range else None
            count = count_loader(row["dataset_id"], where)
        except Exception as exc:
            inspected.append({"dataset_id": row["dataset_id"], "reason": str(exc)})
            continue
        dataset = match.to_result()
        caveats = list(dataset["caveats"])
        caveats.append("Computed from Socrata rows at request time; catalog metadata and live row data may refresh on different schedules.")
        return {
            "question": question,
            "computed": True,
            "answer_type": "count",
            "answer": format_count_answer(count, row, date_range),
            "result": {"count": count},
            "dataset": dataset,
            "datasets": [dataset],
            "query": {
                "dataset_id": row["dataset_id"],
                "operation": "count",
                "where": where or "",
                "date_column": date_column or "",
                "date_range": date_range.__dict__ if date_range else None,
            },
            "caveats": caveats,
            "inspected_candidates": inspected,
        }
    return None


def load_schema_for_row(conn, row: Dict[str, Any]) -> Dict[str, Any]:
    return get_dataset_schema(conn, row["dataset_id"], row.get("modified"))


def is_count_question(question: str) -> bool:
    return bool(COUNT_RE.search(question))


def is_queryable_row(row: Dict[str, Any]) -> bool:
    return asset_group(row) == "active_dataset" and bool(row.get("machine_url"))


def parse_date_range(question: str, *, now: Optional[datetime] = None) -> Optional[DateRange]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    normalized = question.casefold()
    year_match = re.search(r"\b((?:19|20)\d{2})\b", normalized)
    if year_match:
        year = int(year_match.group(1))
        return DateRange(str(year), "%04d-01-01T00:00:00" % year, "%04d-01-01T00:00:00" % (year + 1))
    if "last month" in normalized:
        year = current.year
        month = current.month - 1
        if month == 0:
            year -= 1
            month = 12
        end_year = year + 1 if month == 12 else year
        end_month = 1 if month == 12 else month + 1
        return DateRange("last month", "%04d-%02d-01T00:00:00" % (year, month), "%04d-%02d-01T00:00:00" % (end_year, end_month))
    if "this month" in normalized:
        end_year = current.year + 1 if current.month == 12 else current.year
        end_month = 1 if current.month == 12 else current.month + 1
        return DateRange("this month", "%04d-%02d-01T00:00:00" % (current.year, current.month), "%04d-%02d-01T00:00:00" % (end_year, end_month))
    if "last year" in normalized:
        year = current.year - 1
        return DateRange("last year", "%04d-01-01T00:00:00" % year, "%04d-01-01T00:00:00" % (year + 1))
    if "this year" in normalized:
        return DateRange("this year", "%04d-01-01T00:00:00" % current.year, "%04d-01-01T00:00:00" % (current.year + 1))
    return None


def choose_date_column(schema: Dict[str, Any], question: str) -> Optional[str]:
    terms = set(re.findall(r"[a-z0-9]+", question.casefold()))
    best_field = None
    best_score = 0
    for column in schema.get("columns") or []:
        field_name = str(column.get("field_name") or "")
        if not field_name:
            continue
        text = " ".join([field_name, str(column.get("name") or ""), str(column.get("description") or "")]).casefold()
        data_type = str(column.get("data_type") or "").casefold()
        score = 0
        if data_type in DATE_TYPES:
            score += 10
        if "date" in text or "time" in text:
            score += 8
        for term in terms:
            if term in text:
                score += 12
        for term, hints in DATE_HINTS.items():
            if term in terms and any(hint in text for hint in hints):
                score += 35
        if field_name in {"issue_date", "issued_date", "created_date", "date", "calendar_date"}:
            score += 15
        if score > best_score:
            best_field = field_name
            best_score = score
    return best_field if best_score > 0 else None


def build_date_where(date_column: Optional[str], date_range: Optional[DateRange]) -> Optional[str]:
    if date_column is None or date_range is None:
        return None
    field_name = validate_field_name(date_column)
    start = validate_date_literal(date_range.start)
    end = validate_date_literal(date_range.end)
    return "%s >= '%s' AND %s < '%s'" % (field_name, start, field_name, end)


def validate_date_literal(value: str) -> str:
    cleaned = value.strip()
    if not DATE_LITERAL_RE.fullmatch(cleaned):
        raise ValueError("unsafe date literal: %s" % value)
    datetime.fromisoformat(cleaned)
    return cleaned


def format_count_answer(count: int, row: Dict[str, Any], date_range: Optional[DateRange]) -> str:
    scope = " for %s" % date_range.label if date_range else ""
    return "Austin Open Data has %s matching row%s%s in %s (%s)." % (
        count,
        "" if count == 1 else "s",
        scope,
        row["title"],
        row["dataset_id"],
    )
