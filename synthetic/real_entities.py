"""Real operators and buildings used as the static backbone of the synthetic data.

PROVENANCE
- Facts listed in each record's `verified_fields` (names, operators, addresses, year built, unit counts,
  floors, tickers, leadership) were checked against the `source_urls` on `verified_on`.
- Everything else on a property (heat system, quiet hours, trash days, pet rules, office hours, contacts,
  phone numbers) is SYNTHETIC: plausible values invented for practice, listed in `synthetic_fields`.
- Tenants, leases, work orders, vendors and compliance dates generated from these records are synthetic.
- Policy guidebooks in knowledge/policies/ are practice documents, NOT these companies' actual policies.

FRESHNESS
These records are a static snapshot. Ownership and management change (e.g. AvalonBay and Equity
Residential merged into Vivmark Residential in August 2026; Mosso at 900 Folsom St, an Essex property in
2015, is now managed by Brookfield). `verified_on` is what a freshness job should re-check.
"""
from __future__ import annotations

SNAPSHOT_DATE = "2026-10-17"

COMPANIES = [
    dict(
        company_id="C-VIVMARK",
        name="Vivmark Residential",
        ticker="NYSE: VMRK",
        hq_city="",  # not stated in the merger coverage checked; left blank rather than guessed
        website="https://vivmarkresidential.com",
        description="Apartment REIT formed in August 2026 by the merger of AvalonBay Communities and Equity "
                    "Residential; more than 184,000 apartments. CEO Benjamin Schall. Community names (Avalon, AVA, "
                    "Equity-branded buildings) were kept after the merger.",
        predecessors="AvalonBay Communities (NYSE: AVB, Arlington VA); Equity Residential (NYSE: EQR, Chicago IL)",
        emergency_line="212-555-0100",  # synthetic
        office_email="residents@vivmark.example.com",  # synthetic
        verified_fields="name, ticker, website, merger, CEO, apartment count",
        source_urls="https://www.citybiz.co/article/889884/avalonbay-equity-residential-complete-merger-to-form-70-billion-vivmark-residential/ "
                    "https://www.multifamilydive.com/news/equity-residential-avalonbay-combined-vivmark-residential/826741/",
        verified_on=SNAPSHOT_DATE,
    ),
    dict(
        company_id="C-BEAM",
        name="Beam Living",
        ticker="",
        hq_city="New York",
        website="https://www.blackstone.com/housing/stuytown/",
        description="On-site management company built by Blackstone to operate StuyTown (Stuyvesant Town-Peter Cooper "
                    "Village), Manhattan; Blackstone has owned the complex since 2015.",
        predecessors="",
        emergency_line="212-555-0150",  # synthetic
        office_email="residents@beamliving.example.com",  # synthetic
        verified_fields="name, role as StuyTown operator, owner Blackstone",
        source_urls="https://www.blackstone.com/housing/stuytown/",
        verified_on=SNAPSHOT_DATE,
    ),
    dict(
        company_id="C-ESSEX",
        name="Essex Property Trust",
        ticker="NYSE: ESS",
        hq_city="San Mateo",
        website="https://www.essexapartmenthomes.com",
        description="West Coast apartment REIT (California and Seattle); ownership interests in 258 communities with "
                    "over 62,000 apartment homes (Q2 2026).",
        predecessors="",
        emergency_line="415-555-0100",  # synthetic
        office_email="residents@essex.example.com",  # synthetic
        verified_fields="name, ticker, HQ, markets, portfolio size",
        source_urls="https://www.businesswire.com/news/home/20260729202303/en/ https://en.wikipedia.org/wiki/Essex_Property_Trust",
        verified_on=SNAPSHOT_DATE,
    ),
]

_SYNTH = ("units_modeled, emergency_line, has_elevator, heat_system, heat_controlled_by, hot_water_system, laundry, quiet_hours, "
          "trash_days, recycling_days, pets, smoking, site_contact, site_phone, office_hours")

# Each property is a real building, chosen so different legal rules apply.
PROPERTIES = [
    # 1947 -> NYC Local Law 1 (pre-1960) and federal pre-1978 lead rules; partly rent stabilized; very large
    dict(property_id="P-NYC-001", company_id="C-BEAM", name="StuyTown (Stuyvesant Town-Peter Cooper Village)",
         city="New York", state="NY", district="Manhattan",
         address="First Ave to Avenue C, E 14th St to E 23rd St, New York, NY 10009/10010",
         owner="Blackstone", year_built=1947, units=11250, floors=13, units_modeled=120,
         has_elevator=True, heat_system="central steam plant serving all buildings", heat_controlled_by="landlord",
         hot_water_system="central plant", laundry="laundry rooms in building basements",
         quiet_hours="10:00 PM - 8:00 AM", trash_days="daily (compactor rooms on each floor)", recycling_days="daily",
         pets="dogs and cats allowed with registration", smoking="smoke-free buildings",
         site_contact="StuyTown resident services (synthetic contact)", site_phone="212-555-0111",
         office_hours="Mon-Sat 9 AM - 6 PM", rent_regulated=True,
         verified_fields="name, operator, owner, location, opened 1947, 11,250 apartments, rent regulation (partial)",
         source_urls="https://en.wikipedia.org/wiki/Stuyvesant_Town%E2%80%93Peter_Cooper_Village https://www.blackstone.com/housing/stuytown/"),
    # 1977 -> federal pre-1978 lead disclosure; Local Law 1 only with owner knowledge
    dict(property_id="P-NYC-002", company_id="C-VIVMARK", name="303 East 83rd", city="New York", state="NY",
         district="Manhattan", address="303 E 83rd St, New York, NY 10028", owner="", year_built=1977, units=261,
         floors=30, units_modeled=100,
         has_elevator=True, heat_system="central hot-water boiler with apartment thermostats", heat_controlled_by="landlord",
         hot_water_system="central gas water heaters", laundry="laundry room on lower level",
         quiet_hours="10:00 PM - 7:00 AM", trash_days="trash chute daily; bulk items by request", recycling_days="daily",
         pets="dogs and cats allowed with addendum, max 2", smoking="smoke-free building",
         site_contact="303 East 83rd leasing and management office (synthetic contact)", site_phone="212-555-0122",
         office_hours="Mon-Sat 9 AM - 6 PM", rent_regulated=False,
         verified_fields="name, address, year built 1977, 261 apartments, 30 floors, rental, listed by operator",
         source_urls="https://cityrealty.com/nyc/yorkville/303-east-83rd-street/4141 https://www.equityapartments.com/new-york-city-apartments"),
    # 2010 tower
    dict(property_id="P-NYC-003", company_id="C-VIVMARK", name="The Brooklyner", city="New York", state="NY",
         district="Brooklyn", address="111 Lawrence St, Brooklyn, NY 11201", owner="", year_built=2010, units=491,
         floors=51, units_modeled=100,
         has_elevator=True, heat_system="in-unit heat pumps, tenant thermostat", heat_controlled_by="tenant",
         hot_water_system="central high-efficiency boilers", laundry="in-unit washer/dryer",
         quiet_hours="11:00 PM - 7:00 AM", trash_days="daily chute; bulk items via concierge", recycling_days="daily chute",
         pets="dogs and cats allowed", smoking="smoke-free building",
         site_contact="The Brooklyner resident services (synthetic contact)", site_phone="718-555-0133",
         office_hours="daily 9 AM - 7 PM", rent_regulated=False,
         verified_fields="name, address, completed 2010, 491 rental units, 51 stories, listed by operator",
         source_urls="https://en.wikipedia.org/wiki/Brooklyner https://www.equityapartments.com/new-york-city-apartments"),
    # 1968 -> federal pre-1978 lead disclosure; SF Rent Ordinance (pre-1979)
    dict(property_id="P-SF-001", company_id="C-ESSEX", name="Fox Plaza", city="San Francisco", state="CA",
         district="Civic Center", address="1390 Market St, San Francisco, CA 94102", owner="Essex Property Trust",
         year_built=1968, units=443, floors=29, units_modeled=100,
         has_elevator=True, heat_system="central hot-water heating, landlord-controlled", heat_controlled_by="landlord",
         hot_water_system="central boilers", laundry="laundry rooms on residential floors",
         quiet_hours="10:00 PM - 7:00 AM", trash_days="trash room daily; Recology pickup Mon/Thu", recycling_days="Mon/Thu",
         pets="cats and dogs allowed with addendum", smoking="smoke-free building",
         site_contact="Fox Plaza leasing office (synthetic contact)", site_phone="415-555-0144",
         office_hours="Mon-Fri 9 AM - 6 PM", rent_regulated=True,
         verified_fields="name, address, built 1968, ~443 apartments on floors 14-29 of a 29-story tower, Essex",
         source_urls="https://s203.q4cdn.com/488215793/files/doc_news/2013/02/1/Essex-Acquires-San-Francisco-Apartment-Community.pdf "
                     "https://www.essexapartmenthomes.com/apartments/san-francisco/fox-plaza"),
    # 1958 -> federal pre-1978 lead disclosure; SF Rent Ordinance
    dict(property_id="P-SF-002", company_id="C-ESSEX", name="Park West", city="San Francisco", state="CA",
         district="Inner Richmond", address="121 Funston Ave, San Francisco, CA 94118", owner="Essex Property Trust",
         year_built=1958, units=126, floors=4, units_modeled=60,
         has_elevator=False, heat_system="in-unit electric wall heaters, tenant thermostat", heat_controlled_by="tenant",
         hot_water_system="central gas water heaters", laundry="in-unit washer/dryer",
         quiet_hours="10:00 PM - 8:00 AM", trash_days="Tue (Recology: black, blue, green bins)", recycling_days="Tue",
         pets="pet-friendly; dog run on site", smoking="no smoking anywhere on property",
         site_contact="Park West leasing office (synthetic contact)", site_phone="415-555-0155",
         office_hours="Mon-Fri 9 AM - 5 PM", rent_regulated=True,
         verified_fields="name, address, built 1958, 126 apartments (2015 list), Essex, in-home washer/dryer, dog run",
         source_urls="https://s203.q4cdn.com/488215793/files/doc_financials/2015/q1/Q115-Property-List.pdf "
                     "https://www.essexapartmenthomes.com/apartments/park-west"),
    # 2014 mid-rise; same company as two NYC buildings -> one operator, two cities
    dict(property_id="P-SF-003", company_id="C-VIVMARK", name="AVA 55 Ninth", city="San Francisco", state="CA",
         district="SoMa", address="55 Ninth St, San Francisco, CA 94103", owner="", year_built=2014, units=273,
         floors=17, units_modeled=100,
         has_elevator=True, heat_system="in-unit electric heat, tenant thermostat", heat_controlled_by="tenant",
         hot_water_system="central boilers", laundry="in-unit washer/dryer",
         quiet_hours="10:00 PM - 7:00 AM", trash_days="trash room daily; Recology pickup Mon/Thu", recycling_days="Mon/Thu",
         pets="dogs and cats allowed with addendum", smoking="smoke-free building",
         site_contact="AVA 55 Ninth leasing office (synthetic contact)", site_phone="415-555-0166",
         office_hours="daily 9 AM - 6 PM", rent_regulated=False,
         verified_fields="name, address, 273 rental units, 17 stories, developed by AvalonBay, listed by operator",
         source_urls="https://socketsite.com/archives/2012/06/273_rental_units_ready_to_rise_at_55_9th_street.html "
                     "https://www.equityapartments.com/san-francisco-bay-apartments"),
]

# synthetic after-hours lines, per operator and city (all in the reserved 555-01xx range)
_EMERGENCY = {("C-BEAM", "New York"): "212-555-0150", ("C-VIVMARK", "New York"): "212-555-0100",
              ("C-VIVMARK", "San Francisco"): "415-555-0110", ("C-ESSEX", "San Francisco"): "415-555-0100"}

for _p in PROPERTIES:
    _p["emergency_line"] = _EMERGENCY[(_p["company_id"], _p["city"])]
    _p["synthetic_fields"] = _SYNTH
    _p["verified_on"] = SNAPSHOT_DATE
