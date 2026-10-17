"""Property-aware retrieval over the policy and law databases.

The agent always answers *for a specific property*. That property decides:
  - which company guidebook applies, and which of its city-specific sections
  - which property addendum applies (and overrides the guidebook)
  - which laws apply: federal + the property's state + the property's city

Ranking = BM25 text relevance (normalized) + topic overlap with the taxonomy
+ a precedence bonus (property addendum > company guidebook; city law > state > federal).
Results that match only by topic are still returned, so "radiator is cold" finds
the heat sections even though the word "heat" never appears.

Topic gate: when the message maps to taxonomy topics, only records tagged with one
of those topics qualify (BM25 then orders them). Without detected topics, plain
BM25 is used. This keeps a mold question from surfacing the heat law just because
both mention "bathroom".
"""
from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

from structured.query import facts_for_topics

from .common import (LAWS_DB, POLICIES_DB, SYNTHETIC_DIR, URGENCY_RANK, detect_topics, fts_query, max_urgency,
                     taxonomy)

TOPIC_WEIGHT = 1.0
SECONDARY_TOPIC_WEIGHT = 0.5
LEXICAL_WEIGHT_WITH_TOPICS = 0.5
POLICY_SCOPE_BONUS = {"property": 0.3, "company": 0.0}
LAW_LEVEL_BONUS = {"city": 0.2, "state": 0.1, "federal": 0.0}


# --------------------------------------------------------------------------- source of truth
@lru_cache(maxsize=None)
def _table(name: str) -> tuple[dict, ...]:
    with (SYNTHETIC_DIR / f"{name}.csv").open() as f:
        return tuple(csv.DictReader(f))


def get_property(property_id: str) -> dict:
    for p in _table("properties"):
        if p["property_id"] == property_id:
            company = next(c for c in _table("companies") if c["company_id"] == p["company_id"])
            return {**p, "company": company}
    raise KeyError(f"unknown property_id {property_id!r}; see data/synthetic/properties.csv")


def get_unit(unit_id: str) -> dict:
    for u in _table("units"):
        if u["unit_id"] == unit_id:
            return u
    raise KeyError(f"unknown unit_id {unit_id!r}")


def open_work_orders(unit_id: str, topics: list[str] | None = None) -> list[dict]:
    rows = [w for w in _table("work_orders") if w["unit_id"] == unit_id and w["status"] != "completed"]
    if topics:
        rows = [w for w in rows if w["topic"] in topics]
    return rows


def compliance_records(property_id: str, law_ids: set[str]) -> list[dict]:
    return [c for c in _table("compliance") if c["property_id"] == property_id and c["law_id"] in law_ids]


# --------------------------------------------------------------------------- search
@dataclass
class Hit:
    id: str
    score: float
    title: str
    text: str
    topics: list[str]
    meta: dict = field(default_factory=dict)


def _connect(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"{path.name} not found - run `python -m rag.build` first")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _term_support(query: str, heading: str, body: str) -> bool:
    """Lexical-only evidence check: a query word in the heading, or 2+ distinct query words in the body."""
    terms = [t.strip('"') for t in fts_query(query).split(" OR ") if t]
    heading, body = heading.lower(), body.lower()
    if any(t in heading for t in terms):
        return True
    return sum(t in body for t in terms) >= 2


def _rank(rows: list[sqlite3.Row], lexical: dict[str, float], topics: list[str], id_col: str, bonus,
          query: str, heading_col: str, body_col: str, scope_order) -> list[tuple]:
    top = max(lexical.values(), default=0.0) or 1.0
    hits = []
    for r in rows:
        rtopics = r["topics"].split()
        # a record's first topic is its main subject; later topics are incidental mentions
        overlap = sum(1.0 if i == 0 else SECONDARY_TOPIC_WEIGHT for i, t in enumerate(rtopics) if t in topics)
        lex = lexical.get(r[id_col], 0.0) / top
        if topics and overlap == 0:
            continue  # topic gate
        if not topics and (lex == 0 or not _term_support(query, r[heading_col], r[body_col])):
            continue  # no topic detected: require real lexical evidence
        lex_weight = LEXICAL_WEIGHT_WITH_TOPICS if topics else 1.0  # topic already gated; words only reorder
        hits.append((lex_weight * lex + TOPIC_WEIGHT * overlap + bonus(r), r, rtopics))
    hits.sort(key=lambda h: (-h[0], scope_order(h[1])))  # ties: more specific source first
    return hits


def search_policies(query: str, property_id: str, k: int = 5, topics: list[str] | None = None,
                    today: date | None = None) -> list[Hit]:
    """Guidebook, addendum and building-guide sections that apply to this property on `today`, best first."""
    prop = get_property(property_id)
    topics = topics if topics is not None else detect_topics(query)
    scope_sql = """((scope = 'property' AND property_id = :pid)
                    OR (scope = 'company' AND company_id = :cid
                        AND (cities = 'all' OR ',' || cities || ',' LIKE '%,' || :city || ',%')))
                   AND (valid_from IS NULL OR valid_from <= :today)
                   AND (valid_until IS NULL OR valid_until >= :today)"""
    params = {"pid": property_id, "cid": prop["company_id"], "city": prop["city"],
              "today": (today or date.today()).isoformat()}
    con = _connect(POLICIES_DB)
    rows = con.execute(f"SELECT * FROM chunks WHERE {scope_sql}", params).fetchall()
    lexical = {}
    q = fts_query(query)
    if q:
        for r in con.execute(f"""SELECT c.chunk_id, -bm25(chunks_fts, 0, 2.0, 1.0, 1.0) AS rel
                                 FROM chunks_fts JOIN chunks c USING (chunk_id)
                                 WHERE chunks_fts MATCH :q AND ({scope_sql})""", {**params, "q": q}):
            lexical[r["chunk_id"]] = max(r["rel"], 0.0)
    con.close()
    ranked = _rank(rows, lexical, topics, "chunk_id", lambda r: POLICY_SCOPE_BONUS[r["scope"]],
                   query, "section", "text", lambda r: r["scope"] != "property")
    return [Hit(id=r["chunk_id"], score=round(s, 3), title=f"{r['doc_title']} > {r['section']}", text=r["text"],
                topics=t, meta={"scope": r["scope"], "doc_id": r["doc_id"], "doc_type": r["doc_type"],
                                "valid_until": r["valid_until"], "version": r["version"],
                                "source_path": r["source_path"]})
            for s, r, t in ranked[:k]]


def search_laws(query: str, city: str, state: str, k: int = 5, topics: list[str] | None = None) -> list[Hit]:
    """Laws in force for a city: federal + state + city records only."""
    topics = topics if topics is not None else detect_topics(query)
    juris_sql = """level = 'federal' OR (level = 'state' AND state = :state)
                   OR (level = 'city' AND city = :city AND state = :state)"""
    params = {"city": city, "state": state}
    con = _connect(LAWS_DB)
    rows = con.execute(f"SELECT * FROM laws WHERE {juris_sql}", params).fetchall()
    lexical = {}
    q = fts_query(query)
    if q:
        for r in con.execute(f"""SELECT l.law_id, -bm25(laws_fts, 0, 2.0, 1.0, 1.0, 0.5, 1.0) AS rel
                                 FROM laws_fts JOIN laws l USING (law_id)
                                 WHERE laws_fts MATCH :q AND ({juris_sql})""", {**params, "q": q}):
            lexical[r["law_id"]] = max(r["rel"], 0.0)
    con.close()
    ranked = _rank(rows, lexical, topics, "law_id", lambda r: LAW_LEVEL_BONUS[r["level"]],
                   query, "title", "summary", lambda r: ["city", "state", "federal"].index(r["level"]))
    return [Hit(id=r["law_id"], score=round(s, 3), title=r["title"], text=r["summary"], topics=t,
                meta={"citation": r["citation"], "level": r["level"], "jurisdiction": r["city"] or r["state"] or "US",
                      "key_points": json.loads(r["key_points"]), "source_url": r["source_url"],
                      "verified_on": r["verified_on"], "verification_note": r["verification_note"]})
            for s, r, t in ranked[:k]]


# --------------------------------------------------------------------------- context for the agent
ESCALATION_TEXT = {
    "emergency": "Treat as an emergency: give the emergency line, safety steps first (gas/CO: leave and call 911), "
                 "and create an emergency work order now.",
    "urgent": "Create an urgent work order and confirm the scheduling window.",
    "routine": "Create a routine work order or answer from policy.",
    "city": "Not a landlord responsibility; point the resident to the city (311).",
}


def heat_season_note(city: str, today: date) -> str | None:
    if city == "New York":
        on = today.month >= 10 or today.month <= 5
        return f"NYC heat season is {'IN effect' if on else 'NOT in effect'} today ({today.isoformat()}; Oct 1 - May 31)."
    if city == "San Francisco":
        return "San Francisco has no heat season: the 70F requirement applies year-round where the landlord controls heat."
    return None


def build_context(question: str, property_id: str, unit_id: str | None = None, k_policies: int = 4,
                  k_laws: int = 4, today: date | None = None) -> dict:
    """Everything the agent needs to answer one resident message, with citation labels."""
    today = today or date.today()
    prop = get_property(property_id)
    topics = detect_topics(question)
    urgency = max_urgency(topics)
    policies = search_policies(question, property_id, k=k_policies, topics=topics, today=today)
    laws = search_laws(question, prop["city"], prop["state"], k=k_laws, topics=topics)
    ctx = {
        "question": question,
        "property": {k: v for k, v in prop.items() if k != "company"},
        "company": prop["company"],
        "unit": get_unit(unit_id) if unit_id else None,
        "topics": topics,
        "urgency": urgency,
        "escalation": ESCALATION_TEXT.get(urgency) if urgency else None,
        "notes": [],
        "open_work_orders": open_work_orders(unit_id, topics) if unit_id else [],
        "policies": [dict(label=f"P{i}", **vars(h)) for i, h in enumerate(policies, 1)],
        "laws": [dict(label=f"L{i}", **vars(h)) for i, h in enumerate(laws, 1)],
        "compliance": compliance_records(property_id, {h.id for h in laws}),
        # exact numbers come from the structured database, never from prose
        "facts": [dict(label=f"F{i}", **f) for i, f in enumerate(
            facts_for_topics(property_id, topics, unit_id, as_of=today), 1)],
    }
    if "heat" in topics:
        note = heat_season_note(prop["city"], today)
        if note:
            ctx["notes"].append(note)
        if prop["heat_controlled_by"] == "tenant":
            ctx["notes"].append("Heat at this property is tenant-controlled equipment: troubleshoot thermostat/breaker, "
                                "then treat as an urgent equipment repair.")
    if any(t in topics for t in ("lead", "window_guards")) and ctx["unit"]:
        u = ctx["unit"]
        ctx["notes"].append(f"Unit records: child under 6 reported={u['child_under_6_reported']}, "
                            f"child 10 or under reported={u['child_10_or_under_reported']}.")
    if urgency and URGENCY_RANK[urgency] >= URGENCY_RANK["urgent"] and not ctx["open_work_orders"] and unit_id:
        ctx["notes"].append("No open work order for this issue yet - create one.")
    return ctx


def render_context(ctx: dict) -> str:
    """Plain-text block to put in an LLM prompt. Policies are [P#], laws are [L#]."""
    p, c = ctx["property"], ctx["company"]
    out = [f"PROPERTY: {p['name']} ({p['property_id']}), {p['address']} | company: {c['name']}",
           f"Built {p['year_built']}, {p['units']} units, elevator={p['has_elevator']}, heat: {p['heat_system']} "
           f"(controlled by {p['heat_controlled_by']}) | on-site: {p['site_contact']} {p['site_phone']} | "
           f"emergency line: {p['emergency_line']}",
           "DATA NOTE: operator and building are real; operating details, contacts, phone numbers and policies are "
           f"synthetic practice data (building facts verified {p['verified_on']})."]
    if ctx["unit"]:
        out.append(f"UNIT: {ctx['unit']['unit_id']}")
    out.append(f"TOPICS: {', '.join(ctx['topics']) or '(none detected)'} | URGENCY: {ctx['urgency'] or 'n/a'}")
    if ctx["escalation"]:
        out.append(f"ESCALATION: {ctx['escalation']}")
    out += [f"NOTE: {n}" for n in ctx["notes"]]
    for w in ctx["open_work_orders"]:
        out.append(f"OPEN WORK ORDER {w['work_order_id']}: {w['topic']} ({w['urgency']}), status={w['status']}, "
                   f"scheduled_for={w['scheduled_for'] or 'not yet'}")
    if ctx["facts"]:
        out.append("\nFACTS (exact values from the property database; quote numbers only from here):")
        for f in ctx["facts"]:
            out.append(f"[{f['label']}] {f['title']}")
            out += [f"  - {line}" for line in f["lines"]]
    out.append("\nPOLICIES (property addendum overrides company guidebook; addendum sections listed first):")
    for h in sorted(ctx["policies"], key=lambda h: h["meta"]["scope"] != "property"):
        out.append(f"[{h['label']}] {h['title']} ({h['meta']['scope']})\n{h['text']}")
    out.append("\nLAWS (cite by citation and link):")
    for h in ctx["laws"]:
        flag = "" if h["meta"]["verified_on"] else " [unverified summary]"
        out.append(f"[{h['label']}] {h['meta']['citation']} - {h['title']}{flag}\n{h['text']}\nSource: "
                   f"{h['meta']['source_url']}")
    for c_ in ctx["compliance"]:
        out.append(f"COMPLIANCE {c_['requirement']}: last {c_['last_completed']}, next due {c_['next_due']} "
                   f"({c_['status']})")
    return "\n".join(out)
