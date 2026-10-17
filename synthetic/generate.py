"""Generate synthetic "source of truth" data for the property-management agent.

Everything here is fictional: companies, buildings, tenants and phone numbers
(555-01xx numbers, example.com addresses). The *shape* mirrors what a real
property-management system holds, and the work-order mix follows the NYC 311
housing complaints in data/processed/nyc_311.parquet.

Outputs (deterministic for a given --seed):
  data/synthetic/*.csv                         structured source of truth
  knowledge/policies/properties/<id>.md        per-property policy addenda (RAG input)

Usage:
  python -m synthetic.generate            # seed 311
  python -m synthetic.generate --seed 7
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "synthetic"
ADDENDA_DIR = ROOT / "knowledge" / "policies" / "properties"
TAXONOMY = json.loads((ROOT / "knowledge" / "taxonomy.json").read_text())["topics"]

AS_OF = date(2026, 10, 16)          # "today" for statuses and due dates
HISTORY_START = date(2025, 11, 1)   # work-order history window

# --------------------------------------------------------------------------
# Companies and properties (hand-written so each one exercises different rules)
# --------------------------------------------------------------------------
COMPANIES = [
    {"company_id": "C-LUMEN", "name": "Lumen Park Residential (synthetic)", "hq_city": "New York",
     "resident_portal": "https://portal.lumenpark.example.com", "emergency_line": "212-555-0100",
     "office_email": "residents@lumenpark.example.com"},
    {"company_id": "C-BAYLINE", "name": "Bayline Homes (synthetic)", "hq_city": "San Francisco",
     "resident_portal": "https://residents.bayline.example.com", "emergency_line": "415-555-0100",
     "office_email": "help@bayline.example.com"},
]

# Each property is chosen to trigger different legal regimes.
PROPERTIES = [
    # NYC, pre-1960 walk-up: Local Law 1 lead rules, boiler heat, window guards
    dict(property_id="P-NYC-001", company_id="C-LUMEN", name="Greenpoint Walk-up", city="New York", state="NY",
         district="Brooklyn", address="118 Oakfield St, Brooklyn, NY 11222", year_built=1928, units=24, floors=5,
         has_elevator=False, heat_system="central steam boiler (oil-to-gas conversion 2019)", heat_controlled_by="landlord",
         hot_water_system="boiler-fired indirect tank", laundry="none on site; laundromat at corner",
         quiet_hours="10:00 PM - 8:00 AM", trash_days="Mon, Thu (bags out after 8 PM the night before)",
         recycling_days="Thu", pets="cats allowed; dogs under 25 lb with addendum", smoking="no smoking in common areas",
         super_name="Marek Nowicki", super_phone="718-555-0111", office_hours="Mon-Fri 9 AM - 5 PM",
         rent_regulated=True),
    # NYC, 1985 elevator building, 120 units
    dict(property_id="P-NYC-002", company_id="C-LUMEN", name="Astoria Gardens", city="New York", state="NY",
         district="Queens", address="31-40 Linden Ave, Astoria, NY 11106", year_built=1985, units=120, floors=8,
         has_elevator=True, heat_system="central hot-water boiler with apartment thermostats", heat_controlled_by="landlord",
         hot_water_system="central gas water heaters", laundry="basement laundry room 7 AM - 10 PM",
         quiet_hours="10:00 PM - 7:00 AM", trash_days="Tue, Fri (compactor chute 8 AM - 9 PM)", recycling_days="Fri",
         pets="dogs and cats allowed with addendum, max 2", smoking="smoke-free building",
         super_name="Luis Ortega", super_phone="718-555-0122", office_hours="Mon-Sat 8 AM - 6 PM", rent_regulated=False),
    # NYC, new luxury tower
    dict(property_id="P-NYC-003", company_id="C-LUMEN", name="Hudson Yards Tower", city="New York", state="NY",
         district="Manhattan", address="455 W 35th St, New York, NY 10001", year_built=2015, units=200, floors=32,
         has_elevator=True, heat_system="in-unit heat pumps (PTAC), tenant thermostat", heat_controlled_by="tenant",
         hot_water_system="central high-efficiency boilers", laundry="in-unit washer/dryer",
         quiet_hours="11:00 PM - 7:00 AM", trash_days="daily chute; bulk items via concierge", recycling_days="daily chute",
         pets="dogs and cats allowed, pet spa on 3rd floor", smoking="smoke-free building",
         super_name="Priya Raman (resident manager)", super_phone="212-555-0133", office_hours="daily 8 AM - 8 PM",
         rent_regulated=False),
    # SF, 1925 Edwardian flats: pre-1978 federal lead disclosure, landlord heat (70F 24h rule)
    dict(property_id="P-SF-001", company_id="C-BAYLINE", name="Mission Dolores Flats", city="San Francisco", state="CA",
         district="Mission", address="2140 Valencia Ct, San Francisco, CA 94110", year_built=1925, units=12, floors=4,
         has_elevator=False, heat_system="central gas furnace, landlord-controlled", heat_controlled_by="landlord",
         hot_water_system="shared gas water heater", laundry="coin laundry in garage",
         quiet_hours="10:00 PM - 7:00 AM", trash_days="Wed (Recology: black, blue, green bins)", recycling_days="Wed",
         pets="cats only", smoking="no smoking anywhere on property",
         super_name="Dana Whitfield (on-site manager)", super_phone="415-555-0144", office_hours="Mon-Fri 10 AM - 4 PM",
         rent_regulated=True),
    # SF, 2010 mid-rise
    dict(property_id="P-SF-002", company_id="C-BAYLINE", name="SoMa Commons", city="San Francisco", state="CA",
         district="SoMa", address="88 Harriet Way, San Francisco, CA 94103", year_built=2010, units=150, floors=9,
         has_elevator=True, heat_system="in-unit electric wall heaters, tenant thermostat", heat_controlled_by="tenant",
         hot_water_system="central boilers", laundry="in-unit washer/dryer",
         quiet_hours="10:00 PM - 8:00 AM", trash_days="trash room daily; Recology pickup Mon/Thu", recycling_days="Mon/Thu",
         pets="dogs and cats allowed with addendum", smoking="smoke-free building",
         super_name="Jordan Lee (community manager)", super_phone="415-555-0155", office_hours="daily 9 AM - 6 PM",
         rent_regulated=False),
    # SF, 1952 Sunset 6-unit (Lumen also operates in SF -> one company, two cities)
    dict(property_id="P-SF-003", company_id="C-LUMEN", name="Sunset Terrace", city="San Francisco", state="CA",
         district="Outer Sunset", address="1530 Noriega Pl, San Francisco, CA 94122", year_built=1952, units=6, floors=2,
         has_elevator=False, heat_system="individual gas wall furnaces, tenant-controlled", heat_controlled_by="tenant",
         hot_water_system="individual tank water heaters", laundry="shared washer/dryer in garage",
         quiet_hours="10:00 PM - 7:00 AM", trash_days="Tue (Recology)", recycling_days="Tue",
         pets="no pets except service/assistance animals", smoking="no smoking anywhere on property",
         super_name="Lumen SF maintenance desk", super_phone="415-555-0166", office_hours="Mon-Fri 9 AM - 5 PM",
         rent_regulated=True),
]

FIRST = ["Ava", "Mateo", "Sofia", "Liam", "Mei", "Noah", "Aaliyah", "Diego", "Hana", "Omar", "Grace", "Wei",
         "Isabella", "Kwame", "Lucia", "Ethan", "Zara", "Ravi", "Chloe", "Yusuf", "Elena", "Jin", "Maya", "Tomas"]
LAST = ["Garcia", "Chen", "Kowalski", "Okafor", "Nguyen", "Rossi", "Patel", "Kim", "Haddad", "Silva", "Cohen",
        "Murphy", "Tanaka", "Diallo", "Ivanova", "Lopez", "Brennan", "Singh", "Moreau", "Park", "Novak", "Ali"]
LANGS = ["English"] * 7 + ["Spanish"] * 2 + ["Mandarin", "Cantonese", "Russian", "Polish", "Bengali"]

VENDOR_TRADES = {
    "plumber": ["plumbing", "water_leak", "water_supply"],
    "electrician": ["electrical", "intercom"],
    "exterminator": ["pests", "bedbugs"],
    "boiler_hvac": ["heat", "hot_water"],
    "gas_utility_contractor": ["gas"],
    "elevator_contractor": ["elevator"],
    "mold_remediation": ["mold"],
    "lead_abatement": ["lead", "paint_plaster"],
    "general_handyman": ["paint_plaster", "doors_windows", "flooring_stairs", "window_guards", "smoke_co_alarms",
                          "garbage", "snow_ice"],
    "appliance_repair": ["appliances"],
}

# Work-order mix: topic weights follow HPD 311 volumes (Dec 2025 - Sep 2026).
TOPIC_WEIGHTS = {
    "heat": 96, "hot_water": 52, "pests": 54, "mold": 30, "plumbing": 40, "water_supply": 23,
    "water_leak": 36, "paint_plaster": 51, "doors_windows": 40, "intercom": 9, "gas": 6, "electrical": 27,
    "flooring_stairs": 23, "appliances": 20, "smoke_co_alarms": 6, "window_guards": 2, "elevator": 2,
    "garbage": 17, "noise": 25, "bedbugs": 4, "snow_ice": 5,
}
HEAT_SEASON_TOPICS = {"heat"}

STATUS_FLOW = ["submitted", "scheduled", "in_progress", "completed"]


@dataclass
class Store:
    companies: list = field(default_factory=list)
    properties: list = field(default_factory=list)
    units: list = field(default_factory=list)
    tenants: list = field(default_factory=list)
    leases: list = field(default_factory=list)
    vendors: list = field(default_factory=list)
    work_orders: list = field(default_factory=list)
    compliance: list = field(default_factory=list)


def in_heat_season(d: date, city: str) -> bool:
    # NYC heat season Oct 1 - May 31. SF has no season (requirement is year-round where landlord controls heat).
    return d.month >= 10 or d.month <= 5 if city == "New York" else True


def phone(rng: random.Random, area: str) -> str:
    return f"{area}-555-01{rng.randint(10, 99)}"


def gen_units_tenants_leases(rng: random.Random, s: Store) -> None:
    for p in s.properties:
        area = "718" if p["district"] in ("Brooklyn", "Queens") else "212" if p["city"] == "New York" else "415"
        per_floor = max(1, p["units"] // p["floors"])
        for i in range(p["units"]):
            floor = min(p["floors"], i // per_floor + 1)
            letter = "ABCDEFGHJKLMNP"[i % per_floor] if per_floor <= 14 else f"{i % per_floor + 1:02d}"
            unit_id = f"{p['property_id']}-{floor}{letter}"
            beds = rng.choices([0, 1, 2, 3], weights=[2, 5, 4, 1])[0]
            occupied = rng.random() > 0.05
            child_u6 = occupied and rng.random() < 0.12
            child_u11 = child_u6 or (occupied and rng.random() < 0.08)
            s.units.append(dict(unit_id=unit_id, property_id=p["property_id"], unit_number=f"{floor}{letter}",
                                floor=floor, bedrooms=beds, bathrooms=1 if beds < 3 else 2,
                                sqft=rng.randint(380, 520) + beds * rng.randint(220, 320),
                                status="occupied" if occupied else "vacant",
                                child_under_6_reported=child_u6, child_10_or_under_reported=child_u11))
            if not occupied:
                continue
            tid = f"T-{len(s.tenants) + 1:05d}"
            fn, ln = rng.choice(FIRST), rng.choice(LAST)
            s.tenants.append(dict(tenant_id=tid, unit_id=unit_id, first_name=fn, last_name=ln,
                                  email=f"{fn.lower()}.{ln.lower()}{rng.randint(1, 99)}@example.com",
                                  phone=phone(rng, area), preferred_language=rng.choice(LANGS),
                                  preferred_channel=rng.choice(["sms", "email", "phone", "portal"])))
            start = AS_OF - timedelta(days=rng.randint(30, 900))
            months = 12 if rng.random() < 0.85 else 24
            end = start + timedelta(days=30 * months)
            if end < AS_OF:  # renewed
                start, end = end, end + timedelta(days=365)
            base = {"Brooklyn": 2900, "Queens": 2500, "Manhattan": 4800, "Mission": 3300, "SoMa": 3600,
                    "Outer Sunset": 2800}[p["district"]]
            rent = round((base + beds * rng.randint(700, 1100)) * (0.72 if p["rent_regulated"] else 1.0), -1)
            s.leases.append(dict(lease_id=f"L-{len(s.leases) + 1:05d}", unit_id=unit_id, tenant_id=tid,
                                 start_date=start.isoformat(), end_date=end.isoformat(), monthly_rent=int(rent),
                                 security_deposit=int(rent), lease_type="rent stabilized" if p["rent_regulated"]
                                 and p["city"] == "New York" else "rent controlled" if p["rent_regulated"] else "market",
                                 pet_addendum=rng.random() < 0.3, renters_insurance_required=p["units"] >= 100))


def gen_vendors(rng: random.Random, s: Store) -> None:
    for c in s.companies:
        cities = sorted({p["city"] for p in s.properties if p["company_id"] == c["company_id"]})
        for city in cities:
            area = "212" if city == "New York" else "415"
            for trade in VENDOR_TRADES:
                s.vendors.append(dict(vendor_id=f"V-{len(s.vendors) + 1:03d}", company_id=c["company_id"], city=city,
                                      trade=trade, name=f"{city.split()[0]} {trade.replace('_', ' ').title()} Co. (synthetic)",
                                      phone=phone(rng, area),
                                      emergency_24h=trade in ("plumber", "boiler_hvac", "gas_utility_contractor",
                                                              "elevator_contractor", "electrician"),
                                      licensed=trade in ("exterminator", "mold_remediation", "lead_abatement",
                                                         "electrician", "plumber", "gas_utility_contractor")))


def pick_311_pair(rng: random.Random, topic: str) -> tuple[str, str]:
    pairs = TAXONOMY[topic]["nyc_311"]
    return tuple(rng.choice(pairs)) if pairs else ("(none)", topic.upper())


def gen_work_orders(rng: random.Random, s: Store) -> None:
    occupied = [u for u in s.units if u["status"] == "occupied"]
    tenant_by_unit = {t["unit_id"]: t for t in s.tenants}
    prop = {p["property_id"]: p for p in s.properties}
    topics, weights = zip(*TOPIC_WEIGHTS.items())
    span = (AS_OF - HISTORY_START).days
    target = 1600
    while len(s.work_orders) < target:
        u = rng.choice(occupied)
        p = prop[u["property_id"]]
        topic = rng.choices(topics, weights=weights)[0]
        if topic == "elevator" and not p["has_elevator"]:
            continue
        if topic == "window_guards" and p["city"] != "New York":
            continue
        if topic == "snow_ice" and p["city"] != "New York":
            continue
        created = datetime.combine(HISTORY_START + timedelta(days=rng.randint(0, span)), datetime.min.time()) \
            + timedelta(minutes=rng.randint(0, 1439))
        if topic in HEAT_SEASON_TOPICS and not in_heat_season(created.date(), p["city"]):
            continue
        urgency = TAXONOMY[topic]["urgency"]
        problem, detail = pick_311_pair(rng, topic)
        # resolution time by urgency (hours), long tail
        hrs = {"emergency": rng.expovariate(1 / 14), "urgent": rng.expovariate(1 / 60),
               "routine": rng.expovariate(1 / 180), "city": 0}[urgency]
        closed = created + timedelta(hours=hrs + 0.5)
        age_days = (datetime.combine(AS_OF, datetime.min.time()) - created).days
        if closed.date() >= AS_OF or (age_days < 21 and rng.random() < 0.35):
            status = rng.choice(STATUS_FLOW[:3])
            closed_at = ""
        else:
            status, closed_at = "completed", closed.isoformat(timespec="minutes")
        trade = next(t for t, tops in VENDOR_TRADES.items() if topic in tops) if topic != "noise" else None
        vendor = next((v["vendor_id"] for v in s.vendors if v["company_id"] == p["company_id"]
                       and v["city"] == p["city"] and v["trade"] == trade), "")
        scheduled = "" if status == "submitted" else (created + timedelta(hours=min(hrs, 72) / 2 + 1)).isoformat(
            timespec="minutes")
        s.work_orders.append(dict(
            work_order_id=f"WO-{len(s.work_orders) + 1:05d}", property_id=p["property_id"], unit_id=u["unit_id"],
            tenant_id=tenant_by_unit[u["unit_id"]]["tenant_id"], created_at=created.isoformat(timespec="minutes"),
            topic=topic, category=TAXONOMY[topic]["category"], nyc311_problem=problem, nyc311_detail=detail,
            urgency=urgency, status=status, assigned_vendor_id=vendor if topic != "noise" else "",
            handled_by="property management (lease enforcement)" if topic == "noise" else "maintenance",
            scheduled_for=scheduled, closed_at=closed_at,
            entry_permission="tenant consented" if rng.random() < 0.6 else "notice served"))
    s.work_orders.sort(key=lambda w: w["created_at"])
    for i, w in enumerate(s.work_orders, 1):
        w["work_order_id"] = f"WO-{i:05d}"


def gen_compliance(rng: random.Random, s: Store) -> None:
    """Recurring legal obligations per property. 'law_id' links to knowledge/laws records."""
    def add(p, requirement, law_id, last, every_days, notes=""):
        nxt = last + timedelta(days=every_days)
        status = "overdue" if nxt < AS_OF else "due_soon" if (nxt - AS_OF).days <= 45 else "ok"
        s.compliance.append(dict(record_id=f"CR-{len(s.compliance) + 1:04d}", property_id=p["property_id"],
                                 requirement=requirement, law_id=law_id, last_completed=last.isoformat(),
                                 next_due=nxt.isoformat(), status=status, notes=notes))

    for p in s.properties:
        jitter = lambda base: base - timedelta(days=rng.randint(0, 40))
        if p["city"] == "New York":
            if p["year_built"] < 1960:
                add(p, "Local Law 1 annual notice (child under 6 inquiry)", "nyc-lead-ll1", jitter(date(2026, 1, 15)), 365,
                    "Notices go out Jan 1-16; follow up by Feb 15 if no response")
                add(p, "Local Law 1 annual visual lead inspection (units with child under 6)", "nyc-lead-ll1",
                    jitter(date(2026, 3, 1)), 365)
            add(p, "Local Law 55 annual inspection for pests and mold", "nyc-allergens-ll55", jitter(date(2026, 4, 1)), 365)
            add(p, "Bedbug annual report to HPD (file Dec 1-31)", "nyc-bedbug-ll69", date(2025, 12, 12), 365)
            add(p, "Window guard annual notice", "nyc-window-guards", jitter(date(2026, 1, 15)), 365)
            add(p, "Boiler inspection (DOB)", "nyc-heat", jitter(date(2026, 9, 1)), 365)
            add(p, "Smoke and CO alarm notice/check at turnover", "nyc-smoke-co-alarms", jitter(date(2026, 6, 1)), 365)
            if p["has_elevator"]:
                add(p, "Elevator periodic inspection", "", jitter(date(2026, 5, 1)), 365)
        else:
            add(p, "Bed bug information notice to new tenants (Civ. Code 1954.603)", "ca-bedbug-notice",
                jitter(date(2026, 2, 1)), 365, "Give at every new tenancy; tracked annually for audit")
            add(p, "Smoke and CO alarm check", "ca-smoke-co-alarms", jitter(date(2026, 3, 1)), 365)
            if p["year_built"] < 1978:
                add(p, "Lead-based paint disclosure + EPA pamphlet at lease signing", "us-lead-disclosure",
                    jitter(date(2026, 1, 1)), 365)
            if p["heat_controlled_by"] == "landlord":
                add(p, "Heating system service (70F capability check)", "sf-heat", jitter(date(2025, 11, 1)), 365)
            if p["has_elevator"]:
                add(p, "Elevator annual inspection", "", jitter(date(2026, 4, 1)), 365)


# --------------------------------------------------------------------------
# Property addenda: the property-specific layer of the policy RAG corpus
# --------------------------------------------------------------------------
def addendum_md(p: dict, company: dict) -> str:
    nyc = p["city"] == "New York"
    lines = [
        "---",
        f"doc_id: addendum-{p['property_id'].lower()}",
        "scope: property",
        f"company_id: {p['company_id']}",
        f"property_id: {p['property_id']}",
        f"city: {p['city']}",
        f"state: {p['state']}",
        f"title: {p['name']} - Property Addendum",
        "version: 2026-10 (synthetic)",
        "---",
        f"# {p['name']} - Property Addendum",
        "",
        f"This addendum applies only to {p['name']} ({p['address']}). Where it differs from the "
        f"{company['name']} Resident Guidebook, this addendum controls.",
        "",
        "## Building contacts and emergencies",
        "<!-- topics: gas, water_leak, electrical, elevator, heat, repairs_timeline -->",
        f"On-site contact: {p['super_name']}, {p['super_phone']}. Office hours: {p['office_hours']}. "
        f"After hours, call the {company['name']} emergency line at {company['emergency_line']}. "
        "If you smell gas, leave the building first and call 911 from outside, then the gas utility.",
        "",
        "## Heat and hot water at this building",
        "<!-- topics: heat, hot_water -->",
    ]
    if p["heat_controlled_by"] == "landlord":
        rule = ("from October 1 to May 31 the building keeps apartments at least 68F from 6 AM to 10 PM when it is "
                "below 55F outside, and at least 62F overnight" if nyc else
                "the building heating system keeps every habitable room able to reach 70F at all times")
        lines.append(f"Heat comes from a {p['heat_system']} that management controls; {rule}. "
                     f"Hot water is supplied by a {p['hot_water_system']}. If your apartment is below these levels, "
                     "report it right away as an emergency work order and note the room temperature and time.")
    else:
        lines.append(f"Your apartment has {p['heat_system']}. You control the thermostat, so first check that it is "
                     "on, set above room temperature, and that the breaker has not tripped. If the equipment itself "
                     f"does not produce heat, submit an urgent work order. Hot water comes from {p['hot_water_system']}.")
    lines += ["", "## Quiet hours and noise", "<!-- topics: noise -->",
              f"Quiet hours at {p['name']} are {p['quiet_hours']}. Report repeated noise from another apartment "
              "through the portal with dates and times; management follows up with the other household under the "
              "lease. For noise happening right now that feels unsafe, contact local police.", "",
              "## Trash, recycling and compost", "<!-- topics: garbage, pests -->",
              f"Trash: {p['trash_days']}. Recycling: {p['recycling_days']}. Bag all food waste; "
              "loose garbage in common areas attracts pests.", "",
              "## Laundry", "<!-- topics: appliances -->", f"{p['laundry'].capitalize()}.", "",
              "## Pets and smoking", "<!-- topics: noise -->",
              f"Pets: {p['pets']}. Smoking: {p['smoking']}."]
    if p["has_elevator"]:
        lines += ["", "## Elevator", "<!-- topics: elevator -->",
                  "If the elevator is out of service, report it immediately. Residents with mobility needs can ask the "
                  "office for assistance with groceries and packages until service is restored. If someone is "
                  "trapped, call 911 first."]
    if nyc and p["year_built"] < 1960:
        lines += ["", "## Lead paint (building built before 1960)", "<!-- topics: lead, paint_plaster -->",
                  f"{p['name']} was built in {p['year_built']}, so NYC Local Law 1 applies. Each January we send a "
                  "notice asking whether a child under 6 lives in or regularly spends 10+ hours a week in your "
                  "apartment; please return it. Report peeling or chipping paint immediately. Lead work is done "
                  "only by certified workers using safe work practices."]
    if not nyc and p["year_built"] < 1978:
        lines += ["", "## Lead paint disclosure (built before 1978)", "<!-- topics: lead, paint_plaster -->",
                  f"{p['name']} was built in {p['year_built']}. Your lease package includes the federal lead "
                  "disclosure form and the EPA lead pamphlet. Report peeling or chipping paint right away; do not "
                  "sand or scrape it yourself."]
    if nyc:
        lines += ["", "## Window guards", "<!-- topics: window_guards -->",
                  "If a child 10 or under lives in your apartment, or you simply want them, tell the office and we "
                  "install approved window guards at no charge. Do not remove guards yourself."]
    if p["rent_regulated"]:
        lines += ["", "## Rent regulation", "<!-- topics: retaliation, repairs_timeline -->",
                  ("Most apartments here are rent stabilized. Rent increases on renewal follow the NYC Rent "
                   "Guidelines Board orders. Questions about your rent history go to the office in writing."
                   if nyc else
                   "This building is covered by the San Francisco Rent Ordinance. Allowable annual increases are set "
                   "by the SF Rent Board. Questions about your rent go to the office in writing.")]
    return "\n".join(lines) + "\n"


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=311)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    s = Store(companies=COMPANIES, properties=[dict(p) for p in PROPERTIES])
    gen_units_tenants_leases(rng, s)
    gen_vendors(rng, s)
    gen_work_orders(rng, s)
    gen_compliance(rng, s)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ADDENDA_DIR.mkdir(parents=True, exist_ok=True)
    for name, rows in asdict(s).items():
        write_csv(OUT_DIR / f"{name}.csv", rows)
        print(f"{name:12s} {len(rows):5d} rows -> {(OUT_DIR / f'{name}.csv').relative_to(ROOT)}")
    company = {c["company_id"]: c for c in s.companies}
    for p in s.properties:
        out = ADDENDA_DIR / f"{p['property_id']}.md"
        out.write_text(addendum_md(p, company[p["company_id"]]))
    print(f"addenda      {len(s.properties):5d} files -> {ADDENDA_DIR.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
