from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .models import NormalizedDataset

MODEL_NAME = "category_tfidf_centroid_v1"
MIN_CONFIDENCE = 0.35
EXCLUDED_TRAINING_CATEGORIES = {"see category tile"}
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "city",
    "data",
    "dataset",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


@dataclass
class CategoryModel:
    categories: List[str]
    centroids: Dict[str, Dict[str, float]]
    category_counts: Dict[str, int]
    idf: Dict[str, float]
    training_examples: int


def build_category_suggestions(datasets: Sequence[NormalizedDataset], *, min_confidence: float = MIN_CONFIDENCE) -> Dict[str, Dict[str, Any]]:
    model = train_category_model(datasets)
    return {
        dataset.dataset_id: suggest_category(dataset, model, min_confidence=min_confidence)
        for dataset in datasets
    }


def category_suggestion_summary(suggestions: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    counts = Counter(str(suggestion.get("status") or "unknown") for suggestion in suggestions.values())
    return {
        "model": MODEL_NAME,
        "total": len(suggestions),
        "suggested": counts.get("suggested", 0),
        "low_confidence": counts.get("low_confidence", 0),
        "not_needed": counts.get("not_needed", 0),
        "unavailable": counts.get("unavailable", 0),
    }


def train_category_model(datasets: Sequence[NormalizedDataset]) -> CategoryModel:
    training_docs: List[Tuple[str, Counter[str]]] = []
    document_frequency: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()

    for dataset in datasets:
        category = normalize_category(dataset.category)
        if not category or category.casefold() in EXCLUDED_TRAINING_CATEGORIES:
            continue
        tokens = weighted_tokens(dataset)
        if not tokens:
            continue
        training_docs.append((category, tokens))
        category_counts[category] += 1
        document_frequency.update(tokens.keys())

    if not training_docs:
        return CategoryModel([], {}, {}, {}, 0)

    total_docs = len(training_docs)
    idf = {
        token: math.log((1 + total_docs) / (1 + frequency)) + 1.0
        for token, frequency in document_frequency.items()
    }
    category_vectors: Dict[str, List[Dict[str, float]]] = defaultdict(list)
    for category, tokens in training_docs:
        vector = vectorize(tokens, idf)
        if vector:
            category_vectors[category].append(vector)

    centroids = {
        category: normalize_vector(average_vectors(vectors))
        for category, vectors in category_vectors.items()
        if vectors
    }
    return CategoryModel(
        categories=sorted(centroids),
        centroids=centroids,
        category_counts=dict(category_counts),
        idf=idf,
        training_examples=total_docs,
    )


def suggest_category(dataset: NormalizedDataset, model: CategoryModel, *, min_confidence: float = MIN_CONFIDENCE) -> Dict[str, Any]:
    if dataset.category:
        return {
            "status": "not_needed",
            "catalog_category": dataset.category,
            "model": MODEL_NAME,
            "reason": "Catalog category is already present.",
        }
    if not model.categories:
        return {
            "status": "unavailable",
            "model": MODEL_NAME,
            "reason": "No labeled catalog categories were available for training.",
        }

    tokens = weighted_tokens(dataset)
    vector = vectorize(tokens, model.idf)
    if not vector:
        return {
            "status": "unavailable",
            "model": MODEL_NAME,
            "training_examples": model.training_examples,
            "reason": "No usable title, tags, publisher, description, or asset type tokens were available.",
        }

    scored = sorted(
        ((category, cosine(vector, centroid)) for category, centroid in model.centroids.items()),
        key=lambda item: item[1],
        reverse=True,
    )
    positive = [(category, score) for category, score in scored if score > 0]
    if not positive:
        return {
            "status": "unavailable",
            "model": MODEL_NAME,
            "training_examples": model.training_examples,
            "reason": "No category centroid shared usable terms with this record.",
        }

    probability_base = positive[:5]
    probabilities = softmax(probability_base)
    best_category, best_score = positive[0]
    confidence = probabilities[best_category]
    status = "suggested" if confidence >= min_confidence else "low_confidence"
    return {
        "status": status,
        "suggested_category": best_category,
        "confidence": round(confidence, 3),
        "score": round(best_score, 3),
        "evidence": evidence_tokens(vector, model.centroids[best_category]),
        "alternatives": [
            {
                "category": category,
                "confidence": round(probabilities[category], 3),
                "score": round(score, 3),
            }
            for category, score in positive[:3]
        ],
        "model": MODEL_NAME,
        "training_examples": model.training_examples,
        "category_examples": model.category_counts.get(best_category, 0),
        "reason": "Catalog category is missing; suggestion is inferred from title, tags, publisher, description, and Socrata asset type.",
    }


def rows_with_category_suggestions(rows: Iterable[Dict[str, Any]], *, limit: int = 25) -> List[Dict[str, Any]]:
    candidates = [
        row for row in rows
        if not row.get("category") and (row.get("category_suggestion") or {}).get("suggested_category")
    ]
    candidates.sort(
        key=lambda row: (
            0 if (row.get("category_suggestion") or {}).get("status") == "suggested" else 1,
            -float((row.get("category_suggestion") or {}).get("confidence") or 0),
            row.get("title", "").casefold(),
        )
    )
    return candidates[: max(1, min(int(limit or 25), 100))]


def weighted_tokens(dataset: NormalizedDataset) -> Counter[str]:
    tokens: Counter[str] = Counter()
    add_tokens(tokens, dataset.title, weight=3)
    add_tokens(tokens, dataset.description, weight=1)
    add_tokens(tokens, dataset.publisher, weight=1)
    add_tokens(tokens, dataset.contact, weight=1)
    add_tokens(tokens, dataset.asset_type, weight=1)
    for keyword in dataset.keywords:
        add_tokens(tokens, keyword, weight=4)
    return tokens


def add_tokens(tokens: Counter[str], text: str, *, weight: int) -> None:
    for token in tokenize(text):
        tokens[token] += weight


def tokenize(text: str) -> List[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", (text or "").casefold())
        if len(token) > 1 and token not in STOPWORDS
    ]


def normalize_category(category: str) -> str:
    return " ".join((category or "").split())


def vectorize(tokens: Counter[str], idf: Mapping[str, float]) -> Dict[str, float]:
    vector = {
        token: float(weight) * float(idf.get(token, 1.0))
        for token, weight in tokens.items()
        if token in idf
    }
    return normalize_vector(vector)


def normalize_vector(vector: Mapping[str, float]) -> Dict[str, float]:
    norm = math.sqrt(sum(value * value for value in vector.values()))
    if not norm:
        return {}
    return {token: value / norm for token, value in vector.items()}


def average_vectors(vectors: Sequence[Mapping[str, float]]) -> Dict[str, float]:
    summed: Dict[str, float] = defaultdict(float)
    for vector in vectors:
        for token, value in vector.items():
            summed[token] += value
    count = float(len(vectors) or 1)
    return {token: value / count for token, value in summed.items()}


def cosine(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(token, 0.0) for token, value in left.items())


def softmax(scored: Sequence[Tuple[str, float]]) -> Dict[str, float]:
    scale = 10.0
    exps = {category: math.exp(score * scale) for category, score in scored}
    total = sum(exps.values()) or 1.0
    return {category: value / total for category, value in exps.items()}


def evidence_tokens(query: Mapping[str, float], centroid: Mapping[str, float], *, limit: int = 6) -> List[str]:
    scored = [
        (token, query_weight * centroid.get(token, 0.0))
        for token, query_weight in query.items()
        if centroid.get(token, 0.0) > 0
    ]
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [token for token, _score in scored[:limit]]
