# Cite the DB records behind every answer (deterministic, no prompting)

Stacked on `redo/query-db-tool` (needs `db_tools.py` / `query_db`).

## What
Every answer that used `query_db` now ends with a `Sources:` block naming the source file, record ids and
columns that were actually read, e.g.

```
Your monthly rent is $3,320.

Sources:
[1] leases.csv: L-00001 - monthly_rent
```

## Why it is deterministic
- Citations come from a **ledger built by code**, never from model text. The model prompt and tool spec are unchanged.
- The existing SQLite authorizer now also records every `(table, column)` a query reads (`SQLITE_READ`).
- `EXPLAIN` `OpenRead` opcodes catch tables the authorizer misses (SQLite reports no column reads for `count(*)` over `JOIN ... USING`).
- `cached_statements=0` makes the authorizer run on every query, including repeated SQL.
- Only queries that returned data are cited (errors and `(no rows)` are skipped). Each turn cites only its own queries.
- Memory stores the **uncited** answer, so the model never sees a Sources block and can't learn to write one.

## Size
3 functions: `make_db_tools` (modified; its `authorize` closure records reads and a `run` closure replaces the old lambda), `format_citations` (new), `respond` (modified).
About 100 changed lines in total, including tests and `TODO_citations.md` (deferred follow-ups: row-level lineage, structured citations, RAG citations).

## How to test locally
```bash
./setup.sh
.venv/bin/python -m unittest discover -s tests -q
```
Offline check (no API key needed):
```bash
.venv/bin/python -c "from db_tools import make_db_tools, format_citations; t,_,l=make_db_tools('T-00001'); t['query_db']('SELECT monthly_rent FROM my_lease'); print(format_citations(l))"
```
Expected: `[1] leases.csv: L-00001 - monthly_rent`.

With your own inputs (no API key needed): the first argument is any tenant id, then any number of SQL queries.
```bash
.venv/bin/python -c "import sys; from db_tools import make_db_tools, format_citations; t,_,l=make_db_tools(sys.argv[1]); [print(f'> {s}', t['query_db'](s), sep='\n') for s in sys.argv[2:]]; print(format_citations(l) or '(no sources)')" T-00042 "SELECT monthly_rent, end_date FROM my_lease" "SELECT topic, status FROM my_work_orders" "SELECT bogus FROM my_lease"
```
Expected: each query's rows, then sources for the successful queries only:
`[1] leases.csv: L-00042 - end_date, monthly_rent` and `[2] work_orders.csv: WO-00086, ... - status, topic`.
To find tenant ids, run `cut -d, -f1,3,4 data/synthetic/tenants.csv | head`. The tables are `my_lease`, `my_unit`, `my_property` and `my_work_orders`; the columns are listed in the CSV headers under `data/synthetic/`.

Live (needs `OPENAI_API_KEY` in `.env`): use any tenant id, and ask your own questions.
```bash
.venv/bin/python agent.py T-00001
```
Ask "How much is my rent?" and the reply should end with a Sources block. Ask "thanks", and the reply should have no Sources block.

## Known limitation
Citations are at the table/record-set level. For a filtered query on `my_work_orders`, all of the resident's work orders are listed (capped at 5 + "N more"), not only the matching rows. This is tracked in `TODO_citations.md`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
