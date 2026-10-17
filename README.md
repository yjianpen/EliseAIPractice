# EliseAI interview practice: NYC 311 Service Requests

Source: NYC Open Data, "311 Service Requests from 2010 to Present" (dataset id `erm2-nwe9`)
https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2010-to-Present/erm2-nwe9

## Layout
- `data/raw/` – untouched CSV export (never edit)
- `data/processed/nyc_311.parquet` – typed Parquet copy of the raw CSV
- `dependencies.txt` – Python packages; `setup.sh` – one-command install
- `scripts/download_311.sh` – resumable download of the raw CSV
- `scripts/to_parquet.py` – CSV → partitioned Parquet (DuckDB)
- `knowledge/` – RAG source documents: issue taxonomy, policy guidebooks, law records
- `synthetic/generate.py` – synthetic property-management source of truth → `data/synthetic/*.csv`
- `rag/` – builds and queries the policy and law databases (`data/rag/*.db`)
- `structured/` – builds and queries the structured property-facts database (`data/structured/property_facts.db`)
- `tests/` – `python -m unittest`

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

## Source of truth and RAG databases

The agent answers a resident **at a specific property**. Four layers of truth:

| Layer | What it answers | Where it lives |
|---|---|---|
| Structured source of truth | "What's happening in my unit?" (work orders, lease, building facts, compliance dates) | `data/synthetic/*.csv` |
| Structured facts (SQL, no embeddings) | "How much is rent / the pet fee / parking?" | `synthetic/profiles.py` → `data/synthetic/*.csv` → `data/structured/property_facts.db` |
| Policy RAG | "What does my building/company do about this?" | `knowledge/policies/` + `knowledge/buildings/` → `data/rag/policies.db` |
| Law RAG | "What am I entitled to here?" | `knowledge/laws/` → `data/rag/laws.db` |

311 data stays a signal for patterns (which issues are common, when they spike), not a source of truth.

```bash
python -m synthetic.generate     # (re)create synthetic CSVs + property addenda (deterministic, --seed 311)
python -m rag.build              # build data/rag/policies.db and data/rag/laws.db
python -m rag.cli properties
python -m rag.cli ask "the radiator is cold" --property P-NYC-001 --unit P-NYC-001-3B
python -m rag.cli ask "can my landlord come in without notice?" --property P-SF-002 --json
python -m rag.cli laws "mold in the bathroom" --city "San Francisco" --state CA
python -m structured.cli costs P-NYC-003                     # rent + required monthly charges
python -m structured.cli move-in P-SF-003 --unit-type "1 Bedroom" --pets 1
python -m structured.cli sql "SELECT property, unit_type, total_min, total_max FROM v_monthly_costs ORDER BY total_min"
python -m unittest -v
```

`python -m rag.build` also builds the structured database, so one command refreshes everything.

No new dependencies: all three databases are SQLite (the two RAG ones use FTS5 full-text search with BM25) from the Python standard library.

### How it adapts to each city and apartment
- **Taxonomy** (`knowledge/taxonomy.json`): 33 topics (heat, mold, pests, noise, entry_access, ...), each linked to
  the 311 `(Problem, Problem Detail)` pairs, keywords for detecting the topic in a message, and a default urgency
  (`emergency`, `urgent`, `routine`, `city`). Topics are the join key between data, policies and laws.
- **Policies**: a company guidebook per management company (`knowledge/policies/companies/`), with sections tagged
  `cities: all` or a specific city, plus a generated addendum per property (`knowledge/policies/properties/`) built
  from that building's facts (heat system, quiet hours, trash days, year built, contacts). Retrieval for a property
  only sees its own company's guidebook (only the sections for its city) and its own addendum; the addendum overrides
  the guidebook.
- **Laws**: one JSON file per jurisdiction (`federal`, state, city). A property in San Francisco gets federal + CA +
  SF records only. Each record has a citation, a plain-language summary, key points, a source URL and a
  `verified_on` date (null = summary not re-checked against the source; the context marks it unverified).
- **Ranking**: topic gate (only records tagged with a detected topic qualify) → BM25 relevance to reorder → precedence
  (property addendum > company guidebook; city law > state > federal). Questions with no detected topic need real
  word matches, so off-topic questions return nothing instead of a guess.
- **Context** (`rag.retrieve.build_context`): property and company facts, the unit's open work orders for the topic,
  urgency and escalation instructions, NYC heat-season status, linked compliance records, and policy `[P#]` / law
  `[L#]` passages ready to cite in an LLM prompt (`render_context`).

### Structured facts vs. prose (one source for every number)
- `synthetic/profiles.py` holds each building's operating profile: unit types and advertised rents, the fee
  schedule (application, deposits, required monthly charges such as amenity, trash or water/sewer fees, optional
  parking/storage, pet charges, late fee), pet rules, parking, utilities (included / paid directly / billed back)
  and amenities. Each value is tagged `listing` (seen on a public listing page, with `source_url` and
  `observed_on`) or `synthetic`.
- The generator writes those to CSVs and to `knowledge/buildings/<id>.md` building guides. Guides describe how
  things work and say "see the fee schedule"; **no dollar amounts appear in any prose document** (enforced by a
  test), so the RAG text and the database cannot disagree.
- `data/structured/property_facts.db` (SQLite) has typed tables with foreign keys and views:
  `v_current_fees` (only fees in effect), `v_monthly_costs` (rent + required monthly charges),
  `v_move_in_costs`, `v_pet_costs`. Python helpers in `structured/query.py` take an explicit `as_of` date, so an
  expired offer (e.g. 303 East 83rd's 2025 deposit special) never appears in an answer.
- `build_context` adds a FACTS block (`[F#]`) with the exact rows for fee, rent, pet, parking, utility, amenity,
  leasing and moving questions, plus the resident's own lease when a unit is given. Maintenance questions get no
  facts block.
- Building-guide notices carry `posted`/`expires` dates; retrieval drops a notice outside its window.

### Company policies
Each operator's guidebook (`knowledge/policies/companies/`) now also covers paying rent and late rent, the fee
schedule, pets, parking and storage, amenity reservations, utility billing, renewals and move-out/deposit return.

### Adding a city or property
1. Add `knowledge/laws/<city>.json` (and the state file if new), using taxonomy topics.
2. Add city-specific sections to the company guidebook with `<!-- topics: ... | cities: <City> -->`.
3. Add the property to `PROPERTIES` in `synthetic/real_entities.py` (with `source_urls` and `verified_fields`),
   then run `python -m synthetic.generate && python -m rag.build`.

### What is real and what is synthetic

| Real (verified, with sources) | Synthetic (invented for practice) |
|---|---|
| Operators: Vivmark Residential (AvalonBay + Equity Residential, merged Aug 2026), Beam Living (StuyTown, owned by Blackstone), Essex Property Trust | Guidebooks and addenda in `knowledge/policies/` (marked "practice"; not the companies' actual policies) |
| Buildings: StuyTown, 303 East 83rd, The Brooklyner, Fox Plaza, Park West, AVA 55 Ninth: name, address, year built, unit count, floors | Building operating details (heat system, quiet hours, trash days, pets), contacts, all phone numbers (reserved 555-01xx range) |
| | Tenants, leases, work orders, vendors, compliance dates (a modeled sample of units per building) |

Each company and property row carries `source_urls`, `verified_fields`, `synthetic_fields` and `verified_on`
(see `synthetic/real_entities.py`). Law summaries are for practice, not legal advice; each links to its source.

### Data freshness (next)
The operator and building facts are a static snapshot taken on `verified_on`. They go stale: AvalonBay and Equity
Residential became Vivmark Residential in August 2026, and Mosso (900 Folsom St), an Essex property in 2015, is now
managed by Brookfield. Planned work: re-verify records past a max age, track changes with valid-from/valid-to dates
instead of overwriting, and surface record age in the agent context so it can hedge or refuse on stale facts.
