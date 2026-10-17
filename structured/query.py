"""Read-only queries over data/structured/property_facts.db.

Every fee query takes an explicit `as_of` date, so expired offers (effective_to in the past) never leak
into an answer. `facts_for_topics` is what the agent calls: it maps taxonomy topics to the exact rows
the answer needs, already formatted for a prompt.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from .build import DB_PATH

FACT_TOPICS = {"rent_and_fees", "pets", "parking", "utilities", "amenities", "garbage", "leasing", "moving"}


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"{db_path.name} not found - run `python -m structured.build` first")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)  # read-only: ad-hoc SQL cannot modify data
    con.row_factory = sqlite3.Row
    return con


def _rows(sql: str, params: tuple = ()) -> list[dict]:
    con = connect()
    try:
        return [dict(r) for r in con.execute(sql, params)]
    finally:
        con.close()


def sql(query: str) -> list[dict]:
    """Run an ad-hoc read-only query (the connection is opened in read-only mode)."""
    return _rows(query)


def _iso(as_of: date | str | None) -> str:
    return (as_of if isinstance(as_of, str) else (as_of or date.today()).isoformat())


# ------------------------------------------------------------------------------------------- lookups
def fee_schedule(property_id: str, as_of=None, categories: set[str] | None = None,
                 codes: set[str] | None = None) -> list[dict]:
    rows = _rows("""SELECT * FROM fees WHERE property_id = ? AND effective_from <= ?
                    AND (effective_to IS NULL OR effective_to >= ?) ORDER BY category, fee_name""",
                 (property_id, _iso(as_of), _iso(as_of)))
    if categories:
        rows = [r for r in rows if r["category"] in categories]
    if codes:
        rows = [r for r in rows if r["fee_code"] in codes]
    return rows


def unit_types(property_id: str) -> list[dict]:
    return _rows("SELECT * FROM unit_types WHERE property_id = ? ORDER BY bedrooms", (property_id,))


def monthly_costs(property_id: str, as_of=None) -> list[dict]:
    """Advertised rent range plus required flat monthly charges, per unit type."""
    required = [f for f in fee_schedule(property_id, as_of) if f["frequency"] == "monthly" and f["required"]
                and f["basis"] == "flat"]
    extra = sum(f["amount"] for f in required)
    return [dict(unit_type=u["unit_type"], rent_min=u["rent_min"], rent_max=u["rent_max"],
                 required_monthly_fees=extra, total_min=u["rent_min"] + extra, total_max=u["rent_max"] + extra,
                 fees=[(f["fee_name"], f["amount"]) for f in required]) for u in unit_types(property_id)]


def move_in_cost(property_id: str, unit_type: str, pets: int = 0, as_of=None) -> dict:
    """Upper-bound move-in estimate: first month + security deposit + required one-time fees + pet one-time fees."""
    ut = next(u for u in unit_types(property_id) if u["unit_type"].lower() == unit_type.lower())
    fees = fee_schedule(property_id, as_of)
    rent = ut["rent_max"]
    deposit = sum(f["amount"] * rent if f["basis"] == "months_of_rent" else f["amount"]
                  for f in fees if f["category"] == "deposit" and f["fee_code"].startswith("security") and f["required"])
    one_time = [f for f in fees if f["frequency"] == "one_time" and f["required"] and not
                (f["category"] == "deposit" and f["fee_code"].startswith("security"))]
    pet_one_time = [f for f in fees if f["category"] == "pet" and f["frequency"] == "one_time"]
    items = [("First month's rent (top of range)", rent), ("Security deposit", deposit)]
    items += [(f["fee_name"], f["amount"]) for f in one_time]
    items += [(f"{f['fee_name']} x{pets}", f["amount"] * pets) for f in pet_one_time if pets]
    return dict(property_id=property_id, unit_type=ut["unit_type"], pets=pets, items=items,
                total=sum(a for _, a in items))


def pet_policy(property_id: str) -> dict:
    return _rows("SELECT * FROM pet_policies WHERE property_id = ?", (property_id,))[0]


def parking(property_id: str) -> list[dict]:
    return _rows("SELECT * FROM parking WHERE property_id = ?", (property_id,))


def utilities(property_id: str) -> list[dict]:
    return _rows("SELECT * FROM utilities WHERE property_id = ? ORDER BY utility", (property_id,))


def amenities(property_id: str) -> list[dict]:
    return _rows("SELECT * FROM amenities WHERE property_id = ? ORDER BY amenity_id", (property_id,))


def lease_for_unit(unit_id: str) -> dict | None:
    rows = _rows("SELECT * FROM leases WHERE unit_id = ? ORDER BY end_date DESC LIMIT 1", (unit_id,))
    return rows[0] if rows else None


# ------------------------------------------------------------------------------------------- for the agent
def _money(x: float) -> str:
    return f"${x:,.0f}" if float(x).is_integer() else f"${x:,.2f}"


def _fee_line(f: dict) -> str:
    if f["basis"] == "months_of_rent":
        amount = f"{f['amount']:g} month(s) of rent"
    else:
        amount = _money(f["amount"]) + (" per pet" if f["basis"] == "per_pet" else "")
    freq = {"one_time": "one-time", "monthly": "monthly", "per_occurrence": "each time"}[f["frequency"]]
    if f["category"] == "pet":
        applies = "pet owners only"
    elif f["category"] == "penalty":
        applies = "only if it applies"
    else:
        applies = "required for all residents" if f["required"] else "optional"
    flags = [applies] + (["refundable"] if f["refundable"] else [])
    note = f" - {f['notes']}" if f["notes"] else ""
    src = " [listing]" if f["provenance"] == "listing" else " [synthetic]"
    return f"{f['fee_name']}: {amount}, {freq} ({', '.join(flags)}){note}{src}"


def facts_for_topics(property_id: str, topics: list[str], unit_id: str | None = None, as_of=None) -> list[dict]:
    """Exact facts for the detected topics. Each fact: {kind, title, lines}."""
    wanted = set(topics) & FACT_TOPICS
    if not wanted:
        return []
    facts = []

    def add(kind, title, lines):
        if lines:
            facts.append(dict(kind=kind, title=title, lines=lines))

    if "rent_and_fees" in wanted or "leasing" in wanted:
        if unit_id and (lease := lease_for_unit(unit_id)):
            add("lease", "Your current lease", [
                f"Monthly rent {_money(lease['monthly_rent'])}; lease {lease['start_date']} to {lease['end_date']}; "
                f"type {lease['lease_type']}; deposit on file {_money(lease['security_deposit'])}"])
        add("rents", "Advertised rents and required monthly charges", [
            f"{c['unit_type']}: rent {_money(c['rent_min'])}-{_money(c['rent_max'])}; with required monthly "
            f"charges {_money(c['total_min'])}-{_money(c['total_max'])}" for c in monthly_costs(property_id, as_of)])
    if "rent_and_fees" in wanted:
        add("fees", "Fee schedule (in effect today)", [_fee_line(f) for f in fee_schedule(property_id, as_of)])
    if "pets" in wanted:
        pp = pet_policy(property_id)
        allowed = [k for k in ("cats", "dogs") if pp[f"{k}_allowed"]]
        add("pets", "Pet policy and pet charges", [
            f"Allowed: {', '.join(allowed) or 'none'}; max pets {pp['max_pets'] or 'n/a'}; max dog weight "
            f"{str(pp['max_weight_lb']) + ' lb' if pp['max_weight_lb'] else 'no limit'}; breed restrictions: "
            f"{pp['breed_restrictions'] or 'none listed'}; registration required: {bool(pp['registration_required'])}"]
            + [_fee_line(f) for f in fee_schedule(property_id, as_of, {"pet"})]
            + ([] if fee_schedule(property_id, as_of, {"pet"}) else ["No pet charges."]))
    if "parking" in wanted:
        add("parking", "Parking", [
            f"{p['parking_type']}; spaces {p['spaces'] or 'n/a'}; assigned {bool(p['assigned'])}; EV "
            f"{bool(p['ev_charging'])}; waitlist {bool(p['waitlist'])}" for p in parking(property_id)]
            + [_fee_line(f) for f in fee_schedule(property_id, as_of, {"parking"})])
    if wanted & {"utilities", "garbage"}:
        add("utilities", "Utilities (who pays) and utility charges", [
            f"{u['utility']}: {u['responsibility']}" + (f" ({u['provider']})" if u["provider"] else "")
            for u in utilities(property_id)] + [_fee_line(f) for f in fee_schedule(property_id, as_of, {"utility"})])
    if "amenities" in wanted:
        fees = {f["fee_id"]: f for f in fee_schedule(property_id, as_of)}
        add("amenities", "Amenities", [
            f"{a['amenity']}: hours {a['hours']}" + ("; reservation required" if a["reservation_required"] else "")
            + (f"; {_fee_line(fees[a['fee_id']])}" if a["fee_id"] in fees else "") for a in amenities(property_id)])
    if "moving" in wanted:
        add("fees", "Move-related charges", [_fee_line(f) for f in fee_schedule(property_id, as_of)
                                              if f["category"] in ("deposit", "application")])
    return facts
