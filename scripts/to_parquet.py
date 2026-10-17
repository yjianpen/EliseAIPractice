"""Convert the raw 311 CSV into Parquet partitioned by year.

Usage:  python3 scripts/to_parquet.py
Needs:  pip install duckdb
Output: data/processed/nyc_311/year=YYYY/*.parquet  (columnar, compressed, fast to query)
"""
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "nyc_311_2010_present.csv"
OUT = ROOT / "data" / "processed" / "nyc_311"

con = duckdb.connect()
con.execute("SET preserve_insertion_order = false")  # lower memory on big files
con.execute(f"""
    COPY (
        SELECT *,
               year(strptime("Created Date", '%m/%d/%Y %I:%M:%S %p')) AS year
        FROM read_csv('{RAW}', header = true, all_varchar = true)
    )
    TO '{OUT}' (FORMAT parquet, PARTITION_BY (year), COMPRESSION zstd, OVERWRITE_OR_IGNORE)
""")
print(con.execute(f"""
    SELECT year, count(*) AS rows
    FROM read_parquet('{OUT}/**/*.parquet', hive_partitioning = true)
    GROUP BY year ORDER BY year
""").fetchdf().to_string(index=False))
