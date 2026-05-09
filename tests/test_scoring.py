from __future__ import annotations

import unittest
from datetime import datetime, timezone

from civic_data_health.models import NormalizedDataset
from civic_data_health.scoring import parse_accrual_periodicity_days, score_dataset


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
        "accrual_periodicity": "R/P1M",
        "landing_url": "https://data.austintexas.gov/d/abcd-1234",
        "distribution": [{"downloadURL": "https://example.com/data.csv"}],
        "machine_url": "https://example.com/data.csv",
        "raw": {},
    }
    values.update(overrides)
    return NormalizedDataset(**values)


class ScoringTests(unittest.TestCase):
    def test_missing_modified_reduces_score(self):
        result = score_dataset(dataset(modified=None), now=datetime(2026, 5, 9, tzinfo=timezone.utc))
        self.assertIn("modified_missing", result.issue_codes)
        self.assertLessEqual(result.score, 70)

    def test_known_cadence_stale_gets_full_penalty(self):
        result = score_dataset(dataset(modified="2025-01-01", accrual_periodicity="R/P1M"), now=datetime(2026, 5, 9, tzinfo=timezone.utc))
        self.assertIn("freshness_stale_known_cadence", result.issue_codes)
        self.assertEqual(result.score, 75)

    def test_unknown_cadence_old_gets_low_confidence_penalty(self):
        result = score_dataset(dataset(modified="2025-01-01", accrual_periodicity=""), now=datetime(2026, 5, 9, tzinfo=timezone.utc))
        self.assertIn("freshness_old_unknown_cadence", result.issue_codes)
        self.assertEqual(result.freshness_confidence, "low")
        self.assertEqual(result.score, 92)

    def test_missing_distribution_forces_high_risk(self):
        result = score_dataset(dataset(distribution=[], machine_url=""), now=datetime(2026, 5, 9, tzinfo=timezone.utc))
        self.assertIn("no_distribution", result.issue_codes)
        self.assertEqual(result.label, "high_risk")

    def test_cadence_parser(self):
        self.assertEqual(parse_accrual_periodicity_days("R/P1Y"), 365)
        self.assertEqual(parse_accrual_periodicity_days("R/P1M"), 30)
        self.assertEqual(parse_accrual_periodicity_days("R/P2W"), 14)


if __name__ == "__main__":
    unittest.main()

