-- Build typed table `sr` from the raw CSV. Run from the project root:
--   duckdb data/processed/nyc311.duckdb < scripts/build_db.sql
CREATE OR REPLACE TABLE sr AS
SELECT * REPLACE (
  strptime("Created Date", '%m/%d/%Y %I:%M:%S %p') AS "Created Date",
  try_strptime("Closed Date", '%m/%d/%Y %I:%M:%S %p') AS "Closed Date",
  try_strptime("Due Date", '%m/%d/%Y %I:%M:%S %p') AS "Due Date",
  try_strptime("Resolution Action Updated Date", '%m/%d/%Y %I:%M:%S %p') AS "Resolution Action Updated Date",
  try_cast(Latitude AS DOUBLE) AS Latitude,
  try_cast(Longitude AS DOUBLE) AS Longitude,
  try_cast("Unique Key" AS BIGINT) AS "Unique Key")
FROM read_csv('data/raw/nyc_311_2010_present.csv', header=true, all_varchar=true, ignore_errors=true, parallel=false);
