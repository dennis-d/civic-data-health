from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class NormalizedDataset:
    dataset_id: str
    title: str
    description: str
    modified: Optional[str]
    publisher: str
    contact: str
    keywords: List[str]
    license: str
    category: str
    accrual_periodicity: str
    landing_url: str
    distribution: List[Dict[str, Any]]
    machine_url: str
    raw: Dict[str, Any]
    asset_type: str = ""


@dataclass
class SkippedRecord:
    source_index: int
    title: str
    identifier_candidate: str
    reason_code: str
    raw_excerpt: str


@dataclass
class HealthResult:
    dataset_id: str
    score: int
    label: str
    issue_codes: List[str]
    remediation: List[str]
    freshness_confidence: str
    data_dictionary_quality: Dict[str, Any]
    classification: Dict[str, Any]
