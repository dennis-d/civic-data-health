from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from civic_data_health.storage import cached_view_metadata, init_db, upsert_view_metadata


class StorageMigrationTests(unittest.TestCase):
    def test_demo_database_schema_is_migrated(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "civic.sqlite"
            conn = sqlite3.connect(str(db_path))
            conn.executescript(
                """
                CREATE TABLE runs (
                    id integer primary key,
                    fetched_at text,
                    source_url text,
                    catalog_sha256 text,
                    compressed_bytes integer,
                    uncompressed_bytes integer,
                    dataset_count integer
                );
                CREATE TABLE dataset_health (
                    run_id integer,
                    dataset_id text,
                    score integer,
                    label text,
                    issues_json text,
                    remediation_json text
                );
                """
            )
            conn.close()

            init_db(db_path)

            migrated = sqlite3.connect(str(db_path))
            run_columns = {row[1] for row in migrated.execute("PRAGMA table_info(runs)").fetchall()}
            dataset_columns = {row[1] for row in migrated.execute("PRAGMA table_info(datasets)").fetchall()}
            health_columns = {row[1] for row in migrated.execute("PRAGMA table_info(dataset_health)").fetchall()}
            self.assertIn("limit_applied", run_columns)
            self.assertIn("tool_version", run_columns)
            self.assertIn("asset_type", dataset_columns)
            self.assertIn("issue_codes_json", health_columns)
            self.assertIn("data_dictionary_quality_json", health_columns)
            self.assertIn("classification_json", health_columns)
            migrated.close()

    def test_view_metadata_cache_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "civic.sqlite"
            init_db(db_path)
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            raw = {"name": "Example", "columns": [{"fieldName": "issue_date"}]}
            upsert_view_metadata(conn, dataset_id="abcd-1234", source_modified="2026-01-01", raw=raw)
            self.assertEqual(cached_view_metadata(conn, "abcd-1234", "2026-01-01"), raw)
            conn.close()


if __name__ == "__main__":
    unittest.main()
