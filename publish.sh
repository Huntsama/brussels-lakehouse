#!/usr/bin/env bash
# Pull bronze from the lake, rebuild silver/gold, publish the dashboard page.
set -euo pipefail
ACCOUNT=${LAKE_ACCOUNT:-belakehouselake}
# */*/* = real files only; the lake also lists its folders (source/, source/date=...) as empty blobs.
# re-downloads everything each run; switch to azcopy sync once bronze is big
az storage blob download-batch -s bronze -d data/bronze --pattern '*/*/*' \
  --account-name "$ACCOUNT" --auth-mode key --overwrite -o none --only-show-errors
uv run dbt build --project-dir transform --profiles-dir transform
uv run python -m lakehouse.report site/index.html
az storage blob upload --account-name "$ACCOUNT" --auth-mode key -c '$web' -f site/index.html -n index.html \
  --content-type "text/html; charset=utf-8" --overwrite -o none
echo "https://$ACCOUNT.z1.web.core.windows.net/"
