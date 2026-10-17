"""query_db tool for the ReAct loop: read-only SQL over the company's structured data, scoped to ONE resident.

Each resident gets a fresh in-memory database that contains ONLY their own rows (data minimization):
  my_lease, my_unit, my_property, my_work_orders
so no query, however clever, can reach another tenant's data. A SQLite authorizer additionally makes the
database read-only (no writes, PRAGMA or ATTACH). Data comes from data/synthetic/*.csv.

Citations are deterministic: the same authorizer records every (table, column) a query reads, the query
plan (EXPLAIN OpenRead) catches tables the authorizer misses (e.g. count(*) over JOIN ... USING), and each
successful query appends its source file, record ids and columns to a ledger. Answers cite that ledger,
never text the model wrote, so a source appears only when the data was actually read.

Row-level lineage: for a simple single-table SELECT the query's own FROM/WHERE is re-run to cite only the
matching record ids (GROUP BY/HAVING/ORDER BY/LIMIT are ignored, so this may over-cite but never misses a
row). Anything else (joins, subqueries on other tables, CTEs, compound selects) falls back to citing all of
the resident's records for each table read, and the entry is marked exact=False.
"""
from __future__ import annotations

import csv
import re
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data" / "synthetic"
TABLES = {  # table the model sees -> (source CSV, column that must match the resident's keys)
    "my_lease": ("leases", "tenant_id"),
    "my_unit": ("units", "unit_id"),
    "my_property": ("properties", "property_id"),
    "my_work_orders": ("work_orders", "tenant_id"),
}
MAX_ROWS = 20
SIMPLE_SELECT = re.compile(  # SELECT ... FROM <table> [[AS] alias] [WHERE ...] [GROUP BY | ORDER BY | LIMIT ...]
    r"\s*SELECT\b.*?\bFROM\s+(?P<table>\w+)(?P<alias>\s+(?:AS\s+)?(?!(?:WHERE|GROUP|ORDER|LIMIT)\b)\w+)?"
    r"(?:\s+WHERE\s+(?P<where>.+?))?(?:\s+(?:GROUP\s+BY|ORDER\s+BY|LIMIT)\b.*?)?\s*;?\s*", re.I | re.S)


def matching_ids(con: sqlite3.Connection, sql: str, tables: set, id_col: dict) -> list | None:
    """Record ids of the rows a simple single-table SELECT filters to, or None if lineage can't be derived."""
    m = SIMPLE_SELECT.fullmatch(sql)
    if not m or len(tables) != 1 or m["table"] not in tables or re.search(r"\b(UNION|INTERSECT|EXCEPT)\b", sql, re.I):
        return None
    where = f" WHERE {m['where']}" if m["where"] else ""
    try:
        return [str(r[0]) for r in con.execute(f"SELECT {id_col[m['table']]} FROM {m['table']}{m['alias'] or ''}{where}")]
    except sqlite3.Error:
        return None


def query_db(con: sqlite3.Connection, sql: str) -> str:
    """Run one SELECT and return up to MAX_ROWS rows as text; errors come back as text for the agent."""
    try:
        cur = con.execute(sql)
    except sqlite3.Error as exc:
        return f"Error: {exc}. Only SELECT on {', '.join(TABLES)} is allowed."
    header, rows = [d[0] for d in cur.description or []], cur.fetchmany(MAX_ROWS + 1)
    lines = [" | ".join(header)] + [" | ".join(map(str, r)) for r in rows[:MAX_ROWS]]
    return "\n".join(lines + (["(more rows truncated)"] if len(rows) > MAX_ROWS else [])) if rows else "(no rows)"


def make_db_tools(tenant_id: str, data_dir: Path = DATA_DIR) -> tuple[dict, list[dict], list[dict]]:
    """Build this resident's read-only database; return the tools dict, the OpenAI (Responses API) tool spec
    and the citation ledger (one entry per table a successful query read)."""
    # cached_statements=0: the authorizer only runs when a statement is prepared, so never reuse one
    con = sqlite3.connect(":memory:", check_same_thread=False, cached_statements=0)
    keys, columns, ids = {"tenant_id": {tenant_id}}, {}, {}
    for table, (source, key) in TABLES.items():  # order matters: lease -> unit ids -> property ids
        with (data_dir / f"{source}.csv").open() as f:
            reader = csv.DictReader(f)
            rows = [r for r in reader if r[key] in keys.get(key, set())]
        columns[table] = reader.fieldnames
        ids[table] = [r[reader.fieldnames[0]] for r in rows]  # first column is the record id (lease_id, ...)
        for col in ("unit_id", "property_id"):
            keys.setdefault(col, set()).update(r[col] for r in rows if col in r)
        con.execute(f"CREATE TABLE {table} ({', '.join(columns[table])})")
        con.executemany(f"INSERT INTO {table} VALUES ({', '.join('?' * len(columns[table]))})",
                        [[int(v) if v.isdigit() else v for v in r.values()] for r in rows])

    roots = dict(con.execute("SELECT rootpage, name FROM sqlite_master"))  # b-tree page -> table, for EXPLAIN
    reads, ledger = set(), []  # (table, column) read by the current query; citations for the whole session

    def authorize(action, table, column, *_):
        if action == sqlite3.SQLITE_READ:
            reads.add((table, column))
        allowed = (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION)
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY

    con.set_authorizer(authorize)
    schema = "; ".join(f"{table}({', '.join(cols)})" for table, cols in columns.items())
    spec = {"type": "function", "name": "query_db",  # flat tool format of the OpenAI Responses API
            "description": f"Run ONE read-only SQLite SELECT on the resident's own records. Tables: {schema}. "
                           "Use it for rent, lease dates, deposit, unit and building details, work order status.",
            "parameters": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]}}

    def run(sql: str) -> str:
        reads.clear()
        out = query_db(con, sql)
        if not out.startswith("Error") and out != "(no rows)":  # cite only queries that returned data
            plan = {roots.get(row[3]) for row in con.execute(f"EXPLAIN {sql}") if row[1] == "OpenRead"}
            tables, read = (plan - {None}) | {t for t, _ in reads}, set(reads)  # lineage query adds reads
            matched = matching_ids(con, sql, tables, {t: cols[0] for t, cols in columns.items()})
            for table in sorted(tables):
                hit = set(matched or ())
                ledger.append({"source": f"{TABLES[table][0]}.csv", "exact": matched is not None,
                               "ids": ids[table] if matched is None else [i for i in ids[table] if i in hit],
                               "columns": sorted(c for t, c in read if t == table and c)})
        return out
    run.close = con.close  # callers that finish early (tests) can release the database
    return {"query_db": run}, [spec], ledger


def format_citations(ledger: list[dict], max_ids: int = 5) -> str:
    """Render ledger entries as a numbered Sources block, merging repeat reads of the same records."""
    merged: dict[tuple, set] = {}
    for entry in ledger:
        key = (entry["source"], tuple(entry["ids"]), entry.get("exact", True))
        merged.setdefault(key, set()).update(entry["columns"])
    lines = []
    for n, ((source, rec_ids, exact), cols) in enumerate(merged.items(), 1):
        more = f" (+{len(rec_ids) - max_ids} more)" if len(rec_ids) > max_ids else ""
        scope = "" if exact else " (all your records; row lineage unavailable)"
        lines.append(f"[{n}] {source}: {', '.join(rec_ids[:max_ids]) or 'no records'}{more}{scope} - "
                     f"{', '.join(sorted(cols)) or 'row count'}")
    return "Sources:\n" + "\n".join(lines) if lines else ""
