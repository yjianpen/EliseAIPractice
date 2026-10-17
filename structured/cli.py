"""Command line for the structured property-facts database.

  python -m structured.cli build
  python -m structured.cli fees P-SF-003
  python -m structured.cli costs P-NYC-003
  python -m structured.cli move-in P-SF-003 --unit-type "1 Bedroom" --pets 1
  python -m structured.cli pets P-NYC-002
  python -m structured.cli sql "SELECT property, unit_type, total_min, total_max FROM v_monthly_costs"
"""
from __future__ import annotations

import argparse

from . import build as build_mod
from . import query as q


def _table(rows: list[dict]) -> None:
    if not rows:
        print("(no rows)")
        return
    cols = list(rows[0].keys())
    widths = {c: min(40, max(len(c), *(len(str(r[c])) for r in rows))) for c in cols}
    print("  ".join(c.ljust(widths[c]) for c in cols))
    for r in rows:
        print("  ".join(str(r[c])[:40].ljust(widths[c]) for c in cols))


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m structured.cli", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    for name in ("fees", "costs", "pets", "amenities", "utilities"):
        sp = sub.add_parser(name)
        sp.add_argument("property")
        sp.add_argument("--as-of")
    m = sub.add_parser("move-in")
    m.add_argument("property")
    m.add_argument("--unit-type", required=True)
    m.add_argument("--pets", type=int, default=0)
    m.add_argument("--as-of")
    s = sub.add_parser("sql")
    s.add_argument("query")
    a = ap.parse_args()

    if a.cmd == "build":
        build_mod.main()
    elif a.cmd == "fees":
        _table([{k: f[k] for k in ("fee_name", "category", "amount", "basis", "frequency", "required", "provenance")}
                for f in q.fee_schedule(a.property, a.as_of)])
    elif a.cmd == "costs":
        _table([{k: v for k, v in c.items() if k != "fees"} for c in q.monthly_costs(a.property, a.as_of)])
    elif a.cmd == "pets":
        print(q.pet_policy(a.property))
        _table(q.fee_schedule(a.property, a.as_of, {"pet"}))
    elif a.cmd == "amenities":
        _table(q.amenities(a.property))
    elif a.cmd == "utilities":
        _table(q.utilities(a.property))
    elif a.cmd == "move-in":
        est = q.move_in_cost(a.property, a.unit_type, a.pets, a.as_of)
        for name, amount in est["items"]:
            print(f"  {name:45s} ${amount:>10,.0f}")
        print(f"  {'TOTAL':45s} ${est['total']:>10,.0f}")
    elif a.cmd == "sql":
        _table(q.sql(a.query))


if __name__ == "__main__":
    main()
