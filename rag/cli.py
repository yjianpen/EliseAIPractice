"""Command line for the RAG databases.

  python -m rag.cli build
  python -m rag.cli ask "there's no heat and it's freezing" --property P-NYC-001 --unit P-NYC-001-3B
  python -m rag.cli ask "can my landlord come in without notice?" --property P-SF-002 --json
  python -m rag.cli laws "mold in the bathroom" --city "San Francisco" --state CA
  python -m rag.cli properties
"""
from __future__ import annotations

import argparse
import json
from datetime import date

from . import build as build_mod
from .retrieve import _table, build_context, render_context, search_laws


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m rag.cli", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="(re)build data/rag/policies.db and laws.db")
    sub.add_parser("properties", help="list synthetic properties")
    a = sub.add_parser("ask", help="retrieve context for a resident message at a property")
    a.add_argument("question")
    a.add_argument("--property", required=True)
    a.add_argument("--unit")
    a.add_argument("--date", help="treat this as today (YYYY-MM-DD), e.g. to test heat season")
    a.add_argument("--json", action="store_true", help="print the raw context as JSON")
    l = sub.add_parser("laws", help="search laws for a jurisdiction")
    l.add_argument("query")
    l.add_argument("--city", required=True)
    l.add_argument("--state", required=True)
    l.add_argument("-k", type=int, default=5)
    args = ap.parse_args()

    if args.cmd == "build":
        build_mod.main()
    elif args.cmd == "properties":
        for p in _table("properties"):
            print(f"{p['property_id']:10s} {p['city']:14s} {p['name']:24s} built {p['year_built']}, {p['units']} units")
    elif args.cmd == "ask":
        today = date.fromisoformat(args.date) if args.date else None
        ctx = build_context(args.question, args.property, args.unit, today=today)
        print(json.dumps(ctx, indent=2, default=str) if args.json else render_context(ctx))
    elif args.cmd == "laws":
        for h in search_laws(args.query, args.city, args.state, k=args.k):
            print(f"{h.score:5.2f}  {h.meta['citation']} - {h.title}\n       {h.meta['source_url']}")


if __name__ == "__main__":
    main()
