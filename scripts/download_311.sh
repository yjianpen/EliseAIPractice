#!/usr/bin/env bash
# Download the full NYC 311 Service Requests (2010-present) CSV export.
# Resumable: re-run the script if the connection drops and it continues where it stopped.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/data/raw/nyc_311_2010_present.csv"
URL="https://data.cityofnewyork.us/api/views/erm2-nwe9/rows.csv?accessType=DOWNLOAD"
mkdir -p "$(dirname "$OUT")"
echo "Downloading to $OUT"
curl -L --fail --retry 10 --retry-delay 5 -C - -o "$OUT" "$URL"
echo "Done: $(du -h "$OUT" | cut -f1)"
echo "Rows (excluding header): $(($(wc -l < "$OUT") - 1))"
