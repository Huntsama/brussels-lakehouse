#!/usr/bin/env bash
# Pull bronze from the lake, rebuild silver/gold, publish the dashboard page.
set -euo pipefail
ACCOUNT=${LAKE_ACCOUNT:-belakehouselake}
# */*/* = real files only; the lake also lists its folders (source/, source/date=...) as empty blobs.
# Older days come from the GitHub Actions cache, so normally only yesterday and today are downloaded:
# re-pulling the whole lake every hour would blow through Azure's free download allowance.
download() {
  az storage blob download-batch -s bronze -d data/bronze --pattern "$1" \
    --account-name "$ACCOUNT" --auth-mode key --overwrite -o none --only-show-errors
}
if [ -d data/bronze/stib_waiting ]; then
  for day in "$(date -u -d yesterday +%F)" "$(date -u +%F)"; do download "*/date=$day/*"; done
else
  mkdir -p data/bronze
  download '*/*/*'
fi
uv run dbt build --project-dir transform --profiles-dir transform
uv run python -m lakehouse.report site/index.html
az storage blob upload --account-name "$ACCOUNT" --auth-mode key -c '$web' -f site/index.html -n index.html \
  --content-type "text/html; charset=utf-8" --overwrite -o none
az storage blob upload --account-name "$ACCOUNT" --auth-mode key -c '$web' -f site/lines.json -n lines.json \
  --content-type "application/json" --overwrite -o none
echo "https://$ACCOUNT.z1.web.core.windows.net/"
