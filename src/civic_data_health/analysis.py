from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List, Literal, Optional

AssetGroup = Literal["active_dataset", "measure", "story_reference", "all"]

REFERENCE_ASSET_TYPES = {"story", "href", "blob", "file"}

ASSET_GROUP_LABELS = {
    "active_dataset": "Active datasets",
    "measure": "Measures and indicators",
    "story_reference": "Stories and reference assets",
    "all": "All assets",
}

ISSUE_DETAILS: Dict[str, Dict[str, Any]] = {
    "modified_missing": {
        "title": "Missing modified date",
        "plain_english": "The catalog record does not publish a reliable last-modified date.",
        "recommended_action": "Add or repair the modified timestamp in the catalog metadata.",
        "priority": 95,
        "effort": "low",
    },
    "freshness_stale_known_cadence": {
        "title": "Stale against published cadence",
        "plain_english": "The dataset has a stated refresh cadence, but the last modified date is well past that expected interval.",
        "recommended_action": "Update the dataset or correct the published refresh cadence.",
        "priority": 90,
        "effort": "medium",
    },
    "freshness_old_unknown_cadence": {
        "title": "Old with unknown cadence",
        "plain_english": "The dataset has not changed in over a year and does not say how often it should refresh.",
        "recommended_action": "Add accrualPeriodicity so users know whether the data is stale, archival, or reference material.",
        "priority": 65,
        "effort": "low",
    },
    "description_missing": {
        "title": "Missing description",
        "plain_english": "The record does not explain what the data covers or how it should be used.",
        "recommended_action": "Write a specific description with coverage, source system, update behavior, and intended use.",
        "priority": 85,
        "effort": "low",
    },
    "description_same_as_title": {
        "title": "Description duplicates title",
        "plain_english": "The description repeats the title instead of explaining the dataset.",
        "recommended_action": "Replace the duplicate description with concrete coverage and usage details.",
        "priority": 80,
        "effort": "low",
    },
    "description_too_short": {
        "title": "Thin description",
        "plain_english": "The description is too short to help a user understand content, coverage, or limitations.",
        "recommended_action": "Expand the description with what is measured, date/geography coverage, and known limitations.",
        "priority": 70,
        "effort": "low",
    },
    "description_boilerplate": {
        "title": "Boilerplate description",
        "plain_english": "The description is generic placeholder text.",
        "recommended_action": "Replace placeholder text with a dataset-specific description.",
        "priority": 75,
        "effort": "low",
    },
    "publisher_missing": {
        "title": "Missing publisher",
        "plain_english": "The catalog record does not clearly identify the owning publisher.",
        "recommended_action": "Add the responsible department or publishing organization.",
        "priority": 80,
        "effort": "low",
    },
    "contact_missing": {
        "title": "Missing contact",
        "plain_english": "Users do not have a clear contact for questions or corrections.",
        "recommended_action": "Add a monitored owner or data steward contact.",
        "priority": 80,
        "effort": "low",
    },
    "license_missing": {
        "title": "Missing license",
        "plain_english": "The catalog record does not state reuse rights.",
        "recommended_action": "Add the city's standard open data license or another appropriate license.",
        "priority": 78,
        "effort": "low",
    },
    "category_missing": {
        "title": "Missing category",
        "plain_english": "The record is harder to browse because it is not assigned to a catalog category.",
        "recommended_action": "Assign a category that matches the publishing department or public service area.",
        "priority": 45,
        "effort": "low",
    },
    "tags_missing": {
        "title": "Missing tags",
        "plain_english": "The record is harder to discover because it has no keywords.",
        "recommended_action": "Add search-friendly keywords for department, program, geography, and topic.",
        "priority": 45,
        "effort": "low",
    },
    "no_distribution": {
        "title": "No distribution",
        "plain_english": "The record does not publish a downloadable or accessible distribution in the DCAT catalog.",
        "recommended_action": "If this is an active dataset, add a machine-readable downloadURL or accessURL. If it is a story, measure, or archive, classify it separately.",
        "priority": 88,
        "effort": "medium",
    },
    "no_machine_readable_url": {
        "title": "No machine-readable URL",
        "plain_english": "The record has a distribution, but the catalog does not expose a clear machine-readable URL.",
        "recommended_action": "Add downloadURL or accessURL for the published data file or API endpoint.",
        "priority": 88,
        "effort": "medium",
    },
    "socrata_story_page": {
        "title": "Socrata story page",
        "plain_english": "This is a narrative or reference page, not a normal active dataset.",
        "recommended_action": "Keep it out of active dataset risk ranking, but clean up metadata if it remains in the catalog.",
        "priority": 25,
        "effort": "low",
    },
    "socrata_measure_asset": {
        "title": "Socrata measure asset",
        "plain_english": "This is a Socrata measure or indicator asset, not a normal machine-readable dataset.",
        "recommended_action": "Track it as an indicator asset and do not penalize it as an active dataset solely for missing data distribution.",
        "priority": 25,
        "effort": "low",
    },
    "socrata_reference_asset": {
        "title": "Socrata reference asset",
        "plain_english": "This is a reference asset rather than a standard dataset table.",
        "recommended_action": "Classify it outside the active dataset queue and keep metadata clear.",
        "priority": 25,
        "effort": "low",
    },
    "point_in_time_or_event_record": {
        "title": "Point-in-time or event record",
        "plain_english": "This appears to represent a specific year, incident, report, or archive item.",
        "recommended_action": "Confirm whether it is archival. If yes, mark it clearly so users do not expect continuing refreshes.",
        "priority": 35,
        "effort": "low",
    },
    "columns_not_checked": {
        "title": "Column metadata not checked",
        "plain_english": "Column metadata was not part of the global score.",
        "recommended_action": "Run column enrichment separately when validating data dictionaries.",
        "priority": 15,
        "effort": "medium",
    },
}


def asset_group(row: Dict[str, Any]) -> str:
    asset_type = str(row.get("asset_type") or "").casefold()
    if asset_type == "measure":
        return "measure"
    if "point_in_time_or_event_record" in row.get("issue_codes", []):
        return "story_reference"
    if asset_type in REFERENCE_ASSET_TYPES or (asset_type and asset_type != "measure"):
        return "story_reference"
    return "active_dataset"


def asset_group_label(group: str) -> str:
    return ASSET_GROUP_LABELS.get(group, group.replace("_", " ").title())


def summarize_asset_groups(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    summaries: Dict[str, Dict[str, Any]] = {}
    grouped: Dict[str, List[Dict[str, Any]]] = {"active_dataset": [], "measure": [], "story_reference": []}
    for row in rows:
        grouped.setdefault(asset_group(row), []).append(row)
    for group, group_rows in grouped.items():
        label_counts = Counter(row["label"] for row in group_rows)
        issue_counts = Counter(issue for row in group_rows for issue in row["issue_codes"])
        average = round(sum(int(row["score"]) for row in group_rows) / len(group_rows), 2) if group_rows else 0.0
        summaries[group] = {
            "group": group,
            "label": asset_group_label(group),
            "count": len(group_rows),
            "average_score": average,
            "labels": {
                "high_risk": label_counts.get("high_risk", 0),
                "needs_review": label_counts.get("needs_review", 0),
                "good": label_counts.get("good", 0),
            },
            "top_issues": [
                {"issue_code": issue, "count": count, "title": issue_title(issue)}
                for issue, count in issue_counts.most_common(8)
            ],
        }
    return summaries


def filter_by_asset_group(rows: Iterable[Dict[str, Any]], group: str) -> List[Dict[str, Any]]:
    if group == "all":
        return list(rows)
    return [row for row in rows if asset_group(row) == group]


def top_actionable_fixes(rows: Iterable[Dict[str, Any]], *, limit: int = 25, group: str = "active_dataset") -> List[Dict[str, Any]]:
    candidates = []
    for row in filter_by_asset_group(rows, group):
        actionable_issues = [issue for issue in row["issue_codes"] if issue in ISSUE_DETAILS and issue not in {"socrata_story_page", "socrata_measure_asset", "socrata_reference_asset", "point_in_time_or_event_record", "columns_not_checked"}]
        if not actionable_issues:
            continue
        issue_priority = sum(int(ISSUE_DETAILS[issue]["priority"]) for issue in actionable_issues)
        label_boost = {"high_risk": 100, "needs_review": 40, "good": 0}.get(row["label"], 0)
        active_boost = 30 if asset_group(row) == "active_dataset" else 0
        priority = issue_priority + label_boost + active_boost - int(row["score"])
        candidates.append(
            {
                "dataset_id": row["dataset_id"],
                "title": row["title"],
                "score": row["score"],
                "label": row["label"],
                "asset_group": asset_group(row),
                "asset_group_label": asset_group_label(asset_group(row)),
                "asset_type": row.get("asset_type") or "dataset",
                "owner": row.get("publisher") or row.get("contact") or "Missing",
                "contact": row.get("contact") or "",
                "landing_url": row.get("landing_url") or "",
                "priority": priority,
                "issue_codes": actionable_issues,
                "recommended_actions": [ISSUE_DETAILS[issue]["recommended_action"] for issue in actionable_issues],
            }
        )
    candidates.sort(key=lambda item: (-int(item["priority"]), int(item["score"]), item["title"].casefold()))
    return candidates[: max(1, min(int(limit or 25), 100))]


def explain_issue(issue_code: str) -> Dict[str, Any]:
    normalized = issue_code.strip()
    details = ISSUE_DETAILS.get(normalized)
    if details is None:
        return {
            "issue_code": normalized,
            "title": normalized.replace("_", " ").title(),
            "plain_english": "This issue code is present in the scoring result but does not yet have a detailed explanation.",
            "recommended_action": "Review the dataset detail page and scoring rule that emitted this issue.",
            "priority": 0,
            "effort": "unknown",
        }
    return {"issue_code": normalized, **details}


def explain_dataset_issues(row: Dict[str, Any], issue_code: Optional[str] = None) -> Dict[str, Any]:
    issues = row["issue_codes"]
    if issue_code:
        normalized = issue_code.strip()
        if normalized not in issues:
            raise ValueError("Issue %s is not present on dataset %s" % (normalized, row["dataset_id"]))
        issues = [normalized]
    return {
        "dataset_id": row["dataset_id"],
        "title": row["title"],
        "label": row["label"],
        "score": row["score"],
        "asset_group": asset_group(row),
        "asset_group_label": asset_group_label(asset_group(row)),
        "issues": [explain_issue(issue) for issue in issues],
    }


def draft_department_email(row: Dict[str, Any], *, contact_name: str = "", sender_name: str = "") -> Dict[str, str]:
    actionable = top_actionable_fixes([row], limit=1, group="all")
    actions = actionable[0]["recommended_actions"] if actionable else row["remediation"]
    greeting = "Hello"
    if contact_name.strip():
        greeting += " %s" % contact_name.strip()
    sender = sender_name.strip() or "Civic Data Health"
    subject = "Open data metadata cleanup: %s" % (row["title"] or row["dataset_id"])
    action_lines = "\n".join("- %s" % action for action in actions[:5])
    issue_lines = ", ".join(row["issue_codes"])
    body = """{greeting},

I reviewed the Austin Open Data catalog record for "{title}" ({dataset_id}) and found a few metadata items that would improve public usability.

Current result:
- Label: {label}
- Score: {score}
- Asset type: {asset_type}
- Issues: {issues}

Recommended next steps:
{actions}

Catalog record: {url}

This is an independent public metadata review, not an official City of Austin notice.

Thank you,
{sender}
""".format(
        greeting=greeting,
        title=row["title"] or row["dataset_id"],
        dataset_id=row["dataset_id"],
        label=row["label"],
        score=row["score"],
        asset_type=row.get("asset_type") or "active dataset",
        issues=issue_lines,
        actions=action_lines,
        url=row.get("landing_url") or "",
        sender=sender,
    )
    return {"subject": subject, "body": body}


def issue_title(issue_code: str) -> str:
    return str(ISSUE_DETAILS.get(issue_code, {}).get("title") or issue_code.replace("_", " ").title())
