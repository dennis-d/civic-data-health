from __future__ import annotations

import unittest

from civic_data_health.public_catalog import search_government_resources, search_public_catalogs


def catalog_loader(source_key: str):
    return {
        "dataset": [
            {
                "identifier": "https://data.%s.gov/api/views/abcd-1234" % ("texas" if source_key == "texas" else "austintexas"),
                "title": "Business Permits",
                "description": "License and permit records for businesses.",
                "keyword": ["permit", "license", "business"],
                "publisher": {"name": "Example Agency"},
                "landingPage": "https://example.test/d/abcd-1234",
                "modified": "2026-05-01",
            },
            {
                "identifier": "https://data.%s.gov/api/views/wxyz-9876" % ("texas" if source_key == "texas" else "austintexas"),
                "title": "Unrelated Dataset",
                "description": "Parks and recreation records.",
                "keyword": ["parks"],
                "publisher": {"name": "Example Agency"},
                "landingPage": "https://example.test/d/wxyz-9876",
            },
        ]
    }


class PublicCatalogTests(unittest.TestCase):
    def test_search_public_catalogs_finds_state_dataset(self):
        result = search_public_catalogs("business permit license", jurisdiction="texas", catalog_loader=catalog_loader)

        self.assertEqual(result[0]["jurisdiction"], "State of Texas")
        self.assertEqual(result[0]["dataset_id"], "abcd-1234")
        self.assertTrue(result[0]["queryable"])
        self.assertEqual(result[0]["socrata_domain"], "data.texas.gov")

    def test_search_government_resources_finds_permit_starters(self):
        result = search_government_resources("How do I start a permit process for a business?", jurisdiction="all")

        titles = {item["title"] for item in result}
        self.assertIn("Business Permit Office", titles)
        self.assertIn("Austin Development Services permits", titles)


if __name__ == "__main__":
    unittest.main()
