from __future__ import annotations

import unittest

from civic_data_health.analysis import asset_group, draft_department_email, summarize_asset_groups, top_actionable_fixes


def row(**overrides):
    values = {
        "dataset_id": "abcd-1234",
        "title": "Example Dataset",
        "score": 70,
        "label": "needs_review",
        "asset_type": "",
        "publisher": "Austin Test Department",
        "contact": "owner@example.com",
        "landing_url": "https://data.austintexas.gov/d/abcd-1234",
        "issue_codes": ["description_missing", "license_missing"],
        "remediation": ["Write a better description.", "Add a license."],
    }
    values.update(overrides)
    return values


class AnalysisTests(unittest.TestCase):
    def test_asset_group_splits_active_measure_and_story(self):
        self.assertEqual(asset_group(row(asset_type="")), "active_dataset")
        self.assertEqual(asset_group(row(asset_type="measure")), "measure")
        self.assertEqual(asset_group(row(asset_type="story")), "story_reference")
        self.assertEqual(asset_group(row(asset_type="", issue_codes=["point_in_time_or_event_record"])), "story_reference")

    def test_top_actionable_fixes_defaults_to_active_datasets(self):
        fixes = top_actionable_fixes(
            [
                row(dataset_id="active-0001", title="Active", asset_type="", issue_codes=["description_missing"]),
                row(dataset_id="story-0001", title="Story", asset_type="story", issue_codes=["description_missing"]),
            ],
            limit=10,
        )
        self.assertEqual([item["dataset_id"] for item in fixes], ["active-0001"])

    def test_group_summary_counts_labels_and_issues(self):
        summary = summarize_asset_groups(
            [
                row(asset_type="", label="needs_review", issue_codes=["description_missing"]),
                row(asset_type="measure", label="good", score=100, issue_codes=[]),
                row(asset_type="story", label="needs_review", issue_codes=["license_missing"]),
            ]
        )
        self.assertEqual(summary["active_dataset"]["count"], 1)
        self.assertEqual(summary["measure"]["labels"]["good"], 1)
        self.assertEqual(summary["story_reference"]["top_issues"][0]["issue_code"], "license_missing")

    def test_department_email_is_draft_only(self):
        draft = draft_department_email(row(), contact_name="Data Steward", sender_name="Civic Reviewer")
        self.assertIn("Open data metadata cleanup", draft["subject"])
        self.assertIn("Hello Data Steward", draft["body"])
        self.assertIn("independent public metadata review", draft["body"])


if __name__ == "__main__":
    unittest.main()
