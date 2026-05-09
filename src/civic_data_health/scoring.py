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


def score_dataset(dataset: NormalizedDataset, now: Optional[datetime] = None, columns_checked: bool = False) -> HealthResult:
    now = now or datetime.now(timezone.utc)
    score = 100
    issues = []
    remediation = []
    freshness_confidence = "high"

    modified_dt = parse_datetime(dataset.modified)
    cadence_days = parse_accrual_periodicity_days(dataset.accrual_periodicity)

    if modified_dt is None:
        score -= 30
        issues.append("modified_missing")
        remediation.append("Add or repair the dataset modified timestamp.")
        freshness_confidence = "missing"
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
        hard_override = True
        issues.append("no_distribution")
        remediation.append("Publish at least one distribution for machine or user access.")
    elif not dataset.machine_url:
        hard_override = True
        issues.append("no_machine_readable_url")
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


def dedupe(values):
    seen = set()
    out = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out

