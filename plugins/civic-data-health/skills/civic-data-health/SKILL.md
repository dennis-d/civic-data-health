---
name: civic-data-health
description: Use the hosted Civic Data Health MCP primarily for Texas/Austin public-data search, official service or permit starting links, and bounded public rows; use Austin dataset-quality tools as secondary context.
---

# Civic Data Health

Use this skill when the user asks to find Texas or Austin public datasets, locate official permit/license/service starting points, inspect bounded public rows, or add Austin dataset-quality caveats after relevant data is found.

## Endpoint

- Public report: `https://civic.pagonya.co/`
- MCP endpoint: `https://civic.pagonya.co/mcp`
- Health check: `https://civic.pagonya.co/mcp/health`

If the MCP server is not configured in Codex, add it with:

```bash
codex mcp add civic-data-health --url https://civic.pagonya.co/mcp
```

For direct HTTP smoke tests against `/mcp`, include:

```bash
-H 'accept: application/json, text/event-stream'
```

## Tool Use

Prefer MCP tools over scraping the static JSON when tools are available.

Primary search and service tools:

- `ask_texas_government_question`: broad Texas/Austin government, permit, service, governance, and dataset-backed questions.
- `ask_civic_data_question`: general Texas/Austin civic search with official links and public rows.
- `search_public_data_catalogs`: public catalog search across State of Texas and Austin.
- `find_government_service_resources`: official starting links for permits, licenses, business, and government services.
- `find_government_service_guides`: curated workflow guides for Texas business setup, Austin permits, food businesses, property/zoning, and 3-1-1/code complaints.
- `query_public_dataset_rows`: bounded public rows after search identifies a known Texas or Austin Socrata dataset.
- `ask_austin_data_question`: Austin-specific data search with schema checks and bounded rows.
- `ask_city_data_question`: Austin-only plain-English dataset discovery.
- `find_city_datasets_for_question`: ranked Austin dataset candidates for a topic or question.
- `search_city_knowledge`: Austin catalog plus schema-column search.
- `search_dataset_columns`: Austin schema search for fields like permit type, status, date, amount, or council district.
- `find_answerable_datasets`: Austin answerability search based on schema capabilities.
- `get_dataset_capabilities`: field capability summary after search identifies a dataset.
- `fetch_city_knowledge`: full Austin dataset package after search identifies a dataset.
- `get_dataset_schema`: Socrata columns, types, and field names for a known dataset id.
- `get_sample_rows`: up to 20 live sample rows for a known dataset id.
- `query_dataset_count`: safe read-only `count(*)` query, optionally bounded by a validated date column.

Secondary dataset-quality tools:

- `get_report_summary`: current run summary, classification groups, top active risks.
- `list_high_risk_datasets`: active datasets with hard or severe risk.
- `get_top_actionable_fixes`: steward cleanup queue; defaults to active datasets.
- `list_classification_review_candidates`: dated records that need human classification review.
- `get_classification_methodology`: groups, evidence codes, and hard override rules.
- `search_datasets`: broad report search by title, id, issue, asset, or classification.
- `get_dataset_health`: full row for a known Socrata dataset id.
- `explain_dataset_issue`: plain-English issue explanation for outreach or review.
- `draft_department_email`: draft-only outreach text; never sends email.
- `search` and `fetch`: citation-friendly tools for ChatGPT-style retrieval.

## Operating Notes

- Treat `active_dataset` as the operational cleanup queue.
- Do not call `archive_snapshot`, `event_specific`, `measure`, or `story_reference` records high-risk active datasets.
- Use `classification.evidence` when explaining why a record moved out of the active queue.
- For general public questions, call `ask_civic_data_question` or `ask_texas_government_question` before narrower search tools.
- For count questions, let `ask_city_data_question` try the safe row-level count path before falling back to dataset recommendations.
- Use dataset-quality tools after search when the user asks for caveats, metadata quality, cleanup, or trustworthiness.
- Do not ask for or construct arbitrary SoQL. Use `query_dataset_count`, `get_sample_rows`, or schema-backed tool arguments.
- For ambiguous year-specific records, use the `needs_manual_review` group and suggest a `classification_overrides.json` entry after human review.
