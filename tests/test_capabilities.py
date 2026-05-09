from __future__ import annotations

import unittest

from civic_data_health.capabilities import find_answerable, get_capabilities_for_row, search_columns


def row(**overrides):
    values = {
        "dataset_id": "3syk-w9eu",
        "title": "Issued Construction Permits",
        "description": "Building permits issued by the City of Austin.",
        "keywords": ["permit", "building"],
        "category": "Building and Development",
        "publisher": "data.austintexas.gov",
        "contact": "owner@example.com",
        "landing_url": "https://data.austintexas.gov/d/3syk-w9eu",
        "machine_url": "https://data.austintexas.gov/api/views/3syk-w9eu/rows.csv?accessType=DOWNLOAD",
        "score": 100,
        "label": "good",
        "issue_codes": [],
        "modified": "2026-05-08",
        "classification": {"group": "active_dataset", "confidence": "high", "evidence": ["machine_readable_distribution"]},
    }
    values.update(overrides)
    return values


PERMIT_SCHEMA = {
    "dataset_id": "3syk-w9eu",
    "row_count": 100,
    "column_count": 5,
    "source_url": "https://data.austintexas.gov/api/views/3syk-w9eu",
    "columns": [
        {"field_name": "issue_date", "name": "Issue Date", "data_type": "calendar_date", "description": "Permit issue date"},
        {"field_name": "permit_type", "name": "Permit Type", "data_type": "text", "description": "Type of permit"},
        {"field_name": "council_district", "name": "Council District", "data_type": "text", "description": "Austin council district"},
        {"field_name": "latitude", "name": "Latitude", "data_type": "number", "description": "Location latitude"},
        {"field_name": "declared_valuation", "name": "Declared Valuation", "data_type": "money", "description": "Permit valuation amount"},
    ],
}


PUBLIC_SAFETY_SCHEMA = {
    "dataset_id": "abcd-1234",
    "row_count": 20,
    "column_count": 2,
    "source_url": "https://data.austintexas.gov/api/views/abcd-1234",
    "columns": [
        {"field_name": "incident_type", "name": "Incident Type", "data_type": "text", "description": "Incident category"},
        {"field_name": "reported_date", "name": "Reported Date", "data_type": "calendar_date", "description": "Reported date"},
    ],
}


def schema_loader(_conn, loaded_row):
    if loaded_row["dataset_id"] == "3syk-w9eu":
        return PERMIT_SCHEMA
    return PUBLIC_SAFETY_SCHEMA


class CapabilityTests(unittest.TestCase):
    def test_get_capabilities_classifies_schema_roles(self):
        capabilities = get_capabilities_for_row(None, row(), schema_loader=schema_loader)

        self.assertTrue(capabilities["has_date_column"])
        self.assertTrue(capabilities["has_geo_column"])
        self.assertTrue(capabilities["has_numeric_column"])
        self.assertTrue(capabilities["has_categorical_column"])
        self.assertEqual(capabilities["row_count"], 100)

    def test_search_columns_matches_field_semantics(self):
        result = search_columns(
            None,
            [
                row(),
                row(
                    dataset_id="abcd-1234",
                    title="Public Safety Incidents",
                    category="Public Safety",
                    keywords=["incident"],
                ),
            ],
            "council district permit",
            schema_loader=schema_loader,
        )

        self.assertEqual(result["matches"][0]["dataset_id"], "3syk-w9eu")
        self.assertEqual(result["matches"][0]["column"]["field_name"], "council_district")
        self.assertIn("geography", result["matches"][0]["column_roles"])

    def test_find_answerable_requires_date_column_for_year_question(self):
        result = find_answerable(
            None,
            [row()],
            "How many building permits were issued in 2025?",
            schema_loader=schema_loader,
        )

        self.assertTrue(result["requires"]["count"])
        self.assertTrue(result["requires"]["date_filter"])
        self.assertTrue(result["datasets"][0]["answerable"])
        self.assertEqual(result["datasets"][0]["date_column"], "issue_date")
        self.assertIn("query_dataset_count", result["datasets"][0]["recommended_tools"])


if __name__ == "__main__":
    unittest.main()
