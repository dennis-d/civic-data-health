from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from civic_data_health.storage import init_db


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
            health_columns = {row[1] for row in migrated.execute("PRAGMA table_info(dataset_health)").fetchall()}
            self.assertIn("limit_applied", run_columns)
            self.assertIn("tool_version", run_columns)
            self.assertIn("issue_codes_json", health_columns)
            self.assertIn("data_dictionary_quality_json", health_columns)
            migrated.close()


if __name__ == "__main__":
    unittest.main()

