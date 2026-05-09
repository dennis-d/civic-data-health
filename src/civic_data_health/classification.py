from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .models import NormalizedDataset

CLASSIFICATION_GROUPS = (
    "active_dataset",
    "needs_manual_review",
    "archive_snapshot",
    "event_specific",
    "measure",
    "story_reference",
)

VALID_CLASSIFICATION_GROUPS = set(CLASSIFICATION_GROUPS)
FRESHNESS_EXEMPT_GROUPS = {"archive_snapshot", "event_specific", "measure", "story_reference"}
ACTIVE_LIKE_GROUPS = {"active_dataset", "needs_manual_review"}

REFERENCE_ASSET_TYPES = {"story", "href", "blob", "file"}
ACTIVE_ASSET_TYPES = {"", "dataset", "table", "tabular"}

EVENT_TERMS = {
    "covid",
    "flood",
    "hurricane",
    "memorial day",
    "pandemic",
    "storm",
    "winter storm",
}

STANDALONE_EVENT_TERMS = {
    "during the pandemic",
    "hurricane harvey",
    "winter storm",
}

REPORT_TERMS = {
    "annual report",
    "annual progress report",
    "annual highlights",
    "approved ce",
    "assessment",
    "highlights",
    "homepage",
    "meals and snacks served",
    "progress report",
    "report",
    "summer meals",
    "year in review",
}

MONTH_PATTERN = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
SNAPSHOT_RANGE_TERMS = {"data", "extract", "snapshot", "statistics", "statistic", "stats", "summary"}
SNAPSHOT_SINGLE_YEAR_TERMS = {"extract", "snapshot", "statistics", "statistic", "stats"}


@dataclass(frozen=True)
class ClassificationResult:
    group: str
    confidence: str
    evidence: List[str]
    reason: str
    override_applied: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group": self.group,
            "confidence": self.confidence,
            "evidence": dedupe(self.evidence),
            "reason": self.reason,
            "override_applied": self.override_applied,
        }


def load_classification_overrides(path: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    overrides = payload.get("overrides") if isinstance(payload, dict) else None
    if not isinstance(overrides, dict):
        raise ValueError("classification overrides must contain an object field named 'overrides'")

    normalized: Dict[str, Dict[str, Any]] = {}
    for raw_dataset_id, raw_override in overrides.items():
        dataset_id = str(raw_dataset_id).strip().lower()
        if not re.fullmatch(r"[a-z0-9]{4}-[a-z0-9]{4}", dataset_id):
            raise ValueError("invalid override dataset id: %s" % raw_dataset_id)
        if not isinstance(raw_override, dict):
            raise ValueError("override for %s must be an object" % dataset_id)
        group = str(raw_override.get("group") or "").strip()
        if group not in VALID_CLASSIFICATION_GROUPS:
            raise ValueError("override for %s has invalid group: %s" % (dataset_id, group))
        evidence = raw_override.get("evidence") or ["manual_override"]
        if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
            raise ValueError("override evidence for %s must be a list of strings" % dataset_id)
        normalized[dataset_id] = {
            "group": group,
            "confidence": str(raw_override.get("confidence") or "manual"),
            "evidence": evidence,
            "reason": str(raw_override.get("reason") or "Manual classification override."),
        }
    return normalized


def classify_dataset(
    dataset: NormalizedDataset,
    overrides: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> ClassificationResult:
    base = infer_classification(dataset)
    override = overrides.get(dataset.dataset_id) if overrides else None
    if not override:
        return base
    return ClassificationResult(
        group=str(override["group"]),
        confidence=str(override.get("confidence") or "manual"),
        evidence=dedupe(["manual_override", *base.evidence, *list(override.get("evidence") or [])]),
        reason=str(override.get("reason") or base.reason),
        override_applied=True,
    )


def infer_classification(dataset: NormalizedDataset) -> ClassificationResult:
    asset_type = (dataset.asset_type or "").strip().casefold()
    if asset_type == "measure":
        return ClassificationResult(
            group="measure",
            confidence="high",
            evidence=["socrata_measure_asset"],
            reason="Socrata view metadata identifies this record as a measure or indicator asset.",
        )
    if asset_type == "story":
        return ClassificationResult(
            group="story_reference",
            confidence="high",
            evidence=["socrata_story_asset"],
            reason="Socrata view metadata identifies this record as a story page.",
        )
    if asset_type in REFERENCE_ASSET_TYPES or asset_type not in ACTIVE_ASSET_TYPES:
        return ClassificationResult(
            group="story_reference",
            confidence="medium",
            evidence=["socrata_reference_asset"],
            reason="Socrata view metadata identifies this as a non-table reference asset.",
        )

    text = searchable_text(dataset)
    title_text = (dataset.title or "").casefold()
    has_year = has_year_expression(text)
    has_title_year = has_year_expression(title_text)
    cadence_evidence = ["known_cadence"] if dataset.accrual_periodicity else []

    if any(term in text for term in STANDALONE_EVENT_TERMS) or (has_year and any(term in text for term in EVENT_TERMS)):
        return ClassificationResult(
            group="event_specific",
            confidence="high",
            evidence=dedupe([*cadence_evidence, "event_keyword"]),
            reason="The title or description points to a bounded event rather than an ongoing active dataset.",
        )
    if has_title_year and is_month_or_quarter_snapshot(title_text):
        return ClassificationResult(
            group="archive_snapshot",
            confidence="high",
            evidence=dedupe([*cadence_evidence, "month_quarter_snapshot"]),
            reason="The record names a specific month, quarter, or month range snapshot.",
        )
    if has_title_year and is_bounded_year_snapshot(title_text):
        return ClassificationResult(
            group="archive_snapshot",
            confidence="high",
            evidence=dedupe([*cadence_evidence, "bounded_year_range"]),
            reason="The record names a bounded year range or year-specific statistics snapshot.",
        )
    if has_title_year and any(term in title_text for term in REPORT_TERMS):
        return ClassificationResult(
            group="archive_snapshot",
            confidence="medium",
            evidence=dedupe([*cadence_evidence, "bounded_year_range", "report_keyword"]),
            reason="The record looks like a dated report or highlights page, not a continuously refreshed dataset.",
        )
    if has_title_year and not dataset.accrual_periodicity:
        return ClassificationResult(
            group="needs_manual_review",
            confidence="low",
            evidence=["year_without_cadence"],
            reason="The record contains a year but does not publish a refresh cadence, so classification needs human review.",
        )

    evidence = []
    if dataset.accrual_periodicity:
        evidence.append("known_cadence")
    if dataset.machine_url:
        evidence.append("machine_readable_distribution")
    if not evidence:
        evidence.append("default_active_dataset")
    return ClassificationResult(
        group="active_dataset",
        confidence="high" if "known_cadence" in evidence or "machine_readable_distribution" in evidence else "medium",
        evidence=evidence,
        reason="No evidence indicates this is a bounded archive, story, measure, or event-specific asset.",
    )


def is_point_in_time_record(dataset: NormalizedDataset) -> bool:
    return infer_classification(dataset).group in {"archive_snapshot", "event_specific"}


def searchable_text(dataset: NormalizedDataset) -> str:
    return " ".join([dataset.title or "", dataset.description or ""]).casefold()


def has_year_expression(text: str) -> bool:
    return bool(re.search(r"\b(?:19|20)\d{2}(?:\s*[-/]\s*(?:19|20)?\d{2})?\b|\bfy\s*(?:19|20)\d{2}\b", text))


def is_month_or_quarter_snapshot(text: str) -> bool:
    year = r"(?:19|20)\d{2}"
    if re.search(rf"\b{MONTH_PATTERN}\b\s+{year}\b", text):
        return True
    if re.search(rf"\b{year}\b\s*\(\s*{MONTH_PATTERN}\s*[-/]\s*{MONTH_PATTERN}\s*\)", text):
        return True
    if re.search(rf"\b(?:q[1-4]\s+{year}|{year}\s+q[1-4])\b", text):
        return True
    return False


def is_bounded_year_snapshot(text: str) -> bool:
    year = r"(?:19|20)\d{2}"
    has_year_range = re.search(rf"\b{year}\s*[-/]\s*(?:{year}|\d{{2}})\b", text)
    if has_year_range and any(has_word(text, term) for term in SNAPSHOT_RANGE_TERMS):
        return True
    if re.search(rf"\b{year}\b", text) and any(has_word(text, term) for term in SNAPSHOT_SINGLE_YEAR_TERMS):
        return True
    return False


def has_word(text: str, word: str) -> bool:
    return bool(re.search(r"\b%s\b" % re.escape(word), text))


def dedupe(values: List[str]) -> List[str]:
    seen = set()
    out = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
