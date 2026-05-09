# Civic Data Health

Deterministic Austin Open Data health reports with a read-only MCP endpoint.

V1 uses only public City of Austin catalog data from `https://data.austintexas.gov/data.json`. It fetches the catalog once, stores raw snapshots and normalized rows in SQLite, scores dataset metadata, exports static report files, and serves MCP tools from SQLite.

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

Tools:

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
- `ask_city_data_question`
- `find_city_datasets_for_question`
- `get_dataset_capabilities`
- `search_dataset_columns`
- `find_answerable_datasets`
- `search_city_knowledge`
- `fetch_city_knowledge`
- `get_dataset_schema`
- `get_sample_rows`
- `query_dataset_count`
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

For public-facing discovery, use `ask_city_data_question` first. It accepts plain-English questions like "Where can I find police calls?" or "What data shows building permits?" and returns ranked datasets, match reasons, quality caveats, and usable links.

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

Install or update from GitHub:

```bash
deploy/install_lightsail.sh https://github.com/dennis-d/civic-data-health.git
```

Public endpoints:

- `https://civic.pagonya.co/`
- `https://civic.pagonya.co/mcp/health`
- `https://civic.pagonya.co/mcp`

The refresh timer runs daily and skips expensive reprocessing when the catalog SHA has not changed.
