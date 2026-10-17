"""Turn synthetic/profiles.py into structured CSVs and prose building guides.

  data/synthetic/unit_types.csv, fees.csv, pet_policies.csv, parking.csv, utilities.csv, amenities.csv
  knowledge/buildings/<property_id>.md   (RAG input; no dollar amounts by design)
"""
from __future__ import annotations

from pathlib import Path

from .profiles import LISTING_SOURCES, OBSERVED_ON, PROFILES

UTILITY_WORDS = {
    "included": "included in rent",
    "tenant_direct": "set up and paid by you directly",
    "billed_back": "billed by management on your monthly statement",
}


def _source(pid: str, provenance: str) -> str:
    return LISTING_SOURCES[pid] if provenance == "listing" else ""


def structured_rows(properties: list[dict]) -> dict[str, list[dict]]:
    out = {k: [] for k in ("unit_types", "fees", "pet_policies", "parking", "utilities", "amenities")}
    for p in properties:
        pid = p["property_id"]
        prof = PROFILES[pid]
        for ut, beds, baths, smin, smax, rmin, rmax, prov in prof["unit_types"]:
            out["unit_types"].append(dict(
                property_id=pid, unit_type=ut, bedrooms=beds, bathrooms=baths, sqft_min=smin, sqft_max=smax,
                rent_min=rmin, rent_max=rmax, provenance=prov, source_url=_source(pid, prov), observed_on=OBSERVED_ON))
        for f in prof["fees"]:
            out["fees"].append(dict(
                fee_id=f"{pid}:{f['fee_code']}", property_id=pid, **{k: v for k, v in f.items()},
                source_url=_source(pid, f["provenance"]), observed_on=OBSERVED_ON))
        pets = prof["pets"]
        out["pet_policies"].append(dict(property_id=pid, **pets, source_url=_source(pid, pets["provenance"]),
                                        observed_on=OBSERVED_ON))
        for i, pk in enumerate(prof["parking"], 1):
            out["parking"].append(dict(parking_id=f"{pid}:parking{i}", property_id=pid, **pk,
                                       source_url=_source(pid, pk["provenance"]), observed_on=OBSERVED_ON))
        for util, resp, provider, prov in prof["utilities"]:
            out["utilities"].append(dict(property_id=pid, utility=util, responsibility=resp, provider=provider,
                                         provenance=prov, source_url=_source(pid, prov), observed_on=OBSERVED_ON))
        for name, cat, hours, resv, fee_code, prov in prof["amenities"]:
            out["amenities"].append(dict(
                amenity_id=f"{pid}:{len([a for a in out['amenities'] if a['property_id'] == pid]) + 1:02d}",
                property_id=pid, amenity=name, category=cat, hours=hours, reservation_required=resv,
                fee_id=f"{pid}:{fee_code}" if fee_code else "", provenance=prov, source_url=_source(pid, prov),
                observed_on=OBSERVED_ON))
    return out


# ---------------------------------------------------------------------------------------------- guides
def _fee_names(prof: dict, category: str) -> list[str]:
    return [f["fee_name"].lower() for f in prof["fees"] if f["category"] == category and not f["effective_to"]]


def building_guide_md(p: dict, company: dict) -> str:
    pid = p["property_id"]
    prof = PROFILES[pid]
    pets, park = prof["pets"], prof["parking"]
    amen = prof["amenities"]
    util = {u: (r, prov) for u, r, prov, _ in prof["utilities"]}

    def sec(title, topics, body, extra_meta=""):
        meta = f"topics: {topics}" + (f" | {extra_meta}" if extra_meta else "")
        return ["", f"## {title}", f"<!-- {meta} -->", body]

    lines = ["---", f"doc_id: building-{pid.lower()}", "scope: property", "doc_type: building_guide",
             f"company_id: {p['company_id']}", f"property_id: {pid}", f"city: {p['city']}", f"state: {p['state']}",
             f"title: {p['name']} - Building Guide (practice)", f"version: {OBSERVED_ON} (synthetic practice document)",
             "---", f"# {p['name']} - Building Guide (practice)", "",
             f"> SYNTHETIC PRACTICE DOCUMENT. Built from public listing facts observed {OBSERVED_ON} plus invented "
             f"details. Not {company['name']}'s actual guide. Prices and fees are kept in the property database "
             "(fee schedule), not in this guide."]

    lines += sec("About the building", "amenities, leasing",
                 f"{prof['overview']} Built in {p['year_built']}, {int(p['units']):,} apartments, managed by "
                 f"{company['name']}.")

    category_words = {"fitness": "fitness/gym", "packages": "packages/deliveries", "outdoor": "outdoor space",
                      "event_space": "event/party space", "workspace": "co-working space"}
    amen_lines = []
    for name, cat, hours, resv, fee_code, _ in amen:
        bits = [category_words.get(cat, cat.replace("_", " ")), f"hours: {hours}"]
        if resv:
            bits.append("reservation required")
        if fee_code:
            bits.append("has a fee; see the fee schedule")
        amen_lines.append(f"- {name} ({'; '.join(bits)})")
    lines += sec("Amenities", "amenities", "\n".join(amen_lines))

    allowed = [k for k, v in (("cats", pets["cats_allowed"]), ("dogs", pets["dogs_allowed"])) if v]
    pet_body = (f"{' and '.join(allowed).capitalize() or 'No pets'} are allowed"
                + (f", up to {pets['max_pets']} pets per apartment" if pets["max_pets"] else "")
                + (f", dogs up to {pets['max_weight_lb']} lb" if pets["max_weight_lb"] else "")
                + (f"; {pets['breed_restrictions']}" if pets["breed_restrictions"] else "") + ". "
                + ("Register each pet with the office before it moves in. " if pets["registration_required"] else "")
                + f"{pets['notes']} Assistance animals are not pets and are handled through a reasonable "
                  "accommodation request. ")
    pet_fees = _fee_names(prof, "pet")
    pet_body += (f"Pet charges ({', '.join(pet_fees)}) are listed in the fee schedule." if pet_fees
                 else "There is no separate pet charge in the fee schedule.")
    lines += sec("Pets", "pets", pet_body)

    park_body = " ".join(
        f"{pk['parking_type']}" + (f", about {pk['spaces']} spaces" if pk["spaces"] else "")
        + ("; spaces are assigned" if pk["assigned"] else "") + ("; EV charging available" if pk["ev_charging"] else "")
        + ("; there is a waitlist" if pk["waitlist"] else "") + (f" ({pk['notes']})" if pk["notes"] else "") + "."
        for pk in park)
    bikes = [a[0] for a in amen if "bike" in a[0].lower()]
    if bikes:
        park_body += f" For bikes: {', '.join(bikes).lower()}."
    park_body += " Parking is optional and priced in the fee schedule."
    lines += sec("Parking and bikes", "parking", park_body)

    label = {"water_sewer": "Water and sewer", "hot_water": "Hot water", "cooking_gas": "Cooking gas"}
    util_lines = [f"- {label.get(u, u.capitalize())}: {UTILITY_WORDS[r]}" + (f" - {prov}" if prov else "")
                  for u, (r, prov) in util.items()]
    billed = [label.get(u, u).lower() for u, (r, _) in util.items() if r == "billed_back"]
    tail = (f"\nCharges for {', '.join(billed)} appear on your monthly statement; current amounts are in the fee "
            "schedule." if billed else "\nNo utilities are billed back by management.")
    lines += sec("Utilities and services", "utilities, garbage", "\n".join(util_lines) + tail)

    lines += sec("Packages and deliveries", "amenities", prof["packages"])
    lines += sec("Moving in and out", "moving", prof["moving"])
    lines += sec("Leases and renewals", "leasing, rent_and_fees",
                 prof["leasing"] + " Application, deposit and monthly charges are listed in the fee schedule.")
    for title, body, topics, posted, expires in prof["notices"]:
        lines += sec(f"Notice: {title}", topics, f"Posted {posted}. {body}",
                     extra_meta=f"posted: {posted} | expires: {expires}")
    return "\n".join(lines) + "\n"
