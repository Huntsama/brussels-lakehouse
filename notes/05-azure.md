# Azure deployment notes

- The Azure for Students policy only allows a few regions. westeurope is refused, so we use germanywestcentral.
- Flex Consumption function app: a timer every 15 min for the snapshots, plus weekly jobs for stops and GTFS.
- The function writes to ADLS Gen2 (bronze/silver/gold containers) through its managed identity.
- The lake also lists folders as empty blobs, so the download pattern `*/*/*` keeps real files only.
- $10 budget alert, because the credit is limited.
- The dashboard is a static page on the lake's `$web` container.
