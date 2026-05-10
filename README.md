# Civic Data Health

Read-only Texas and Austin public data search with secondary Austin dataset-quality checks.

The primary workflow is helping people search State of Texas and City of Austin public datasets, find official permit/license/service starting points, and fetch bounded public rows from known Socrata datasets. The secondary workflow scores Austin dataset metadata, exports static quality reports, and serves those quality/caveat tools from SQLite.

## Local Run

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
civic-health run
```

Outputs:

- `out/index.html`
- `out/austin_dataset_health.html`
- `out/austin_dataset_health.csv`
- `out/austin_dataset_health.json`
- `out/methodology.html`
- `out/help.html`
- `out/privacy.html`
- `out/support.html`
- `out/submission.html`
- `data/civic_health.sqlite`
- `data/raw/<timestamp>/data.json`
- `data/raw/<timestamp>/manifest.json`

Smoke test with a smaller normalization set:

```bash
civic-health run --limit 5 --force
python -m unittest discover -s tests
```

## MCP

Start the local MCP HTTP endpoint:

```bash
civic-health --db data/civic_health.sqlite mcp --host 127.0.0.1 --port 8787
```

Health check:

```bash
curl http://127.0.0.1:8787/mcp/health
```

List tools:

```bash
curl -sS -X POST http://127.0.0.1:8787/mcp \
  -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  --data '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

Primary search and service tools:

- `ask_texas_government_question`
- `ask_civic_data_question`
- `search_public_data_catalogs`
- `find_government_service_resources`
- `find_government_service_guides`
- `query_public_dataset_rows`
- `ask_austin_data_question`
- `ask_city_data_question`
- `find_city_datasets_for_question`
- `search_city_knowledge`
- `search_dataset_columns`
- `find_answerable_datasets`
- `get_dataset_capabilities`
- `fetch_city_knowledge`
- `get_dataset_schema`
- `get_sample_rows`
- `query_dataset_count`
- `query_dataset_rows`

Secondary dataset-quality tools:

- `get_report_summary`
- `list_high_risk_datasets`
- `get_top_actionable_fixes`
- `compare_asset_types`
- `list_classification_review_candidates`
- `get_classification_methodology`
- `list_datasets_by_asset_group`
- `get_dataset_health`
- `suggest_dataset_category`
- `list_missing_category_suggestions`
- `explain_dataset_issue`
- `draft_department_email`
- `search_datasets`
- `search`
- `fetch`

## Scoring

Every dataset starts at `100`.

- `-30` for missing modified timestamp.
- `-25` for stale data only when `accrualPeriodicity` gives a known cadence and the modified date is older than `1.5x` that cadence.
- `-8` for low-confidence freshness risk when cadence is absent and the modified date is older than 365 days.
- `-15` for missing, boilerplate, same-as-title, or very short descriptions.
- `-15` for missing publisher/contact metadata.
- `-10` when license, category, or tags are missing.

Hard high-risk overrides for active datasets:

- No distribution.
- No distribution with `downloadURL` or `accessURL`.

## Classification

Every row gets an explicit classification before risk ranking:

- `active_dataset`: ongoing machine-readable data or records with clear active-dataset evidence.
- `needs_manual_review`: dated records without enough cadence or asset evidence for automatic classification.
- `archive_snapshot`: month, quarter, single-year, or bounded-year snapshots.
- `event_specific`: records tied to a specific incident or event.
- `measure`: Socrata measure or indicator assets.
- `story_reference`: Socrata stories, files, links, and other reference assets.

Evidence codes include `known_cadence`, `machine_readable_distribution`, `socrata_story_asset`, `socrata_measure_asset`, `socrata_reference_asset`, `month_quarter_snapshot`, `bounded_year_range`, `event_keyword`, and `manual_override`.

Manual corrections can be added to `classification_overrides.json`:

```json
{
  "overrides": {
    "abcd-1234": {
      "group": "archive_snapshot",
      "reason": "Owner confirmed this is a bounded historical snapshot.",
      "evidence": ["owner_review"]
    }
  }
}
```

After changing overrides, run with `--force` so the SQLite rows and static report are regenerated.

Socrata stories, measures, reference assets, detected event records, and archive snapshots stay visible in the report, but they are grouped separately from active dataset risk so monthly/quarterly snapshots, multi-year statistics, or indicator pages do not distort the high-risk queue.

Column metadata is intentionally outside the global score so enriched and unenriched datasets stay comparable.

## Category Suggestions

Each full run trains a lightweight TF-IDF-style category suggestion model from catalog records that already publish a category. Suggestions are stored separately from Austin's metadata and only appear as review hints when a record is missing a category.

The model uses title, description, tags, publisher/contact text, and Socrata asset type. It does not overwrite the catalog category. Report outputs include `suggested_category`, confidence, status, and evidence fields.

## Codex Plugin

This repo includes a repo-local Codex plugin wrapper:

- Manifest: `plugins/civic-data-health/.codex-plugin/plugin.json`
- MCP config: `plugins/civic-data-health/.mcp.json`
- Skill: `plugins/civic-data-health/skills/civic-data-health/SKILL.md`
- Marketplace entry: `.agents/plugins/marketplace.json`

The plugin points Codex at the hosted MCP server:

```bash
codex mcp add civic-data-health --url https://civic.pagonya.co/mcp
```

For public-facing discovery, use `ask_civic_data_question` or `ask_texas_government_question` first. They accept plain-English questions like "How do I start a food business permit process in Texas and Austin?" or "What data shows building permits?" and return official links, ranked datasets, bounded public rows when useful, quality caveats, and usable links.

## Row-Level Answers

The MCP can answer conservative live row-level count questions when the planner can identify:

- a matching active Socrata dataset,
- a cached or fetchable Socrata schema,
- a safe date column when the question includes a time period,
- a read-only aggregate query that does not expose arbitrary SoQL.

Example:

```text
How many building permits were issued in 2025?
```

The MCP ranks candidate datasets, selects a matching date column such as `issue_date`, runs a safe `count(*)` request against `https://data.austintexas.gov/resource/{dataset_id}.json`, and returns the answer with the dataset id, source link, query metadata, and caveats.

Supporting tools:

- `get_dataset_schema`: fetches and caches Socrata column metadata in SQLite.
- `get_sample_rows`: returns up to 20 live sample rows for a known dataset.
- `query_dataset_count`: runs a safe count over a known dataset, optionally with a validated date range.

Set `SOCRATA_APP_TOKEN` in the service environment if public traffic grows; unauthenticated Socrata calls can be throttled.

## Texas and Austin Government Data

The MCP's primary feature is public-government search for people who want to find useful Texas or Austin government data and official starting points for permits, licenses, services, and governance questions.

Primary tools:

- `ask_texas_government_question`: searches official Texas/Austin service resources and public open-data catalogs, then includes bounded public rows from matching queryable Socrata datasets when useful.
- `search_public_data_catalogs`: searches `https://data.texas.gov/data.json` and `https://data.austintexas.gov/data.json`.
- `find_government_service_resources`: returns official starting links for permit, license, business, and government-service questions.
- `find_government_service_guides`: returns curated starter guides for common workflows such as Texas business setup, Austin building permits, Austin food business permits, Austin property/zoning research, and Austin 3-1-1/code complaints.
- `query_public_dataset_rows`: fetches bounded read-only rows from a known State of Texas or Austin Socrata dataset.

Example:

```text
How do I start a food business permit process in Texas and Austin, and what public datasets can help me research it?
```

The tool returns curated service guides, official Texas and Austin starting links, matching open-data records, bounded row samples when a dataset is queryable, suggested dataset searches, and caveats that permit requirements depend on the agency, locality, business activity, property, and project scope.

Current service guides:

- Start a Texas business.
- Start an Austin building or trade permit.
- Start an Austin food business permit.
- Research Austin property, zoning, and development constraints.
- File or research Austin 3-1-1 and code complaints.

## Schema Knowledge

MCP tools can inspect Socrata schemas on demand and cache them in SQLite:

- `get_dataset_capabilities`: summarizes date, geography, numeric, categorical, and text fields for one dataset.
- `search_dataset_columns`: finds matching columns such as `council district`, `issue date`, `latitude`, `status`, or `amount` across the strongest catalog candidates.
- `find_answerable_datasets`: ranks datasets that can answer a plain-English question based on schema capabilities.
- `search_city_knowledge`: combines catalog search with schema-column search.
- `fetch_city_knowledge`: expands one dataset id into health, classification, category suggestion, and schema capabilities.

These tools intentionally inspect candidate datasets instead of fetching every schema on every run.

## Lightsail Deployment

The production paths are:

- App: `/opt/civic-data-health`
- SQLite/cache: `/var/lib/civic-data-health`
- Static report: `/var/www/civic-data-health`
- MCP: `127.0.0.1:8787` behind nginx

## ChatGPT App Store Submission

Public review URLs:

- MCP URL: `https://civic.pagonya.co/mcp`
- Website URL: `https://civic.pagonya.co/`
- Privacy policy: `https://civic.pagonya.co/privacy.html`
- Support: `https://civic.pagonya.co/support.html`
- Submission checklist: `https://civic.pagonya.co/submission.html`

Submission assets:

- Dashboard checklist: `docs/chatgpt-app-store-submission.md`
- Submission import/test case JSON: `chatgpt-app-submission.json`
- Icon: `assets/texas-civic-data-health-icon.png`

Before submitting, verify OpenAI organization identity, global data residency for the submitting project, support email delivery, screenshots, and the positive/negative test prompts in ChatGPT web and mobile. After OpenAI approval, publish from the Platform dashboard.

Install or update from GitHub:

```bash
deploy/install_lightsail.sh https://github.com/dennis-d/civic-data-health.git
```

Public endpoints:

- `https://civic.pagonya.co/`
- `https://civic.pagonya.co/mcp/health`
- `https://civic.pagonya.co/mcp`

The refresh timer runs daily and skips expensive reprocessing when the catalog SHA has not changed.
