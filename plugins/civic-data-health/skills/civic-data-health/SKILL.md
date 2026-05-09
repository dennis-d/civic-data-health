---
name: civic-data-health
description: Use the hosted Civic Data Health MCP for Austin Open Data metadata audits, dataset search, classification review, and cleanup prioritization.
---

# Civic Data Health

Use this skill when the user asks about Austin open data quality, the Civic Data Health report, dataset risk ranking, classification evidence, or cleanup priorities.

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

- `get_report_summary`: current run summary, classification groups, top active risks.
- `list_high_risk_datasets`: active datasets with hard or severe risk.
- `get_top_actionable_fixes`: steward cleanup queue; defaults to active datasets.
- `list_classification_review_candidates`: dated records that need human classification review.
- `get_classification_methodology`: groups, evidence codes, and hard override rules.
- `search_datasets`: broad report search by title, id, issue, asset, or classification.
- `ask_city_data_question`: plain-English city data discovery with ranked datasets and caveats.
- `find_city_datasets_for_question`: ranked dataset candidates for a civic topic or question.
- `get_dataset_health`: full row for a known Socrata dataset id.
- `explain_dataset_issue`: plain-English issue explanation for outreach or review.
- `draft_department_email`: draft-only outreach text; never sends email.
- `search` and `fetch`: citation-friendly tools for ChatGPT-style retrieval.

## Operating Notes

- Treat `active_dataset` as the operational cleanup queue.
- Do not call `archive_snapshot`, `event_specific`, `measure`, or `story_reference` records high-risk active datasets.
- Use `classification.evidence` when explaining why a record moved out of the active queue.
- For general public questions, call `ask_city_data_question` before narrower search tools.
- For ambiguous year-specific records, use the `needs_manual_review` group and suggest a `classification_overrides.json` entry after human review.
