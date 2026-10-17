# Row-level lineage for DB citations

Before this change, a citation listed every one of the resident's records in each table a query read, so
`SELECT topic FROM my_work_orders WHERE status='open'` cited all of their work orders. Now a simple
single-table SELECT cites only the rows that match its filter. The work is done in code: `matching_ids` re-runs
the query's own `FROM <table> [alias] WHERE ...` and selects the record-id column. The tool spec and prompt are unchanged.

- GROUP BY / HAVING / ORDER BY / LIMIT are ignored when re-running the filter. The citation can therefore list
  more rows than were used, but it never leaves out a row that was used.
- Joins, subqueries on other tables, CTEs and UNION/INTERSECT/EXCEPT fall back to the old whole-record-set
  citation. Those ledger entries carry `exact: False`, and their citation line says
  `(all your records; row lineage unavailable)`.

Changed functions: `matching_ids` (new), `make_db_tools.run` and `format_citations`, plus their tests.

## Test locally (Mac)

```bash
.venv/bin/python -m unittest discover -s tests -q
```

Custom inputs: pass any tenant id, then one or more SQL queries:

```bash
.venv/bin/python -c "import sys; from db_tools import make_db_tools, format_citations; t,_,l=make_db_tools(sys.argv[1]); [print(t['query_db'](s)) for s in sys.argv[2:]]; print(format_citations(l))" T-00329 "SELECT topic FROM my_work_orders WHERE status='submitted'" "SELECT count(*) FROM my_lease JOIN my_unit USING (unit_id)"
```

Expected result: `[1]` cites only the one submitted work order (`WO-01535`). `[2]` and `[3]` (the join) are marked
"row lineage unavailable".

🤖 Generated with [Claude Code](https://claude.com/claude-code)
