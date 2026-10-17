"""query_db tool for the ReAct loop: read-only SQL over the company's structured data, scoped to ONE resident.

Each resident gets a fresh in-memory database that contains ONLY their own rows (data minimization):
  my_lease, my_unit, my_property, my_work_orders
so no query, however clever, can reach another tenant's data. A SQLite authorizer additionally makes the
database read-only (no writes, PRAGMA or ATTACH). Data comes from data/synthetic/*.csv.
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


def make_db_tools(tenant_id: str, data_dir: Path = DATA_DIR) -> tuple[dict, list[dict]]:
    """Build this resident's read-only database; return the tools dict and the OpenAI (Responses API) tool spec."""
    con, keys, columns = sqlite3.connect(":memory:", check_same_thread=False), {"tenant_id": {tenant_id}}, {}
    for table, (source, key) in TABLES.items():  # order matters: lease -> unit ids -> property ids
        with (data_dir / f"{source}.csv").open() as f:
            reader = csv.DictReader(f)
            rows = [r for r in reader if r[key] in keys.get(key, set())]
        columns[table] = reader.fieldnames
        for col in ("unit_id", "property_id"):
            keys.setdefault(col, set()).update(r[col] for r in rows if col in r)
        con.execute(f"CREATE TABLE {table} ({', '.join(columns[table])})")
        con.executemany(f"INSERT INTO {table} VALUES ({', '.join('?' * len(columns[table]))})",
                        [[int(v) if v.isdigit() else v for v in r.values()] for r in rows])

    def authorize(action, *_):
        allowed = (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION)
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY

    con.set_authorizer(authorize)
    schema = "; ".join(f"{table}({', '.join(cols)})" for table, cols in columns.items())
    spec = {"type": "function", "name": "query_db",  # flat tool format of the OpenAI Responses API
            "description": f"Run ONE read-only SQLite SELECT on the resident's own records. Tables: {schema}. "
                           "Use it for rent, lease dates, deposit, unit and building details, work order status.",
            "parameters": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]}}
    return {"query_db": lambda sql: query_db(con, sql)}, [spec]
