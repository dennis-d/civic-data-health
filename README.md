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
- `list_datasets_by_asset_group`
- `get_dataset_health`
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

Socrata stories, measures, reference assets, and detected point-in-time/event records stay visible in the report, but they are grouped separately from active dataset risk so archival or indicator pages do not distort the high-risk queue.

Column metadata is intentionally outside the global score so enriched and unenriched datasets stay comparable.

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
