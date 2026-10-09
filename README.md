# Brussels open-data lakehouse

Every 15 minutes this pipeline collects Brussels public-transport, air-quality and electricity data, and turns it into one clean hourly table:

> How much longer do people wait for a STIB tram or bus than the timetable promises, how polluted is the air, and how much power is Belgium using, hour by hour?

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
  A[STIB / IRCEL / Elia APIs] -->|every 15 min| F[Azure Function<br/>timer trigger]
  F -->|managed identity| B[(ADLS Gen2<br/>bronze: raw JSON)]
  B --> S[dbt silver<br/>clean, dedupe, typed]
  S --> G[dbt gold<br/>city_hourly]
  G --> D[Dashboard]
```

- **Bronze**: each API answer saved untouched, partitioned by `source/date=YYYY-MM-DD/HHMMSS.json`.
- **Silver** (`transform/models/silver`): one tidy table per source. Overlapping snapshots are de-duplicated, latest revision wins.
- **Gold**:
  - `stop_line_hourly`: **Excess Wait Time** per stop, line and hour, the punctuality measure Transport for London uses for frequent services. Actual wait (minutes to the next vehicle at a random moment, from our snapshots) minus scheduled wait (`Σh² / 2Σh` over timetable headways).
  - `city_hourly`: one row per hour with median wait, excess wait, vehicles in service, NO₂/PM and grid load.
- **Tests**: pytest for the ingest, dbt tests (not null, unique, accepted values, value ranges) on every model. CI runs both on a small sample.
- **Infra as code**: `infra/main.tf` creates the data lake, the Function app (Flex Consumption), its role assignments and a $10/month budget alert.

## Run it locally

```bash
uv sync --group dev
uv run python -m lakehouse.ingest          # one snapshot into data/bronze
uv run python -m lakehouse.ingest stops    # stop list (weekly is enough)
uv run python -m lakehouse.ingest gtfs     # timetable (weekly)
uv run dbt build --project-dir transform --profiles-dir transform
uv run pytest -q
uv run python -m lakehouse.report          # dashboard -> site/index.html
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
- [ ] Deployed and running on Azure for a week
- [ ] Dashboard (Power BI / Fabric, plus a public page on jwds.me)
- [x] Excess Wait Time vs the GTFS timetable
