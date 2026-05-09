from __future__ import annotations

import unittest

from civic_data_health.category_suggestions import build_category_suggestions, rows_with_category_suggestions
from civic_data_health.models import NormalizedDataset


def dataset(dataset_id: str, title: str, *, category: str = "", keywords=None, description: str = "", publisher: str = "Austin") -> NormalizedDataset:
    return NormalizedDataset(
        dataset_id=dataset_id,
        title=title,
        description=description,
        modified="2026-01-01",
        publisher=publisher,
        contact="owner@example.com",
        keywords=list(keywords or []),
        license="https://example.com/license",
        category=category,
        accrual_periodicity="",
        landing_url="https://data.austintexas.gov/d/%s" % dataset_id,
        distribution=[{"downloadURL": "https://example.com/%s.csv" % dataset_id}],
        machine_url="https://example.com/%s.csv" % dataset_id,
        raw={},
    )


class CategorySuggestionTests(unittest.TestCase):
    def test_suggests_missing_category_from_tags_and_title(self):
        datasets = [
            dataset("map1-0001", "Creeks Map", category="Locations and Maps", keywords=["map", "creeks", "geography"]),
            dataset("map2-0002", "Zoning Map", category="Locations and Maps", keywords=["map", "zoning", "geography"]),
            dataset("safe-0003", "Police Calls", category="Public Safety", keywords=["police", "calls", "incident"]),
            dataset("safe-0004", "Fire Incidents", category="Public Safety", keywords=["fire", "incident", "safety"]),
            dataset("miss-0005", "County Boundary Map", keywords=["county", "map", "geography"]),
        ]

        suggestions = build_category_suggestions(datasets)
        suggestion = suggestions["miss-0005"]

        self.assertEqual(suggestion["suggested_category"], "Locations and Maps")
        self.assertIn(suggestion["status"], {"suggested", "low_confidence"})
        self.assertIn("map", suggestion["evidence"])

    def test_rows_with_category_suggestions_filters_present_categories(self):
        rows = [
            {"dataset_id": "has-0001", "title": "Has Category", "category": "Public Safety", "category_suggestion": {"status": "not_needed"}},
            {
                "dataset_id": "miss-0002",
                "title": "Missing",
                "category": "",
                "category_suggestion": {"status": "suggested", "suggested_category": "Locations and Maps", "confidence": 0.8},
            },
        ]

        self.assertEqual([row["dataset_id"] for row in rows_with_category_suggestions(rows)], ["miss-0002"])


if __name__ == "__main__":
    unittest.main()
