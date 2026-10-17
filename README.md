# EliseAI interview practice: NYC 311 Service Requests

Source: NYC Open Data, "311 Service Requests from 2010 to Present" (dataset id `erm2-nwe9`)
https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2010-to-Present/erm2-nwe9

## Layout
- `data/raw/` – untouched CSV export (never edit)
- `data/processed/nyc_311.parquet` – typed Parquet copy of the raw CSV
- `dependencies.txt` – Python packages; `setup.sh` – one-command install
- `scripts/download_311.sh` – resumable download of the raw CSV
- `scripts/to_parquet.py` – CSV → partitioned Parquet (DuckDB)

## Quick start
Install all dependencies (creates `.venv` with Python 3.13 and installs `dependencies.txt`):

```bash
cd EliseAIPractice
bash setup.sh
source .venv/bin/activate
```

## Data steps
    bash scripts/download_311.sh
    python scripts/to_parquet.py

## Querying (DuckDB)
- `data/processed/nyc_311.parquet` – typed copy of the raw CSV (timestamps parsed, lat/lon as numbers), 2.71M rows
- `scripts/build_db.sql` – the typing logic used to build it
- `duckdb` command: `setup.sh` installs the DuckDB CLI into `.venv/bin`, so it works after `source .venv/bin/activate`

    duckdb -c "SELECT Agency, count(*) FROM 'data/processed/nyc_311.parquet' GROUP BY 1 ORDER BY 2 DESC"

Note: the raw download was cut off mid-row. Full coverage is roughly Dec 2025 to Sep 2026; earlier months hold only a few straggler records.
