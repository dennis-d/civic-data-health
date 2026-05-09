from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from .models import HealthResult, NormalizedDataset

BOILERPLATE_DESCRIPTIONS = {
    "to be updated",
    "n/a",
    "na",
    "none",
    "not available",
    "no description",
    "no description available",
}

POINT_IN_TIME_TERMS = {
    "annual report",
    "annual progress report",
    "annual highlights",
    "assessment",
    "approved ce",
    "covid",
    "flood",
    "highlights",
    "homepage",
    "hurricane",
    "meals and snacks served",
    "memorial day",
    "pandemic",
    "progress report",
    "report",
    "storm",
    "summer meals",
    "winter storm",
    "year in review",
}

STANDALONE_EVENT_TERMS = {
    "during the pandemic",
    "hurricane harvey",
    "winter storm",
}

MONTH_PATTERN = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"


def score_dataset(dataset: NormalizedDataset, now: Optional[datetime] = None, columns_checked: bool = False) -> HealthResult:
    now = now or datetime.now(timezone.utc)
    score = 100
    issues = []
    remediation = []
    freshness_confidence = "high"
    reference_issue = reference_asset_issue_code(dataset)
    reference_asset = reference_issue is not None
    point_in_time = is_point_in_time_record(dataset)
    if reference_issue:
        issues.append(reference_issue)
        if reference_issue == "socrata_measure_asset":
            remediation.append("Treat this as a Socrata measure/indicator asset, not a machine-readable dataset; keep it out of the active dataset risk queue.")
        else:
            remediation.append("Treat this as a story/reference page, not an active machine-readable dataset; score it outside the active dataset risk queue.")
        freshness_confidence = "not_applicable"
    if point_in_time:
        issues.append("point_in_time_or_event_record")
        remediation.append("Confirm this is an archival/event-specific record; if so, mark it as archival and exclude it from active freshness expectations.")
        freshness_confidence = "not_applicable"

    modified_dt = parse_datetime(dataset.modified)
    cadence_days = parse_accrual_periodicity_days(dataset.accrual_periodicity)

    if modified_dt is None:
        score -= 30
        issues.append("modified_missing")
        remediation.append("Add or repair the dataset modified timestamp.")
        freshness_confidence = "missing"
    elif reference_asset or point_in_time:
        pass
    elif cadence_days is not None:
        age_days = max((now - modified_dt).total_seconds() / 86400, 0)
        if age_days > cadence_days * 1.5:
            score -= 25
            issues.append("freshness_stale_known_cadence")
            remediation.append("Update the dataset or adjust the published refresh cadence.")
    else:
        age_days = max((now - modified_dt).total_seconds() / 86400, 0)
        if age_days > 365:
            score -= 8
            issues.append("freshness_old_unknown_cadence")
            remediation.append("Add accrualPeriodicity so archival/reference data is not misread as stale.")
            freshness_confidence = "low"

    description_issue = description_issue_code(dataset.title, dataset.description)
    if description_issue:
        score -= 15
        issues.append(description_issue)
        remediation.append("Write a specific description that explains contents, coverage, and intended use.")

    if not dataset.publisher or not dataset.contact:
        score -= 15
        if not dataset.publisher:
            issues.append("publisher_missing")
        if not dataset.contact:
            issues.append("contact_missing")
        remediation.append("Publish owner and contact metadata for follow-up questions.")

    metadata_missing = False
    if not dataset.license:
        metadata_missing = True
        issues.append("license_missing")
    if not dataset.category:
        metadata_missing = True
        issues.append("category_missing")
    if not dataset.keywords:
        metadata_missing = True
        issues.append("tags_missing")
    if metadata_missing:
        score -= 10
        remediation.append("Add license, category, and keyword metadata.")

    hard_override = False
    if not dataset.distribution:
        hard_override = not reference_asset and not point_in_time
        issues.append("no_distribution")
        if reference_asset or point_in_time:
            remediation.append("If this record is meant to be machine-readable data, add a distribution; otherwise classify it separately as a reference, indicator, or archive asset.")
        else:
            remediation.append("Publish at least one distribution for machine or user access.")
    elif not dataset.machine_url:
        hard_override = not reference_asset and not point_in_time
        issues.append("no_machine_readable_url")
        if reference_asset or point_in_time:
            remediation.append("If this record is meant to be machine-readable data, add downloadURL or accessURL; otherwise classify it as a reference, indicator, or archive asset.")
        else:
            remediation.append("Add downloadURL or accessURL to at least one distribution.")

    score = max(0, min(100, score))
    label = "good" if score >= 80 else "needs_review" if score >= 50 else "high_risk"
    if hard_override:
        label = "high_risk"

    data_dictionary_quality = {
        "status": "not_checked",
        "issue_codes": ["columns_not_checked"],
        "summary": "Column metadata was not fetched; global score is still comparable.",
    }
    if columns_checked:
        data_dictionary_quality = {
            "status": "checked",
            "issue_codes": [],
            "summary": "Column metadata was checked separately from global score.",
        }

    return HealthResult(
        dataset_id=dataset.dataset_id,
        score=score,
        label=label,
        issue_codes=dedupe(issues),
        remediation=dedupe(remediation),
        freshness_confidence=freshness_confidence,
        data_dictionary_quality=data_dictionary_quality,
    )


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    for candidate in (cleaned, cleaned[:10]):
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def parse_accrual_periodicity_days(value: str) -> Optional[float]:
    if not value:
        return None
    cleaned = value.strip().upper()
    if "/" in cleaned:
        cleaned = cleaned.rsplit("/", 1)[-1]
    match = re.fullmatch(r"P(?:(\d+(?:\.\d+)?)Y)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)W)?(?:(\d+(?:\.\d+)?)D)?", cleaned)
    if not match:
        return None
    years, months, weeks, days = (float(part) if part else 0.0 for part in match.groups())
    total = years * 365 + months * 30 + weeks * 7 + days
    return total or None


def description_issue_code(title: str, description: str) -> Optional[str]:
    cleaned = " ".join((description or "").split())
    if not cleaned:
        return "description_missing"
    if cleaned.casefold() == " ".join((title or "").split()).casefold():
        return "description_same_as_title"
    if cleaned.casefold() in BOILERPLATE_DESCRIPTIONS:
        return "description_boilerplate"
    if len(cleaned) < 80:
        return "description_too_short"
    return None


def is_point_in_time_record(dataset: NormalizedDataset) -> bool:
    if dataset.accrual_periodicity:
        return False
    text = " ".join([dataset.title or "", dataset.description or ""]).casefold()
    if any(term in text for term in STANDALONE_EVENT_TERMS):
        return True
    has_year = re.search(r"\b(?:19|20)\d{2}(?:\s*[-/]\s*(?:19|20)?\d{2})?\b|\bfy\s*(?:19|20)\d{2}\b", text)
    if has_year and is_month_or_quarter_snapshot(text):
        return True
    return bool(has_year and any(term in text for term in POINT_IN_TIME_TERMS))


def is_month_or_quarter_snapshot(text: str) -> bool:
    year = r"(?:19|20)\d{2}"
    if re.search(rf"\b{MONTH_PATTERN}\b\s+{year}\b", text):
        return True
    if re.search(rf"\b{year}\b\s*\(\s*{MONTH_PATTERN}\s*[-/]\s*{MONTH_PATTERN}\s*\)", text):
        return True
    if re.search(rf"\b(?:q[1-4]\s+{year}|{year}\s+q[1-4])\b", text):
        return True
    return False


def reference_asset_issue_code(dataset: NormalizedDataset) -> Optional[str]:
    asset_type = dataset.asset_type.casefold()
    if asset_type == "story":
        return "socrata_story_page"
    if asset_type == "measure":
        return "socrata_measure_asset"
    if asset_type in {"href", "blob", "file"}:
        return "socrata_reference_asset"
    return None


def dedupe(values):
    seen = set()
    out = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
