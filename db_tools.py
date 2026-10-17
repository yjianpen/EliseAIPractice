"""query_db tool for the ReAct loop: read-only SQL over the company's structured data, scoped to ONE resident.

Each resident gets a fresh in-memory database that contains ONLY their own rows (data minimization):
  my_lease, my_unit, my_property, my_work_orders
so no query, however clever, can reach another tenant's data. A SQLite authorizer additionally makes the
database read-only (no writes, PRAGMA or ATTACH). Data comes from data/synthetic/*.csv.

Citations are deterministic: the same authorizer records every (table, column) a query reads, the query
plan (EXPLAIN OpenRead) catches tables the authorizer misses (e.g. count(*) over JOIN ... USING), and each
successful query appends its source file, record ids and columns to a ledger. Answers cite that ledger,
never text the model wrote, so a source appears only when the data was actually read.
"""
from __future__ import annotations

import csv
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
            for table in sorted((plan - {None}) | {t for t, _ in reads}):
                ledger.append({"source": f"{TABLES[table][0]}.csv", "ids": ids[table],
                               "columns": sorted(c for t, c in reads if t == table and c)})
        return out
    return {"query_db": run}, [spec], ledger


def format_citations(ledger: list[dict], max_ids: int = 5) -> str:
    """Render ledger entries as a numbered Sources block, merging repeat reads of the same records."""
    merged: dict[tuple, set] = {}
    for entry in ledger:
        merged.setdefault((entry["source"], tuple(entry["ids"])), set()).update(entry["columns"])
    lines = []
    for n, ((source, rec_ids), cols) in enumerate(merged.items(), 1):
        more = f" (+{len(rec_ids) - max_ids} more)" if len(rec_ids) > max_ids else ""
        lines.append(f"[{n}] {source}: {', '.join(rec_ids[:max_ids]) or 'no records'}{more} - "
                     f"{', '.join(sorted(cols)) or 'row count'}")
    return "Sources:\n" + "\n".join(lines) if lines else ""
