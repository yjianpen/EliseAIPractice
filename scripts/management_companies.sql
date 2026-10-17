-- Who runs each building? Joins 311 housing complaints to HPD building registrations.
-- DuckDB only: reads the two HPD datasets directly from NYC Open Data over HTTPS (httpfs autoloads).
-- Run from the repo root:   duckdb data/processed/hpd.duckdb < scripts/management_companies.sql
-- First run downloads ~1M contact rows (a minute or two); later runs reuse the saved tables.

INSTALL httpfs; LOAD httpfs;

-- 1. HPD Multiple Dwelling Registrations (one row per registered building)
CREATE TABLE IF NOT EXISTS registrations AS
SELECT * FROM read_csv('https://data.cityofnewyork.us/api/views/tesw-yqqr/rows.csv?accessType=DOWNLOAD',
                       header = true, all_varchar = true);

-- 2. HPD Registration Contacts (owners, officers, managing agent, site manager per registration)
CREATE TABLE IF NOT EXISTS contacts AS
SELECT * FROM read_csv('https://data.cityofnewyork.us/api/views/feu5-w2e2/rows.csv?accessType=DOWNLOAD',
                       header = true, all_varchar = true);

.mode box
.maxwidth 200
-- Check column names (adjust the queries below if HPD renamed anything)
SELECT column_name FROM (DESCRIBE registrations);
SELECT column_name FROM (DESCRIBE contacts);
SELECT Type, count(*) AS n FROM contacts GROUP BY 1 ORDER BY 2 DESC;

-- 3. Building -> managing agent (and corporate owner), keyed by 10-digit BBL like the 311 data
CREATE OR REPLACE VIEW building_operator AS
WITH reg AS (
  SELECT RegistrationID, BuildingID,
         BoroID || lpad(Block, 5, '0') || lpad(Lot, 4, '0') AS bbl,
         HouseNumber || ' ' || StreetName AS reg_address,
         try_strptime(RegistrationEndDate, '%m/%d/%Y') AS reg_end
  FROM registrations)
SELECT r.bbl, r.reg_address, r.reg_end,
       max(CASE WHEN c.Type = 'Agent'          THEN coalesce(nullif(c.CorporationName, ''), c.FirstName || ' ' || c.LastName) END) AS managing_agent,
       max(CASE WHEN c.Type = 'CorporateOwner' THEN c.CorporationName END)                                                  AS corporate_owner,
       max(CASE WHEN c.Type = 'Agent'          THEN c.BusinessHouseNumber || ' ' || c.BusinessStreetName || ', ' || c.BusinessCity END) AS agent_address
FROM reg r LEFT JOIN contacts c USING (RegistrationID)
GROUP BY ALL
QUALIFY row_number() OVER (PARTITION BY r.bbl ORDER BY r.reg_end DESC NULLS LAST) = 1;  -- latest registration per building

-- 4. Management companies ranked by 311 housing complaints
SELECT upper(trim(o.managing_agent)) AS managing_agent,
       count(DISTINCT s.BBL)        AS buildings,
       count(*)                     AS complaints,
       round(count(*) / count(DISTINCT s.BBL), 1) AS complaints_per_building,
       round(100.0 * count(*) FILTER (WHERE s."Problem (formerly Complaint Type)" = 'HEAT/HOT WATER') / count(*)) AS pct_heat
FROM 'data/processed/nyc_311.parquet' s
JOIN building_operator o ON s.BBL = o.bbl
WHERE s.Agency = 'HPD' AND o.managing_agent IS NOT NULL
GROUP BY 1 ORDER BY complaints DESC LIMIT 25;

-- 5. Example lookup: who runs a given address?
SELECT o.reg_address, o.managing_agent, o.corporate_owner, o.agent_address, count(*) AS hpd_complaints
FROM 'data/processed/nyc_311.parquet' s JOIN building_operator o ON s.BBL = o.bbl
WHERE s.Agency = 'HPD' AND s."Incident Address" = '957 WOODYCREST AVENUE'
GROUP BY ALL;
