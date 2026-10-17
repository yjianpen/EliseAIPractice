"""Per-building operating profiles: the single source for BOTH outputs.

  structured facts  -> data/synthetic/{unit_types,fees,pet_policies,parking,utilities,amenities}.csv
                       -> data/structured/property_facts.db   (exact numbers, queried with SQL)
  building guides   -> knowledge/buildings/<property_id>.md  (prose, retrieved by the RAG engine)

Rule: dollar amounts live ONLY in the structured facts. Guides describe how things work and point to
the fee schedule, so the two can never disagree.

Provenance per fact:
  "listing"   - seen on a public listing or operator page (LISTING_SOURCES[pid]) on OBSERVED_ON.
                Listing data goes stale quickly; effective_to marks offers that have already ended.
  "synthetic" - invented for practice.
"""
from __future__ import annotations

OBSERVED_ON = "2026-10-17"

LISTING_SOURCES = {
    "P-NYC-001": "https://www.stuytown.com/amenities https://www.stuytown.com/amenities/modern-conveniences",
    "P-NYC-002": "https://www.apartmentsearch.com/apartments/new-york/manhattan/303-east-83rd",
    "P-NYC-003": "https://www.apartmentadvisor.com/details/111-lawrence-st-brooklyn-ny-11201",
    "P-SF-001": "https://www.essexapartmenthomes.com/apartments/san-francisco/fox-plaza "
                "https://s203.q4cdn.com/488215793/files/doc_news/2013/02/1/Essex-Acquires-San-Francisco-Apartment-Community.pdf",
    "P-SF-002": "https://www.essexapartmenthomes.com/apartments/park-west",
    "P-SF-003": "https://www.apartmentsearch.com/apartments/california/san-francisco/ava-55-ninth "
                "https://www.avaloncommunities.com/california/san-francisco-apartments/ava-55-ninth/apartments",
}

L, S = "listing", "synthetic"

# fee tuple: (fee_code, name, category, amount, basis, frequency, required, refundable, provenance, notes,
#             effective_from, effective_to)
#   basis:     flat | per_pet | months_of_rent
#   frequency: one_time | monthly | per_occurrence
#   category:  application | deposit | recurring | pet | parking | utility | amenity | penalty | service
#   required:  charged to every resident (pet charges default to False: they apply only to pet owners)


def fee(code, name, category, amount, basis="flat", frequency="one_time", required=None, refundable=False,
        provenance=S, notes="", effective_from="2026-01-01", effective_to=None):
    """required = charged to every resident. Pet charges apply only to pet owners, so they default to False."""
    if required is None:
        required = category != "pet"
    return dict(fee_code=code, fee_name=name, category=category, amount=amount, basis=basis, frequency=frequency,
                required=required, refundable=refundable, provenance=provenance, notes=notes,
                effective_from=effective_from, effective_to=effective_to)


PROFILES = {
    # ------------------------------------------------------------------ StuyTown (Beam Living)
    "P-NYC-001": dict(
        overview="StuyTown is an 80-acre community of brick apartment buildings between First Avenue and Avenue C "
                 "from East 14th to East 23rd Street, with lawns, playgrounds and The Oval at its center.",
        unit_types=[  # (unit_type, bedrooms, bathrooms, sqft_min, sqft_max, rent_min, rent_max, provenance)
            ("Studio", 0, 1, 420, 520, 3600, 4100, S), ("1 Bedroom", 1, 1, 600, 720, 4300, 5200, S),
            ("2 Bedroom", 2, 1, 760, 900, 5400, 6800, S), ("3 Bedroom", 3, 2, 1000, 1200, 6900, 8200, S)],
        fees=[
            fee("application", "Application and credit check fee", "application", 20),
            fee("security_deposit", "Security deposit", "deposit", 1, "months_of_rent", refundable=True),
            fee("stuyfitness", "StuyFitness membership", "amenity", 75, frequency="monthly", required=False),
            fee("parking", "Garage parking (LAZ Parking)", "parking", 525, frequency="monthly", required=False,
                notes="Valet or park & lock; monthly contracts through the garage operator"),
            fee("storage", "In-building storage unit (Storage Deluxe)", "service", 85, frequency="monthly",
                required=False, notes="Starting price; varies by size"),
            fee("late_fee", "Late rent fee", "penalty", 50, frequency="per_occurrence",
                notes="Charged when rent is not received by the 5th"),
            fee("key_fob", "Replacement key fob", "service", 25, frequency="per_occurrence", required=False),
        ],
        pets=dict(cats_allowed=True, dogs_allowed=True, max_pets=2, max_weight_lb=None, breed_restrictions="",
                  registration_required=True, provenance=S,
                  notes="Pets must be registered with resident services before move-in; a dog run is on site."),
        parking=[dict(parking_type="Covered garages (6, operated by LAZ Parking)", spaces=None, assigned=False,
                      ev_charging=False, waitlist=True, provenance=L,
                      notes="24/7 garages with valet and park & lock options")],
        utilities=[("heat", "included", "", S), ("hot_water", "included", "", S), ("cooking_gas", "included", "", S),
                   ("electricity", "tenant_direct", "Con Edison", S), ("water_sewer", "included", "", S),
                   ("trash", "included", "", S), ("internet", "tenant_direct", "Spectrum or Verizon Fios", S)],
        amenities=[  # (name, category, hours, reservation_required, fee_code, provenance)
            ("StuyFitness (3 fitness centers, classes, trainers)", "fitness", "5 AM - 11 PM", False, "stuyfitness", L),
            ("The Oval Study (library-style co-working space)", "workspace", "7 AM - 11 PM", False, None, L),
            ("Oval Services station (self-serve kiosk, equipment rentals)", "services", "8 AM - 8 PM", False, None, L),
            ("Smart Package Room", "packages", "24/7", False, None, L),
            ("15 playgrounds", "outdoor", "dawn to dusk", False, None, L),
            ("Dog run", "pets", "6 AM - 10 PM", False, None, L),
            ("Pickleball and athletic courts", "outdoor", "7 AM - 9 PM", False, None, L),
            ("Seasonal ice rink and greenmarket", "outdoor", "seasonal", False, None, L),
            ("River Room event space", "event_space", "by reservation", True, None, L),
            ("In-building storage (Storage Deluxe)", "storage", "24/7", False, "storage", L),
        ],
        packages="Packages go to the Smart Package Room, open 24/7; you get a pickup code by text or email.",
        moving="Moves are scheduled with resident services at least 5 business days ahead, Monday to Saturday "
               "8 AM - 6 PM. Movers must provide a certificate of insurance naming the owner and operator.",
        leasing="Leases are 12 or 24 months. Renewal offers go out about 90 days before the lease ends; rent "
                "stabilized apartments receive renewals on the state form within the required window.",
        notices=[  # (title, body, topics, posted_on, expires_on)
            ("Steam system maintenance - Building 4 and 5 Stuyvesant Oval",
             "Heat and hot water will be off from 9 AM to 1 PM while the steam plant valves are serviced.",
             "heat, hot_water", "2026-10-14", "2026-10-22"),
            ("Summer concert series", "Join us at The Oval for live music on Saturday.", "amenities",
             "2026-07-01", "2026-07-20"),
        ],
    ),
    # ------------------------------------------------------------------ 303 East 83rd (Vivmark)
    "P-NYC-002": dict(
        overview="303 East 83rd is a 30-story rental tower on the Upper East Side (Yorkville) with a concierge, "
                 "on-site maintenance and a garage.",
        unit_types=[("Studio", 0, 1, 450, 520, 3900, 4300, S), ("1 Bedroom", 1, 1, 602, 735, 4935, 5549, L),
                    ("2 Bedroom", 2, 2, 950, 1100, 6800, 7900, S), ("3 Bedroom", 3, 2, 1250, 1400, 8900, 10500, S)],
        fees=[
            fee("application", "Application fee", "application", 20, provenance=L),
            fee("holding_deposit", "Holding deposit", "deposit", 500, provenance=L, notes="Non-refundable per listing"),
            fee("security_deposit", "Security deposit", "deposit", 1, "months_of_rent", refundable=True),
            fee("security_deposit_special", "Security deposit special (select apartments)", "deposit", 1000,
                refundable=True, required=False, provenance=L, effective_from="2025-07-01",
                effective_to="2025-09-30", notes="Promotional; replaced the standard deposit on select units"),
            fee("amenity_fee", "Amenity use fee", "amenity", 50, frequency="monthly", provenance=L),
            fee("pet_fee", "Pet fee", "pet", 100, "per_pet", provenance=L, required=False,
                notes="Per cat or dog; listing calls it optional"),
            fee("parking", "Garage parking", "parking", 650, frequency="monthly", required=False),
            fee("late_fee", "Late rent fee", "penalty", 50, frequency="per_occurrence"),
        ],
        pets=dict(cats_allowed=True, dogs_allowed=True, max_pets=6, max_weight_lb=None, breed_restrictions="",
                  registration_required=True, provenance=L, notes="Up to 3 dogs and up to 3 cats per listing."),
        parking=[dict(parking_type="Covered garage in building", spaces=None, assigned=False, ev_charging=False,
                      waitlist=False, provenance=L, notes="")],
        utilities=[("heat", "included", "", S), ("hot_water", "included", "", S), ("cooking_gas", "included", "", S),
                   ("electricity", "tenant_direct", "Con Edison", S), ("water_sewer", "included", "", S),
                   ("trash", "included", "", S), ("internet", "tenant_direct", "Spectrum or Verizon Fios", S)],
        amenities=[("Concierge", "services", "24/7", False, None, L),
                   ("Fitness center", "fitness", "24/7 with key fob", False, "amenity_fee", L),
                   ("Package receiving", "packages", "24/7 at concierge", False, None, L),
                   ("Laundry room", "laundry", "7 AM - 11 PM", False, None, L),
                   ("Garage parking", "parking", "24/7", False, "parking", L)],
        packages="The concierge desk signs for packages 24/7 and notifies you by text.",
        moving="Reserve the service elevator through the office at least 3 business days ahead; moves run "
               "Monday to Saturday 9 AM - 5 PM. Movers need a certificate of insurance.",
        leasing="12-month leases; short-term leases are not offered. Renewal offers go out about 90 days before "
                "the lease end date.",
        notices=[("Fitness center refresh", "New cardio equipment is being installed; the fitness center is "
                  "closed during installation.", "amenities", "2026-10-10", "2026-10-31")],
    ),
    # ------------------------------------------------------------------ The Brooklyner (Vivmark)
    "P-NYC-003": dict(
        overview="The Brooklyner is a 51-story rental tower in Downtown Brooklyn with a rooftop lounge and sundeck, "
                 "concierge and on-site valet parking.",
        unit_types=[("Studio", 0, 1, 430, 520, 3413, 3747, L), ("1 Bedroom", 1, 1, 600, 720, 4122, 4472, L),
                    ("2 Bedroom", 2, 2, 950, 1150, 5600, 6900, S)],
        fees=[
            fee("application", "Application fee", "application", 17, provenance=L),
            fee("holding_deposit", "Holding deposit", "deposit", 500, refundable=True, provenance=L),
            fee("security_deposit", "Security deposit", "deposit", 1, "months_of_rent", refundable=True),
            fee("utility_setup", "Utility account setup fee", "utility", 10, provenance=L),
            fee("utility_billing", "Utility billing service fee", "utility", 5, frequency="monthly", provenance=L),
            fee("amenity_fee", "Amenity use fee (fitness center)", "amenity", 100, frequency="monthly", provenance=L),
            fee("pet_fee", "Pet fee", "pet", 100, "per_pet", provenance=L),
            fee("water_sewer", "Water and sewer (submetered)", "utility", 45, frequency="monthly",
                notes="Average; billed on actual usage"),
            fee("parking", "Valet parking", "parking", 595, frequency="monthly", required=False),
            fee("late_fee", "Late rent fee", "penalty", 50, frequency="per_occurrence"),
        ],
        pets=dict(cats_allowed=True, dogs_allowed=True, max_pets=2, max_weight_lb=None, breed_restrictions="",
                  registration_required=True, provenance=L, notes="Cats and dogs allowed."),
        parking=[dict(parking_type="On-site valet garage", spaces=None, assigned=False, ev_charging=True,
                      waitlist=False, provenance=L, notes="")],
        utilities=[("heat", "tenant_direct", "Con Edison (in-unit heat pump)", S), ("hot_water", "included", "", S),
                   ("electricity", "tenant_direct", "Con Edison", L), ("water_sewer", "billed_back", "submetered", S),
                   ("trash", "included", "", S), ("internet", "tenant_direct", "Verizon Fios or Optimum", S)],
        amenities=[("Fitness center and yoga studio", "fitness", "24/7 with key fob", False, "amenity_fee", L),
                   ("Rooftop lounge and sundeck", "outdoor", "8 AM - 11 PM, seasonal", False, None, L),
                   ("Resident lounge and game room", "lounge", "8 AM - 11 PM", False, None, L),
                   ("Outdoor grilling areas", "outdoor", "10 AM - 10 PM", True, None, L),
                   ("Concierge", "services", "24/7", False, None, L),
                   ("Package receiving", "packages", "24/7 at concierge", False, None, L),
                   ("Bike storage", "storage", "24/7", False, None, L),
                   ("Storage space", "storage", "by request", False, None, L),
                   ("Valet parking", "parking", "24/7", False, "parking", L)],
        packages="The concierge receives packages 24/7; perishable deliveries go to the cold-storage shelves.",
        moving="Book a move window through the resident portal at least 3 business days ahead; the service "
               "elevator is padded and reserved for your window.",
        leasing="12-month leases are standard; renewal offers arrive about 90 days before your lease ends.",
        notices=[("Rooftop closed for the season", "The rooftop sundeck closes for winter; the resident lounge "
                  "stays open.", "amenities", "2026-10-15", "2027-04-15")],
    ),
    # ------------------------------------------------------------------ Fox Plaza (Essex)
    "P-SF-001": dict(
        overview="Fox Plaza is a 29-story tower on Market Street at Civic Center; apartments occupy floors 14-29 "
                 "above offices, with retail and a two-level underground garage.",
        unit_types=[("Studio", 0, 1, 400, 500, 1864, 2300, L), ("1 Bedroom", 1, 1, 550, 700, 2350, 2700, S),
                    ("2 Bedroom", 2, 1, 800, 950, 2750, 3014, L)],
        fees=[
            fee("application", "Application screening fee", "application", 50),
            fee("security_deposit", "Security deposit", "deposit", 1, "months_of_rent", refundable=True),
            fee("pet_rent", "Pet rent", "pet", 50, "per_pet", "monthly"),
            fee("trash_fee", "Trash and recycling fee", "utility", 25, frequency="monthly",
                notes="Recology service billed back as a flat monthly charge"),
            fee("water_sewer", "Water and sewer", "utility", 40, frequency="monthly",
                notes="Allocated by apartment size and occupancy"),
            fee("parking", "Underground garage parking", "parking", 300, frequency="monthly", required=False),
            fee("late_fee", "Late rent fee", "penalty", 75, frequency="per_occurrence"),
        ],
        pets=dict(cats_allowed=True, dogs_allowed=True, max_pets=2, max_weight_lb=50, breed_restrictions="",
                  registration_required=True, provenance=S, notes="Pet-friendly residences (listing)."),
        parking=[dict(parking_type="Two-level underground garage (about 405 stalls)", spaces=405, assigned=False,
                      ev_charging=False, waitlist=False, provenance=L, notes="Garage shared with retail and office")],
        utilities=[("heat", "included", "", S), ("hot_water", "included", "", S), ("electricity", "tenant_direct",
                   "PG&E", S), ("water_sewer", "billed_back", "allocated", S), ("trash", "billed_back", "Recology", S),
                   ("internet", "tenant_direct", "Comcast Xfinity or Sonic", S)],
        amenities=[("Fitness center", "fitness", "5 AM - 11 PM", False, None, L),
                   ("USPS Post Office on site", "services", "post office hours", False, None, L),
                   ("Package receiving", "packages", "Mon-Sat 9 AM - 6 PM", False, None, L),
                   ("Dry cleaning valet", "services", "pickup Mon/Thu", False, None, L),
                   ("Redwood Credit Union branch", "services", "branch hours", False, None, L),
                   ("Starbucks in building", "services", "store hours", False, None, L)],
        packages="Packages are received at the management office during business hours and held for 7 days.",
        moving="Reserve the freight elevator through the leasing office; moves are allowed Monday to Saturday "
               "9 AM - 5 PM through the garage loading dock.",
        leasing="12-month leases are standard, with shorter terms at some move-in dates. Renewal offers go out "
                "about 60 days before the lease ends.",
        notices=[("Freight elevator inspection", "The freight elevator is out of service for its annual "
                  "inspection; moves are paused that day.", "elevator, moving", "2026-10-12", "2026-10-25")],
    ),
    # ------------------------------------------------------------------ Park West (Essex)
    "P-SF-002": dict(
        overview="Park West is a low-rise community next to Golden Gate Park with in-home washers and dryers and "
                 "a dog run.",
        unit_types=[("1 Bedroom", 1, 1, 650, 760, 2900, 3300, S), ("2 Bedroom", 2, 1, 850, 1000, 3700, 4200, S)],
        fees=[
            fee("application", "Application screening fee", "application", 50),
            fee("security_deposit", "Security deposit", "deposit", 1, "months_of_rent", refundable=True),
            fee("pet_rent", "Pet rent", "pet", 50, "per_pet", "monthly"),
            fee("trash_fee", "Trash and recycling fee", "utility", 30, frequency="monthly",
                notes="Recology service billed back as a flat monthly charge"),
            fee("water_sewer", "Water and sewer", "utility", 55, frequency="monthly",
                notes="Allocated by apartment size and occupancy"),
            fee("parking", "Assigned parking space", "parking", 200, frequency="monthly", required=False,
                notes="Limited spaces; waitlist"),
            fee("late_fee", "Late rent fee", "penalty", 75, frequency="per_occurrence"),
        ],
        pets=dict(cats_allowed=True, dogs_allowed=True, max_pets=2, max_weight_lb=60,
                  breed_restrictions="aggressive breeds per Essex standard list", registration_required=True,
                  provenance=S, notes="Pet-friendly with an on-site dog run (listing)."),
        parking=[dict(parking_type="Assigned surface and tuck-under spaces", spaces=60, assigned=True,
                      ev_charging=False, waitlist=True, provenance=S, notes="")],
        utilities=[("heat", "tenant_direct", "PG&E (electric wall heaters)", S), ("hot_water", "included", "", S),
                   ("electricity", "tenant_direct", "PG&E", S), ("water_sewer", "billed_back", "allocated", S),
                   ("trash", "billed_back", "Recology", S), ("internet", "tenant_direct", "Comcast Xfinity or Sonic", S)],
        amenities=[("In-home washer and dryer", "laundry", "in unit", False, None, L),
                   ("Dog run", "pets", "7 AM - 9 PM", False, None, L),
                   ("Package lockers", "packages", "24/7", False, None, S)],
        packages="Carriers deliver to the package lockers by the main entrance; you get a code by email.",
        moving="Schedule your move with the leasing office; moves are allowed daily 8 AM - 7 PM.",
        leasing="12-month leases. Renewal offers go out about 60 days before the lease ends.",
        notices=[("Exterior painting", "Painters will work on the Funston Avenue side; please keep windows "
                  "closed during work hours.", "paint_plaster", "2026-10-05", "2026-11-15")],
    ),
    # ------------------------------------------------------------------ AVA 55 Ninth (Vivmark)
    "P-SF-003": dict(
        overview="AVA 55 Ninth is a 17-story SoMa building with a 10,000 square foot courtyard, bike shop, dog run "
                 "and underground parking.",
        unit_types=[("Studio", 0, 1, 450, 520, 2700, 2950, S), ("1 Bedroom", 1, 1, 650, 733, 3250, 3450, L),
                    ("2 Bedroom", 2, 2, 855, 986, 3880, 4293, L)],
        fees=[
            fee("application", "Application screening fee", "application", 55),
            fee("security_deposit", "Security deposit", "deposit", 1000, refundable=True, provenance=L,
                notes="Listing amount; may vary by credit result"),
            fee("pet_fee", "Pet fee", "pet", 300, "per_pet"),
            fee("pet_rent", "Pet rent", "pet", 75, "per_pet", "monthly"),
            fee("trash_fee", "Trash and recycling fee", "utility", 35, frequency="monthly",
                notes="Recology service billed back as a flat monthly charge"),
            fee("water_sewer", "Water and sewer", "utility", 60, frequency="monthly",
                notes="Allocated by apartment size and occupancy"),
            fee("parking", "Underground parking", "parking", 350, frequency="monthly", required=False),
            fee("ev_charging", "EV charging add-on", "parking", 50, frequency="monthly", required=False),
            fee("late_fee", "Late rent fee", "penalty", 50, frequency="per_occurrence"),
        ],
        pets=dict(cats_allowed=True, dogs_allowed=True, max_pets=4, max_weight_lb=None,
                  breed_restrictions="breed and pet restrictions apply", registration_required=True, provenance=L,
                  notes="Up to 2 dogs and up to 2 cats; big dogs welcome; dog run and pet wash station."),
        parking=[dict(parking_type="Underground garage", spaces=None, assigned=False, ev_charging=True,
                      waitlist=False, provenance=L, notes="EV outlets available")],
        utilities=[("heat", "tenant_direct", "PG&E (in-unit electric heat)", S), ("hot_water", "included", "", S),
                   ("electricity", "tenant_direct", "PG&E", S), ("water_sewer", "billed_back", "allocated", S),
                   ("trash", "billed_back", "Recology", S), ("internet", "tenant_direct", "Comcast Xfinity or Sonic", S)],
        amenities=[("Fitness center", "fitness", "24/7 with key fob", False, None, L),
                   ("Bike storage and repair room", "storage", "24/7", False, None, L),
                   ("Dog run and pet wash station", "pets", "6 AM - 10 PM", False, None, L),
                   ("Courtyard with outdoor movie screen", "outdoor", "7 AM - 10 PM", False, None, L),
                   ("Lounge, terrace, grills and DIY work space", "lounge", "7 AM - 11 PM", True, None, L),
                   ("Package receiving", "packages", "24/7 lockers", False, None, L),
                   ("Underground parking with EV outlets", "parking", "24/7", False, "parking", L)],
        packages="Packages go to smart lockers in the lobby; oversized items are held at the leasing office.",
        moving="Reserve a move window in the resident app at least 2 business days ahead; moves run daily "
               "8 AM - 6 PM using the garage-level elevator.",
        leasing="Lease terms from 6 to 15 months depending on move-in date; short-term leases are not offered. "
                "Renewal offers go out about 60 days before the lease ends.",
        notices=[("Garage gate repair", "The garage gate will be open and staffed while a new motor is "
                  "installed.", "parking", "2026-10-16", "2026-10-20")],
    ),
}
