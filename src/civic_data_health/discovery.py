from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence, Set

from .analysis import asset_group, asset_group_label

STOPWORDS = {
    "a",
    "about",
    "and",
    "any",
    "are",
    "austin",
    "can",
    "city",
    "could",
    "data",
    "dataset",
    "datasets",
    "do",
    "find",
    "for",
    "get",
    "has",
    "have",
    "how",
    "i",
    "in",
    "is",
    "me",
    "near",
    "of",
    "on",
    "open",
    "show",
    "shows",
    "the",
    "there",
    "to",
    "what",
    "where",
    "with",
    "would",
}

CITY_TOPIC_HINTS: Dict[str, Set[str]] = {
    "public_safety": {
        "911",
        "apd",
        "arrest",
        "cad",
        "call",
        "calls",
        "crime",
        "dispatch",
        "ems",
        "fire",
        "incident",
        "incidents",
        "police",
        "public safety",
    },
    "transportation": {
        "bike",
        "bicycle",
        "bus",
        "capmetro",
        "collision",
        "crash",
        "gtfs",
        "mobility",
        "parking",
        "sidewalk",
        "street",
        "traffic",
        "transit",
        "transportation",
    },
    "development_permits": {
        "building",
        "code",
        "construction",
        "development",
        "inspection",
        "permit",
        "permits",
        "site plan",
        "zoning",
    },
    "housing": {
        "affordable",
        "eviction",
        "homeless",
        "housing",
        "rental",
        "shelter",
        "short term rental",
        "str",
    },
    "finance_budget": {
        "bond",
        "budget",
        "expense",
        "expenditure",
        "fee",
        "finance",
        "financial",
        "revenue",
        "tax",
    },
    "environment_utilities": {
        "creek",
        "drainage",
        "electric",
        "energy",
        "environment",
        "flood",
        "recycling",
        "trash",
        "utility",
        "waste",
        "water",
        "watershed",
    },
    "health_food": {
        "child care",
        "food",
        "health",
        "inspection",
        "restaurant",
        "safety",
    },
    "land_maps": {
        "address",
        "boundary",
        "gis",
        "land",
        "map",
        "parcel",
        "property",
        "zoning",
    },
    "service_requests": {
        "311",
        "complaint",
        "request",
        "service",
        "sr",
        "ticket",
    },
    "civic_governance": {
        "agenda",
        "board",
        "boards",
        "campaign",
        "city council",
        "commission",
        "commissions",
        "council",
        "councilmember",
        "election",
        "ethics",
        "governance",
        "lobbyist",
        "mayor",
        "meeting",
        "minutes",
        "ordinance",
        "resolution",
        "vote",
        "voting",
    },
    "parks_culture": {
        "arts",
        "culture",
        "library",
        "park",
        "parks",
        "recreation",
        "trail",
    },
}

HIGH_INTENT_TERMS = {
    "311",
    "budget",
    "cad",
    "calls",
    "crime",
    "crash",
    "flood",
    "gtfs",
    "incident",
    "incidents",
    "inspection",
    "inspections",
    "parcel",
    "permit",
    "permits",
    "property",
    "restaurant",
    "revenue",
    "traffic",
    "zoning",
}


@dataclass
class DiscoveryMatch:
    row: Dict[str, Any]
    score: int
    matched_terms: List[str]
    matched_topics: List[str]
    field_matches: List[str]

    def to_result(self) -> Dict[str, Any]:
        row = self.row
        caveats = []
        if asset_group(row) != "active_dataset":
            caveats.append("Classification is %s, so verify it is appropriate for an operational data need." % asset_group_label(asset_group(row)))
        if row["label"] != "good":
            caveats.append("Health label is %s; review metadata issues before relying on it." % row["label"])
        if not row.get("machine_url"):
            caveats.append("No machine-readable URL is exposed in the catalog metadata.")
        if "freshness_old_unknown_cadence" in row.get("issue_codes", []):
            caveats.append("Freshness confidence is low because no update cadence is published.")
        return {
            "dataset_id": row["dataset_id"],
            "title": row["title"],
            "description": row.get("description") or "",
            "url": row.get("landing_url") or "",
            "machine_url": row.get("machine_url") or "",
            "category": row.get("category") or "",
            "publisher": row.get("publisher") or "",
            "contact": row.get("contact") or "",
            "modified": row.get("modified") or "",
            "score": row["score"],
            "label": row["label"],
            "classification": row.get("classification") or {},
            "asset_group": asset_group(row),
            "asset_group_label": asset_group_label(asset_group(row)),
            "match_score": self.score,
            "matched_terms": self.matched_terms,
            "matched_topics": self.matched_topics,
            "field_matches": self.field_matches,
            "why_this_matches": build_match_explanation(row, self.matched_terms, self.matched_topics, self.field_matches),
            "caveats": caveats,
        }


def answer_city_data_question(rows: Iterable[Dict[str, Any]], question: str, *, limit: int = 8) -> Dict[str, Any]:
    matches = find_city_datasets(rows, question, limit=limit)
    if matches:
        answer = "I found %s Austin Open Data record%s that likely match this question." % (len(matches), "" if len(matches) == 1 else "s")
    else:
        answer = "I did not find a strong catalog match. Try naming the department, program, topic, or record type."
    return {
        "question": question,
        "answer": answer,
        "interpreted_topics": detect_topics(question),
        "expanded_terms": sorted(expand_query_terms(tokenize(question))),
        "datasets": [match.to_result() for match in matches],
        "method": "Deterministic lexical ranking over Austin DCAT metadata with civic topic expansion. It does not query live dataset rows.",
    }


def find_city_datasets(rows: Iterable[Dict[str, Any]], question: str, *, limit: int = 10) -> List[DiscoveryMatch]:
    direct_terms = tokenize(question)
    query_terms = expand_query_terms(direct_terms)
    if not query_terms:
        return []
    topic_matches = detect_topics(question)
    matches = [match for row in rows if (match := score_row(row, query_terms, topic_matches, direct_terms)).score > 0]
    matches.sort(key=lambda match: (-match.score, group_rank(asset_group(match.row)), -int(match.row["score"]), match.row["title"].casefold()))
    return matches[: max(1, min(int(limit or 10), 100))]


def score_row(row: Dict[str, Any], query_terms: Set[str], topic_matches: Sequence[str], direct_terms: Set[str]) -> DiscoveryMatch:
    fields = {
        "dataset_id": normalize_text(row["dataset_id"]),
        "title": normalize_text(row["title"]),
        "keywords": normalize_text(" ".join(row.get("keywords") or [])),
        "category": normalize_text(row.get("category") or ""),
        "publisher": normalize_text(row.get("publisher") or ""),
        "description": normalize_text(row.get("description") or ""),
        "classification": normalize_text(
            " ".join(
                [
                    str((row.get("classification") or {}).get("group") or ""),
                    str((row.get("classification") or {}).get("reason") or ""),
                    " ".join((row.get("classification") or {}).get("evidence") or []),
                    asset_group_label(asset_group(row)),
                ]
            )
        ),
        "issues": normalize_text(" ".join(row.get("issue_codes") or [])),
    }
    weights = {
        "dataset_id": 30,
        "title": 12,
        "keywords": 8,
        "category": 6,
        "publisher": 4,
        "description": 3,
        "classification": 2,
        "issues": 1,
    }
    score = 0
    matched_terms: Set[str] = set()
    field_matches: Set[str] = set()
    for term in query_terms:
        term_pattern = r"\b%s\b" % re.escape(term)
        for field, value in fields.items():
            if re.search(term_pattern, value):
                score += weights[field]
                matched_terms.add(term)
                field_matches.add(field)
    for term in direct_terms:
        if re.search(r"\b%s\b" % re.escape(term), fields["title"]):
            score += 18
            if term in HIGH_INTENT_TERMS:
                score += 30
        if re.search(r"\b%s\b" % re.escape(term), fields["keywords"]):
            score += 8
    row_topic_matches = []
    for topic in topic_matches:
        topic_text = normalize_text(" ".join(CITY_TOPIC_HINTS[topic]))
        row_text = " ".join(fields.values())
        if any(re.search(r"\b%s\b" % re.escape(term), row_text) for term in tokenize(topic_text)):
            score += 12
            row_topic_matches.append(topic)
            field_matches.add("topic")
    if asset_group(row) == "active_dataset":
        score += 8
    elif asset_group(row) == "needs_manual_review":
        score += 3
    if row["label"] == "good":
        score += 3
    return DiscoveryMatch(
        row=row,
        score=score,
        matched_terms=sorted(matched_terms),
        matched_topics=row_topic_matches,
        field_matches=sorted(field_matches),
    )


def expand_query_terms(base_terms: Set[str]) -> Set[str]:
    terms = set(base_terms)
    query_text = " ".join(base_terms)
    for topic, hints in CITY_TOPIC_HINTS.items():
        hint_terms = set()
        for hint in hints:
            hint_terms.update(tokenize(hint))
        if base_terms.intersection(hint_terms) or any(hint in query_text for hint in hints if " " in hint):
            terms.update(hint_terms)
            terms.add(topic.replace("_", " "))
    return terms


def detect_topics(question: str) -> List[str]:
    normalized = normalize_text(question)
    terms = tokenize(normalized)
    matches = []
    for topic, hints in CITY_TOPIC_HINTS.items():
        hint_terms = set()
        phrase_match = False
        for hint in hints:
            normalized_hint = normalize_text(hint)
            if " " in normalized_hint and normalized_hint in normalized:
                phrase_match = True
            hint_terms.update(tokenize(normalized_hint))
        if phrase_match or terms.intersection(hint_terms):
            matches.append(topic)
    return matches


def build_match_explanation(row: Dict[str, Any], matched_terms: Sequence[str], matched_topics: Sequence[str], field_matches: Sequence[str]) -> str:
    pieces = []
    if matched_terms:
        pieces.append("matched terms: %s" % ", ".join(matched_terms[:8]))
    if matched_topics:
        pieces.append("matched civic topics: %s" % ", ".join(matched_topics[:4]))
    if field_matches:
        pieces.append("matched fields: %s" % ", ".join(field_matches[:6]))
    pieces.append("classification: %s" % asset_group_label(asset_group(row)))
    return "; ".join(pieces)


def tokenize(value: str) -> Set[str]:
    return {term for term in re.findall(r"[a-z0-9]+", normalize_text(value)) if len(term) > 1 and term not in STOPWORDS}


def normalize_text(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def group_rank(group: str) -> int:
    return {
        "active_dataset": 0,
        "needs_manual_review": 1,
        "archive_snapshot": 2,
        "event_specific": 3,
        "measure": 4,
        "story_reference": 5,
    }.get(group, 9)
