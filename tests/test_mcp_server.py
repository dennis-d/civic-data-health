from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from civic_data_health.mcp_server import create_mcp
from civic_data_health.models import HealthResult, NormalizedDataset
from civic_data_health.storage import connect, insert_datasets, insert_health, insert_run, init_db


def build_test_db(db_path: Path) -> None:
    init_db(db_path)
    with connect(db_path) as conn:
        run_id = insert_run(
            conn,
            fetched_at="2026-05-10T00:00:00Z",
            source_url="https://data.austintexas.gov/data.json",
            raw_path=db_path.parent / "data.json",
            manifest_path=db_path.parent / "manifest.json",
            raw_bytes=100,
            catalog_sha256="abc123",
            total_records=1,
            normalized_count=1,
            skipped_count=0,
            errored_count=0,
            limit_applied=None,
        )
        insert_datasets(
            conn,
            run_id,
            [
                NormalizedDataset(
                    dataset_id="abcd-1234",
                    title="Example Building Permits",
                    description="Building permit records for Austin.",
                    modified="2026-05-01",
                    publisher="data.austintexas.gov",
                    contact="owner@example.com",
                    keywords=["building", "permits"],
                    license="Public Domain",
                    category="Development",
                    accrual_periodicity="R/P1D",
                    landing_url="https://data.austintexas.gov/d/abcd-1234",
                    distribution=[],
                    machine_url="https://data.austintexas.gov/api/views/abcd-1234/rows.csv?accessType=DOWNLOAD",
                    raw={},
                    asset_type="dataset",
                )
            ],
        )
        insert_health(
            conn,
            run_id,
            [
                HealthResult(
                    dataset_id="abcd-1234",
                    score=87,
                    label="needs_review",
                    issue_codes=["category_missing"],
                    remediation=["Add missing metadata: category."],
                    freshness_confidence="high",
                    data_dictionary_quality={},
                    classification={"group": "active_dataset", "confidence": "high", "evidence": ["machine_readable_distribution"]},
                    category_suggestion={"suggested_category": "Development", "confidence": 0.82},
                )
            ],
        )


class MCPServerTests(unittest.TestCase):
    def test_search_and_fetch_advertise_compatibility_output_schemas(self):
        with tempfile.TemporaryDirectory() as tmp:
            mcp = create_mcp(Path(tmp) / "civic.sqlite", "127.0.0.1", 0)
            tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}

            search_schema = tools["search"].outputSchema or {}
            fetch_schema = tools["fetch"].outputSchema or {}

            self.assertIn("results", search_schema["properties"])
            self.assertNotIn("result", search_schema["properties"])
            self.assertEqual({"id", "title", "text", "url", "metadata"}, set(fetch_schema["properties"]))
            self.assertNotIn("result", fetch_schema["properties"])

    def test_search_and_fetch_return_structured_content_and_json_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "civic.sqlite"
            build_test_db(db_path)
            mcp = create_mcp(db_path, "127.0.0.1", 0)

            search_content, search_structured = asyncio.run(mcp.call_tool("search", {"query": "building permits"}))
            self.assertEqual(search_structured["results"][0]["id"], "abcd-1234")
            self.assertEqual(json.loads(search_content[0].text), search_structured)

            fetch_content, fetch_structured = asyncio.run(mcp.call_tool("fetch", {"id": "abcd-1234"}))
            self.assertEqual(fetch_structured["id"], "abcd-1234")
            self.assertEqual(fetch_structured["metadata"]["label"], "needs_review")
            self.assertEqual(json.loads(fetch_content[0].text), fetch_structured)


if __name__ == "__main__":
    unittest.main()
