from __future__ import annotations

import unittest

from civic_data_health.normalize import extract_dataset_id, normalize_catalog


class NormalizeTests(unittest.TestCase):
    def test_extracts_4x4_id_from_urls(self):
        self.assertEqual(extract_dataset_id("https://data.austintexas.gov/d/abcd-1234?x=1"), "abcd-1234")
        self.assertEqual(extract_dataset_id("ABCD-1234"), "abcd-1234")

    def test_unrecoverable_identifier_is_skipped(self):
        catalog = {"dataset": [{"title": "No stable id", "identifier": "not-a-socrata-id"}]}
        normalized, skipped, total = normalize_catalog(catalog)
        self.assertEqual(total, 1)
        self.assertEqual(normalized, [])
        self.assertEqual(skipped[0].reason_code, "unstable_identifier")


if __name__ == "__main__":
    unittest.main()

