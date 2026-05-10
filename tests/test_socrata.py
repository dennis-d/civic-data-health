from __future__ import annotations

import unittest

from civic_data_health.socrata import simplify_schema, validate_dataset_id, validate_field_name, validate_socrata_domain


class SocrataTests(unittest.TestCase):
    def test_validate_dataset_id(self):
        self.assertEqual(validate_dataset_id("3SYK-W9EU"), "3syk-w9eu")
        with self.assertRaises(ValueError):
            validate_dataset_id("not-safe")

    def test_validate_field_name(self):
        self.assertEqual(validate_field_name("issue_date"), "issue_date")
        with self.assertRaises(ValueError):
            validate_field_name("issue_date;drop")

    def test_validate_socrata_domain(self):
        self.assertEqual(validate_socrata_domain("data.texas.gov"), "data.texas.gov")
        with self.assertRaises(ValueError):
            validate_socrata_domain("example.com")

    def test_simplify_schema_keeps_queryable_columns(self):
        schema = simplify_schema(
            "3syk-w9eu",
            {
                "name": "Issued Construction Permits",
                "assetType": "dataset",
                "rowCount": 10,
                "columns": [
                    {"fieldName": "issue_date", "name": "Issue Date", "dataTypeName": "calendar_date", "description": "Issued"},
                    {"fieldName": ":id", "name": "Internal id", "dataTypeName": "meta_data"},
                ],
            },
        )
        self.assertEqual(schema["column_count"], 1)
        self.assertEqual(schema["columns"][0]["field_name"], "issue_date")


if __name__ == "__main__":
    unittest.main()
