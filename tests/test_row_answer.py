from __future__ import annotations

import unittest
from datetime import datetime, timezone

from civic_data_health.row_answer import (
    DateRange,
    answer_row_level_question,
    build_date_where,
    choose_date_column,
    parse_date_range,
)


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


SCHEMA = {
    "dataset_id": "3syk-w9eu",
    "columns": [
        {"field_name": "issue_date", "name": "Issue Date", "data_type": "calendar_date", "description": "Permit issue date"},
        {"field_name": "permit_number", "name": "Permit Number", "data_type": "text", "description": ""},
    ],
}


class RowAnswerTests(unittest.TestCase):
    def test_parse_year_range(self):
        result = parse_date_range("How many permits were issued in 2025?", now=datetime(2026, 5, 9, tzinfo=timezone.utc))
        self.assertEqual(result, DateRange("2025", "2025-01-01T00:00:00", "2026-01-01T00:00:00"))

    def test_parse_last_month_range(self):
        result = parse_date_range("How many permits were issued last month?", now=datetime(2026, 5, 9, tzinfo=timezone.utc))
        self.assertEqual(result, DateRange("last month", "2026-04-01T00:00:00", "2026-05-01T00:00:00"))

    def test_choose_date_column_prefers_issue_date_for_issued_question(self):
        self.assertEqual(choose_date_column(SCHEMA, "How many permits were issued in 2025?"), "issue_date")

    def test_build_date_where_rejects_unsafe_literals(self):
        with self.assertRaises(ValueError):
            build_date_where("issue_date", DateRange("bad", "2025-01-01'; drop table x; --", "2026-01-01T00:00:00"))

    def test_answer_row_level_count_question(self):
        answer = answer_row_level_question(
            None,
            [row()],
            "How many building permits were issued in 2025?",
            now=datetime(2026, 5, 9, tzinfo=timezone.utc),
            schema_loader=lambda _conn, _row: SCHEMA,
            count_loader=lambda dataset_id, where: 123 if dataset_id == "3syk-w9eu" and "issue_date" in (where or "") else 0,
        )
        self.assertIsNotNone(answer)
        self.assertTrue(answer["computed"])
        self.assertEqual(answer["result"]["count"], 123)
        self.assertEqual(answer["datasets"][0]["dataset_id"], "3syk-w9eu")
        self.assertEqual(answer["query"]["date_column"], "issue_date")

    def test_non_count_question_is_not_computed(self):
        answer = answer_row_level_question(None, [row()], "Where can I find permit data?", schema_loader=lambda _conn, _row: SCHEMA)
        self.assertIsNone(answer)


if __name__ == "__main__":
    unittest.main()
