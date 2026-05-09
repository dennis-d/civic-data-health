from __future__ import annotations

import unittest

from civic_data_health.discovery import answer_city_data_question, find_city_datasets


def row(**overrides):
    values = {
        "dataset_id": "abcd-1234",
        "title": "Example Dataset",
        "description": "General city dataset.",
        "keywords": [],
        "category": "Operations",
        "publisher": "data.austintexas.gov",
        "contact": "owner@example.com",
        "landing_url": "https://data.austintexas.gov/d/abcd-1234",
        "machine_url": "https://example.com/data.csv",
        "score": 90,
        "label": "good",
        "issue_codes": [],
        "modified": "2026-05-01",
        "classification": {"group": "active_dataset", "confidence": "high", "evidence": ["machine_readable_distribution"]},
    }
    values.update(overrides)
    return values


class DiscoveryTests(unittest.TestCase):
    def test_plain_english_police_question_finds_apd_dataset(self):
        matches = find_city_datasets(
            [
                row(dataset_id="22de-7rzg", title="APD Computer Aided Dispatch Incidents", category="Public Safety"),
                row(dataset_id="bike-0001", title="Bicycle Facilities", category="Transportation and Mobility"),
            ],
            "Where can I find police calls and incidents?",
        )
        self.assertEqual(matches[0].row["dataset_id"], "22de-7rzg")
        self.assertIn("public_safety", matches[0].matched_topics)

    def test_answer_includes_caveats_for_non_active_matches(self):
        answer = answer_city_data_question(
            [
                row(
                    dataset_id="story-0001",
                    title="Flood Story Map",
                    category="Environment",
                    label="needs_review",
                    classification={"group": "story_reference", "confidence": "high", "evidence": ["socrata_story_asset"]},
                    machine_url="",
                )
            ],
            "flood maps",
        )
        self.assertEqual(answer["datasets"][0]["asset_group"], "story_reference")
        self.assertTrue(answer["datasets"][0]["caveats"])


if __name__ == "__main__":
    unittest.main()
