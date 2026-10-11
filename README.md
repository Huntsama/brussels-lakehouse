# Brussels open-data lakehouse

Every 5 minutes this pipeline collects Brussels public-transport, air-quality and electricity data on Azure, and turns it into clean hourly tables and a public dashboard.

**Live dashboard:** https://belakehouselake.z1.web.core.windows.net/ (rebuilt every hour)

![Dashboard](docs/dashboard.png)

The page answers in plain words whether STIB is on time right now, shows the extra wait per hour for metro, tram and bus, the worst hours of the day, a map of every stop coloured by delay, and the lines furthest behind. Click a line to see which of its stops are late. Air quality, grid load and the full hourly table (with CSV download) sit below.

The question it answers:

> How much longer do people wait for a STIB metro, tram or bus than the timetable promises, how polluted is the air, and how much power is Belgium using, hour by hour?

## Sources (all open, no key)

| Source | What | How often |
|---|---|---|
| [STIB-MIVB](https://data.belgianmobility.io/) | live vehicle positions, waiting times at ~900 stops, 2,458 stop locations | real time, so we keep snapshots |
| STIB timetable (GTFS) | every scheduled departure (~485k for two service days) | weekly |
| [IRCEL-CELINE](https://geo.irceline.be/sos/api/v1/) | NO₂, PM10, PM2.5 at 13 Brussels stations | hourly |
| [Elia](https://opendata.elia.be/) | Belgian grid load (MW) | 15 min |

## Architecture

```mermaid
flowchart LR
  A[STIB / IRCEL / Elia APIs] -->|STIB every 5 min, air and grid every 15| F[Azure Function<br/>timer trigger]
  F -->|managed identity| B[(ADLS Gen2<br/>bronze: raw JSON)]
  B --> S[dbt silver<br/>clean, dedupe, typed]
  S --> G[dbt gold<br/>city_hourly]
  G --> D[Dashboard]
```

- **Bronze**: each API answer saved untouched as gzipped JSON, partitioned by `source/date=YYYY-MM-DD/HHMMSS.json.gz`.
- **Silver** (`transform/models/silver`): one tidy table per source. Overlapping snapshots are de-duplicated, latest revision wins.
- **Gold**:
  - `stop_line_hourly`: **Excess Wait Time** per stop, line and hour, the punctuality measure Transport for London uses for frequent services. Actual wait (minutes to the next vehicle at a random moment, from our snapshots) minus scheduled wait (`Σh² / 2Σh` over timetable headways).
  - `city_hourly`: one row per hour with median wait, excess wait, vehicles in service, NO₂/PM and grid load.
- **Tests**: pytest for the ingest, dbt tests (not null, unique, accepted values, value ranges) on every model. CI runs both on a small sample.
- **Infra as code**: `infra/main.tf` creates the data lake, the Function app (Flex Consumption), its role assignments and a $10/month budget alert.

## Analysis

`uv run python -m lakehouse.analysis` prints excess wait by mode, by line and by hour of day, and correlates it with air quality and grid load (raw, and with the daily rhythm removed so rush hour isn't mistaken for a link).

First look (13 hours, 10 Oct 2026): metro runs +0.5 min over its timetable, tram +0.4, bus +0.4. Bus 75 and tram 35 are the furthest behind. The correlations wait for a full week of data.

## Field notes

What the data actually looked like, and the problems on the way, in [`notes/`](notes/):
[STIB API](notes/01-stib.md) · [IRCEL and Elia](notes/02-air-and-grid.md) · [GTFS timetable](notes/03-gtfs.md) · [Excess Wait Time](notes/04-excess-wait.md) · [Azure deployment](notes/05-azure.md)

## Run it locally

```bash
uv sync --group dev
uv run python -m lakehouse.ingest          # one snapshot into data/bronze
uv run python -m lakehouse.ingest stops    # stop list (weekly is enough)
uv run python -m lakehouse.ingest gtfs     # timetable (weekly)
uv run dbt build --project-dir transform --profiles-dir transform
uv run pytest -q
uv run python -m lakehouse.report          # dashboard -> site/index.html
uv run python -m lakehouse.analysis        # the studies above, printed as tables
```

## Deploy to Azure

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars   # your subscription id and email
az login
terraform init && terraform apply
cd .. && func azure functionapp publish func-belakehouse
```

## Limits

- STIB publishes no history, so delays can only be measured from the snapshots this pipeline has collected.
- Actual wait uses STIB's live prediction of the next arrival, not a measured arrival. Excess wait is only as good as that prediction.
- About 24% of live stop IDs have no exact match in the GTFS timetable, so those stops are left out of excess wait.
- Elia's measured load arrives with about a day of delay; the latest hours are empty until it does.
- Brussels air is averaged over all stations; per-commune values need a stop-to-station mapping.

## Status

- [x] Ingest STIB, IRCEL and Elia into bronze
- [x] dbt silver and gold with tests, CI
- [x] Terraform for Azure (lake, function, budget)
- [x] Excess Wait Time vs the GTFS timetable
- [x] Deployed on Azure (Germany West Central), STIB snapshots every 5 min, air and grid every 15
- [x] Public dashboard, rebuilt hourly by GitHub Actions
- [x] Analysis script: by mode, by line, by hour, correlations
- [ ] One week of data, then the correlation study written up
- [ ] Power BI / Fabric report
