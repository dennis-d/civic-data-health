from __future__ import annotations

import unittest

from civic_data_health.reports import PUBLIC_MCP_URL, render_help_page


class ReportRenderTests(unittest.TestCase):
    def test_help_page_contains_chatgpt_demo_connection_details(self):
        html = render_help_page({"run_id": 7, "fetched_at": "2026-05-09T11:09:51Z"})

        self.assertIn("Connect Civic Data Health to ChatGPT", html)
        self.assertIn(PUBLIC_MCP_URL, html)
        self.assertIn("Settings -&gt; Apps &amp; Connectors", html)
        self.assertIn("accept: application/json, text/event-stream", html)
        self.assertIn("https://developers.openai.com/apps-sdk/deploy/connect-chatgpt", html)
        self.assertIn("Pagonya LLC", html)


if __name__ == "__main__":
    unittest.main()
