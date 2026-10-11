# Azure deployment notes

- The Azure for Students policy only allows a few regions. westeurope is refused, so we use germanywestcentral.
- Flex Consumption function app: a timer every 15 min for the snapshots, plus weekly jobs for stops and GTFS.
- The function writes to ADLS Gen2 (bronze/silver/gold containers) through its managed identity.
- The lake also lists folders as empty blobs, so the download pattern `*/*/*` keeps real files only.
- $10 budget alert, because the credit is limited.
- The dashboard is a static page on the lake's `$web` container.

## 11 Oct: every 5 minutes
- With 4 snapshots an hour, a stop that is served every 8 minutes gets only a few wait readings per hour, so excess wait was noisy. STIB now runs every 5 min; IRCEL (hourly) and Elia (15 min) stay on a 15-min timer, polling them faster adds nothing.
- One STIB waiting-times snapshot is ~1.1 MB of JSON, 69 KB gzipped. Snapshots are now `.json.gz`; DuckDB reads old and new files with the same `*.json*` glob.
- The hourly publish job used to download the whole lake every run. That grows into hundreds of GB of egress a month, past the 100 GB free allowance. Bronze now sits in the GitHub Actions cache and only yesterday and today are downloaded.
