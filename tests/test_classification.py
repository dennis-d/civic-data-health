from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from civic_data_health.classification import classify_dataset, load_classification_overrides
from civic_data_health.models import NormalizedDataset


def dataset(**overrides):
    values = {
        "dataset_id": "abcd-1234",
        "title": "Healthy Dataset",
        "description": "This dataset contains enough clear metadata to explain coverage, purpose, update behavior, and use.",
        "modified": "2026-05-01T00:00:00Z",
        "publisher": "City Department",
        "contact": "owner@example.com",
        "keywords": ["city"],
        "license": "https://example.com/license",
        "category": "Operations",
        "accrual_periodicity": "",
        "landing_url": "https://data.austintexas.gov/d/abcd-1234",
        "distribution": [{"downloadURL": "https://example.com/data.csv"}],
        "machine_url": "https://example.com/data.csv",
        "raw": {},
        "asset_type": "",
    }
    values.update(overrides)
    return NormalizedDataset(**values)


class ClassificationTests(unittest.TestCase):
    def test_classifies_bounded_year_data_as_archive_snapshot(self):
        result = classify_dataset(dataset(title="HOT Data 2022-2024"))
        self.assertEqual(result.group, "archive_snapshot")
        self.assertIn("bounded_year_range", result.evidence)

    def test_classifies_month_snapshot_as_archive_snapshot(self):
        result = classify_dataset(dataset(title="CapMetro GTFS - January 2018 (Apr-Jun)"))
        self.assertEqual(result.group, "archive_snapshot")
        self.assertIn("month_quarter_snapshot", result.evidence)

    def test_classifies_event_keyword_as_event_specific(self):
        result = classify_dataset(dataset(title="2013 Halloween Flood"))
        self.assertEqual(result.group, "event_specific")
        self.assertIn("event_keyword", result.evidence)

    def test_marks_ambiguous_dated_record_for_manual_review(self):
        result = classify_dataset(dataset(title="Program Inventory 2024"))
        self.assertEqual(result.group, "needs_manual_review")
        self.assertIn("year_without_cadence", result.evidence)

    def test_manual_override_wins_and_records_evidence(self):
        result = classify_dataset(
            dataset(dataset_id="abcd-1234", title="Program Inventory 2024"),
            {"abcd-1234": {"group": "active_dataset", "reason": "Reviewed with owner.", "evidence": ["owner_review"]}},
        )
        self.assertEqual(result.group, "active_dataset")
        self.assertTrue(result.override_applied)
        self.assertIn("manual_override", result.evidence)
        self.assertIn("owner_review", result.evidence)

    def test_loads_classification_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "classification_overrides.json"
            path.write_text(
                '{"overrides":{"abcd-1234":{"group":"archive_snapshot","reason":"Owner confirmed archive."}}}',
                encoding="utf-8",
            )
            overrides = load_classification_overrides(path)
            self.assertEqual(overrides["abcd-1234"]["group"], "archive_snapshot")


if __name__ == "__main__":
    unittest.main()
