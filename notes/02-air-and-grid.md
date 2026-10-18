# IRCEL air quality and Elia grid load

## IRCEL-CELINE (SOS API)
- Phenomenon ids: 8 = NO2, 5 = PM10, 6001 = PM2.5.
- There's no "Brussels" filter. Brussels station labels start with `41`, which gives 13 stations.
- Values come back hourly, with timestamps as epoch milliseconds.
- Asking for the last 24 h on every run is cheap, and dedupe fixes the overlap.

## Elia (ods001)
- Total Belgian load, one row per 15 minutes (`totalload`, MW).
- `limit=100` covers 25 h, more than enough when we pull every 15 min.

## 16 Oct: negative PM2.5
- On a clean night (16 Oct, 21:00 and 22:00) four stations reported PM2.5 slightly below zero, down to -0.5 µg/m³. Optical sensors drift around zero when there is almost nothing to measure.
- The dbt range test rejected them, gold was skipped, and the hourly dashboard stopped updating for two days while ingest kept running. Silver now floors the value at 0.
