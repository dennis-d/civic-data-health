from __future__ import annotations

import unittest

from civic_data_health.reports import (
    PRIVACY_URL,
    PUBLIC_MCP_URL,
    SUPPORT_EMAIL,
    SUPPORT_URL,
    find_asset,
    render_detail_page,
    render_help_page,
    render_privacy_page,
    render_submission_page,
    render_support_page,
)


class ReportRenderTests(unittest.TestCase):
    def test_submission_icon_asset_is_available_from_repo_root(self):
        asset = find_asset("texas-civic-data-health-icon.png")

        self.assertIsNotNone(asset)
        self.assertTrue(asset.exists())

    def test_help_page_contains_chatgpt_demo_connection_details(self):
        html = render_help_page({"run_id": 7, "fetched_at": "2026-05-09T11:09:51Z"})

        self.assertIn("Connect Public Texas State and Austin City Search to ChatGPT", html)
        self.assertIn(PUBLIC_MCP_URL, html)
        self.assertIn("Settings -&gt; Apps &amp; Connectors", html)
        self.assertIn("Settings -&gt; Connectors -&gt; Create", html)
        self.assertIn("Search State of Texas and Austin public data", html)
        self.assertIn("Austin dataset-quality checks are secondary context", html)
        self.assertIn("accept: application/json, text/event-stream", html)
        self.assertIn("https://developers.openai.com/apps-sdk/deploy/connect-chatgpt", html)
        self.assertIn("Independently operated", html)
        self.assertIn(PRIVACY_URL, html)
        self.assertIn(SUPPORT_URL, html)

    def test_privacy_page_contains_review_required_disclosures(self):
        html = render_privacy_page({"run_id": 7, "fetched_at": "2026-05-09T11:09:51Z"})

        self.assertIn("Privacy Policy", html)
        self.assertIn("Tool inputs that ChatGPT sends to the MCP server", html)
        self.assertIn("Standard hosting and security logs", html)
        self.assertIn("Do not send Social Security numbers", html)
        self.assertIn("does not sell personal data", html)
        self.assertIn("Disconnect the app in ChatGPT settings", html)
        self.assertIn(SUPPORT_EMAIL, html)

    def test_support_page_contains_public_contact_and_scope(self):
        html = render_support_page({"run_id": 7, "fetched_at": "2026-05-09T11:09:51Z"})

        self.assertIn("Support", html)
        self.assertIn(SUPPORT_EMAIL, html)
        self.assertIn("cannot submit applications", html)
        self.assertIn(PUBLIC_MCP_URL, html)
        self.assertIn(PRIVACY_URL, html)

    def test_submission_page_contains_dashboard_fields(self):
        html = render_submission_page({"run_id": 7, "fetched_at": "2026-05-09T11:09:51Z"})

        self.assertIn("ChatGPT App Submission Checklist", html)
        self.assertIn("Public Texas State and Austin City Search", html)
        self.assertIn("TX and Austin public data", html)
        self.assertIn(PUBLIC_MCP_URL, html)
        self.assertIn(PRIVACY_URL, html)
        self.assertIn(SUPPORT_URL, html)
        self.assertIn("OpenAI organization identity verification", html)

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
