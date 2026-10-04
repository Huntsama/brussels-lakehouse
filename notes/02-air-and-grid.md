# IRCEL air quality and Elia grid load

## IRCEL-CELINE (SOS API)
- Phenomenon ids: 8 = NO2, 5 = PM10, 6001 = PM2.5.
- There's no "Brussels" filter. Brussels station labels start with `41`, which gives 13 stations.
- Values come back hourly, with timestamps as epoch milliseconds.
- Asking for the last 24 h on every run is cheap, and dedupe fixes the overlap.

## Elia (ods001)
- Total Belgian load, one row per 15 minutes (`totalload`, MW).
- `limit=100` covers 25 h, more than enough when we pull every 15 min.
