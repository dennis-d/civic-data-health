from __future__ import annotations

import unittest

from civic_data_health.reports import PUBLIC_MCP_URL, render_detail_page, render_help_page


class ReportRenderTests(unittest.TestCase):
    def test_help_page_contains_chatgpt_demo_connection_details(self):
        html = render_help_page({"run_id": 7, "fetched_at": "2026-05-09T11:09:51Z"})

        self.assertIn("Connect Civic Data Health to ChatGPT", html)
        self.assertIn(PUBLIC_MCP_URL, html)
        self.assertIn("Settings -&gt; Apps &amp; Connectors", html)
        self.assertIn("accept: application/json, text/event-stream", html)
        self.assertIn("https://developers.openai.com/apps-sdk/deploy/connect-chatgpt", html)
        self.assertIn("Pagonya LLC", html)

    def test_detail_page_surfaces_tags_when_category_is_missing(self):
        html = render_detail_page(
            {"run_id": 7, "fetched_at": "2026-05-09T11:09:51Z"},
            {
                "dataset_id": "sw7f-2kkd",
                "title": "Texas Counties Cartographic Boundary Map",
                "score": 67,
                "label": "needs_review",
                "classification": {"confidence": "high", "evidence": ["machine_readable_distribution"], "reason": "Dataset."},
                "asset_type": "dataset",
                "modified": "2023-07-17",
                "issue_codes": ["category_missing"],
                "remediation": ["Add missing metadata: category."],
                "publisher": "data.austintexas.gov",
                "contact": "no-reply@example.com",
                "category": "",
                "keywords": ["map", "texas", "county"],
                "category_suggestion": {
                    "status": "suggested",
                    "suggested_category": "Locations and Maps",
                    "confidence": 0.84,
                    "evidence": ["map", "county"],
                },
                "license": "",
                "landing_url": "https://data.austintexas.gov/d/sw7f-2kkd",
                "machine_url": "https://data.austintexas.gov/api/views/sw7f-2kkd/rows.csv?accessType=DOWNLOAD",
            },
        )

        self.assertIn("Category:</strong> Missing (tags available: map, texas, county)", html)
        self.assertIn("Tags:</strong> map, texas, county", html)
        self.assertIn("Suggested category:</strong> Locations and Maps", html)
        self.assertIn("Evidence:</strong> map, county", html)


if __name__ == "__main__":
    unittest.main()
