"""Tests for the synthetic source of truth and the two RAG databases.

Run:  python -m unittest -v
"""
from __future__ import annotations

import csv
import json
import random
import unittest
from datetime import date

from rag import build
from rag.common import LAW_DIR, SYNTHETIC_DIR, detect_topics, fts_query, taxonomy
from rag.retrieve import build_context, render_context, search_laws, search_policies
from synthetic import generate

NYC = ("New York", "NY")
SF = ("San Francisco", "CA")


def rows(name: str) -> list[dict]:
    with (SYNTHETIC_DIR / f"{name}.csv").open() as f:
        return list(csv.DictReader(f))


class TestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build.build_all()


class TestJurisdictionIsolation(TestBase):
    """A property only ever sees laws for its own city, its own state, and federal law."""

    QUESTIONS = ["no heat", "mold in the bathroom", "mice and roaches", "landlord entered without notice",
                 "loud music from upstairs", "peeling paint and my toddler", "bed bugs", "they raised my rent after I complained"]

    def test_sf_never_gets_new_york_law(self):
        for q in self.QUESTIONS:
            for h in search_laws(q, *SF, k=20):
                self.assertIn(h.meta["jurisdiction"], {"San Francisco", "CA", "US"}, (q, h.id))

    def test_nyc_never_gets_california_law(self):
        for q in self.QUESTIONS:
            for h in search_laws(q, *NYC, k=20):
                self.assertIn(h.meta["jurisdiction"], {"New York", "NY", "US"}, (q, h.id))

    def test_city_specific_heat_law(self):
        self.assertEqual(search_laws("my radiator is cold", *NYC)[0].id, "nyc-heat")
        self.assertEqual(search_laws("my radiator is cold", *SF)[0].id, "sf-heat")

    def test_city_specific_entry_law(self):
        self.assertEqual(search_laws("can the landlord enter without notice", *SF)[0].id, "ca-entry")
        self.assertEqual(search_laws("can the landlord enter without notice", *NYC)[0].id, "nyc-entry-access")

    def test_pre_1978_lead_federal_rule_reaches_sf(self):
        ids = [h.id for h in search_laws("peeling lead paint", *SF)]
        self.assertIn("us-lead-disclosure", ids)

    def test_retaliation_uses_state_law(self):
        self.assertEqual(search_laws("they want to evict me because I complained", *NYC)[0].id, "ny-retaliation")
        self.assertEqual(search_laws("they want to evict me because I complained", *SF)[0].id, "ca-retaliation")


class TestPolicyScoping(TestBase):
    """Policies come only from the property's company (city-appropriate sections) and its own addendum."""

    def test_company_isolation(self):
        operator = {"P-NYC-001": "beam", "P-NYC-002": "vivmark", "P-NYC-003": "vivmark",
                    "P-SF-001": "essex", "P-SF-002": "essex", "P-SF-003": "vivmark"}
        for pid, company in operator.items():
            for h in search_policies("heat leak mold noise pests entry", pid, k=50, topics=list(taxonomy())):
                if h.meta["scope"] == "company":
                    self.assertEqual(h.meta["doc_id"], f"guidebook-c-{company}", (pid, h.id))

    def test_same_company_different_city_sections(self):
        # Vivmark runs P-NYC-002 (Manhattan) and P-SF-003 (San Francisco)
        sf = [h.title for h in search_policies("radiator is cold", "P-SF-003", k=10)]
        ny = [h.title for h in search_policies("radiator is cold", "P-NYC-002", k=10)]
        self.assertTrue(any("San Francisco" in t for t in sf), sf)
        self.assertFalse(any("New York City" in t for t in sf), sf)
        self.assertTrue(any("New York City" in t for t in ny), ny)
        self.assertFalse(any("San Francisco" in t for t in ny), ny)

    def test_only_own_property_addendum(self):
        for h in search_policies("quiet hours noise", "P-NYC-002", k=20):
            if h.meta["scope"] == "property":
                self.assertEqual(h.meta["doc_id"], "addendum-p-nyc-002")

    def test_addendum_reflects_property_facts(self):
        hits = search_policies("what are the quiet hours", "P-NYC-003", k=5)
        addendum = next(h for h in hits if h.meta["scope"] == "property")
        self.assertIn("11:00 PM", addendum.text)  # The Brooklyner differs from the 10 PM default

    def test_irrelevant_question_returns_nothing(self):
        self.assertEqual(search_policies("what is the capital of france", "P-NYC-003"), [])

    def test_amenity_question_finds_amenities_section(self):
        hits = search_policies("what time does the gym open", "P-NYC-003", today=date(2026, 10, 17))
        self.assertEqual(hits[0].title, "The Brooklyner - Building Guide (practice) > Amenities")

    def test_fts_syntax_is_neutralized(self):
        for q in ['"', 'AND OR NOT', 'NEAR(heat, mold)', "heat* -cold ^title:'x'", ""]:
            search_policies(q, "P-NYC-001")
            search_laws(q, *NYC)
        self.assertNotIn("(", fts_query("NEAR(heat, mold)"))


class TestContext(TestBase):
    def test_gas_is_emergency(self):
        ctx = build_context("I smell gas in the kitchen", "P-SF-003", "P-SF-003-1A")
        self.assertEqual(ctx["urgency"], "emergency")
        self.assertIn("911", render_context(ctx))

    def test_heat_season_note(self):
        winter = build_context("no heat", "P-NYC-001", today=date(2026, 1, 10))
        summer = build_context("no heat", "P-NYC-001", today=date(2026, 7, 10))
        self.assertTrue(any("IN effect" in n for n in winter["notes"]))
        self.assertTrue(any("NOT in effect" in n for n in summer["notes"]))

    def test_tenant_controlled_heat_note(self):
        ctx = build_context("my heater is not working", "P-SF-002")
        self.assertTrue(any("tenant-controlled" in n for n in ctx["notes"]))

    def test_city_services_routed_to_311(self):
        ctx = build_context("someone is parked in front of the hydrant", "P-NYC-002")
        self.assertEqual(ctx["urgency"], "city")

    def test_compliance_linked_to_retrieved_law(self):
        ctx = build_context("peeling paint, my 2 year old child lives here", "P-NYC-001", "P-NYC-001-2A")  # StuyTown, 1947
        self.assertIn("nyc-lead-ll1", [h["id"] for h in ctx["laws"]])
        self.assertTrue(any(c["law_id"] == "nyc-lead-ll1" for c in ctx["compliance"]))


class TestRealEntityProvenance(unittest.TestCase):
    """Real operators/buildings carry sources and a verification date; invented fields are declared."""

    def test_every_company_and_property_has_provenance(self):
        for r in rows("companies") + rows("properties"):
            self.assertTrue(r["source_urls"].startswith("https://"), r)
            self.assertRegex(r["verified_on"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertTrue(r["verified_fields"], r)
        for r in rows("properties"):
            self.assertIn("site_phone", r["synthetic_fields"])

    def test_contacts_are_fictional(self):
        for r in rows("companies"):
            self.assertRegex(r["emergency_line"], r"^\d{3}-555-01\d\d$")
            self.assertTrue(r["office_email"].endswith(".example.com"))
        for r in rows("properties"):
            self.assertRegex(r["site_phone"], r"^\d{3}-555-01\d\d$")  # 555-0100..0199 is reserved for fiction
            self.assertRegex(r["emergency_line"], r"^\d{3}-555-01\d\d$")
            self.assertEqual(r["emergency_line"][:3] == "415", r["city"] == "San Francisco", r["property_id"])
            self.assertIn("synthetic", r["site_contact"])

    def test_policy_documents_carry_practice_disclaimer(self):
        from rag.common import POLICY_DIR
        for path in POLICY_DIR.rglob("*.md"):
            text = path.read_text()
            self.assertIn("SYNTHETIC PRACTICE DOCUMENT", text, path)
            self.assertIn("(practice)", text.split("title:", 1)[1].splitlines()[0], path)

    def test_modeled_units_do_not_exceed_real_units(self):
        for r in rows("properties"):
            self.assertLessEqual(int(r["units_modeled"]), int(r["units"]), r["property_id"])
        counts = {}
        for u in rows("units"):
            counts[u["property_id"]] = counts.get(u["property_id"], 0) + 1
        for r in rows("properties"):
            self.assertEqual(counts[r["property_id"]], int(r["units_modeled"]))

    def test_unit_ids_unique(self):
        ids = [u["unit_id"] for u in rows("units")]
        self.assertEqual(len(ids), len(set(ids)))


class TestSourceOfTruthIntegrity(unittest.TestCase):
    def test_foreign_keys(self):
        props = {p["property_id"] for p in rows("properties")}
        units = {u["unit_id"]: u for u in rows("units")}
        tenants = {t["tenant_id"] for t in rows("tenants")}
        vendors = {v["vendor_id"] for v in rows("vendors")}
        self.assertTrue(all(u["property_id"] in props for u in units.values()))
        for w in rows("work_orders"):
            self.assertIn(w["unit_id"], units)
            self.assertEqual(units[w["unit_id"]]["property_id"], w["property_id"])
            self.assertIn(w["tenant_id"], tenants)
            self.assertIn(w["topic"], taxonomy())
            if w["assigned_vendor_id"]:
                self.assertIn(w["assigned_vendor_id"], vendors)
        for l in rows("leases"):
            self.assertIn(l["unit_id"], units)
            self.assertLess(l["start_date"], l["end_date"])

    def test_compliance_points_at_real_laws(self):
        law_ids = {law["id"] for p in LAW_DIR.glob("*.json") for law in json.loads(p.read_text())["laws"]}
        for c in rows("compliance"):
            if c["law_id"]:
                self.assertIn(c["law_id"], law_ids, c)

    def test_nyc_heat_work_orders_only_in_heat_season(self):
        nyc = {p["property_id"] for p in rows("properties") if p["city"] == "New York"}
        for w in rows("work_orders"):
            if w["topic"] == "heat" and w["property_id"] in nyc:
                self.assertNotIn(int(w["created_at"][5:7]), range(6, 10), w["work_order_id"])

    def test_generator_is_deterministic(self):
        def run(seed):
            s = generate.Store(companies=generate.COMPANIES, properties=[dict(p) for p in generate.PROPERTIES])
            rng = random.Random(seed)
            generate.gen_units_tenants_leases(rng, s)
            generate.gen_vendors(rng, s)
            generate.gen_work_orders(rng, s)
            return s.work_orders
        self.assertEqual(run(5), run(5))
        self.assertNotEqual(run(5), run(6))

    def test_every_taxonomy_topic_reachable(self):
        """Each topic has at least one policy section or law record, so the agent can always ground an answer."""
        build.build_all()
        import sqlite3
        covered = set()
        for db, table in ((build.POLICIES_DB, "chunks"), (build.LAWS_DB, "laws")):
            con = sqlite3.connect(db)
            for (topics,) in con.execute(f"SELECT topics FROM {table}"):
                covered.update(topics.split())
            con.close()
        self.assertEqual(set(taxonomy()) - covered - {"street_parking"}, set())

    def test_keywords_detect_their_topic(self):
        for topic, spec in taxonomy().items():
            for kw in spec["keywords"]:
                self.assertIn(topic, detect_topics(f"I have a problem: {kw}."), (topic, kw))


if __name__ == "__main__":
    unittest.main()


class TestStructuredFacts(TestBase):
    """Exact numbers live in data/structured/property_facts.db and are queried with SQL, not embeddings."""

    TODAY = date(2026, 10, 17)

    def test_expired_offer_is_excluded(self):
        from structured.query import fee_schedule
        codes_now = {f["fee_code"] for f in fee_schedule("P-NYC-002", self.TODAY)}
        codes_then = {f["fee_code"] for f in fee_schedule("P-NYC-002", date(2025, 9, 15))}
        self.assertNotIn("security_deposit_special", codes_now)
        self.assertIn("security_deposit_special", codes_then)

    def test_monthly_cost_is_rent_plus_required_flat_fees(self):
        from structured.query import monthly_costs
        studio = next(c for c in monthly_costs("P-NYC-003", self.TODAY) if c["unit_type"] == "Studio")
        self.assertEqual(studio["required_monthly_fees"], 100 + 5 + 45)  # amenity + billing + water
        self.assertEqual(studio["total_min"], 3413 + 150)

    def test_pet_and_optional_charges_not_in_required_totals(self):
        from structured.query import monthly_costs
        for pid in ("P-SF-001", "P-SF-003"):
            for c in monthly_costs(pid, self.TODAY):
                names = {n for n, _ in c["fees"]}
                self.assertFalse(names & {"Pet rent", "Underground parking", "Underground garage parking"}, names)

    def test_move_in_estimate_adds_up(self):
        from structured.query import move_in_cost
        est = move_in_cost("P-SF-003", "1 Bedroom", pets=2, as_of=self.TODAY)
        self.assertEqual(est["total"], 3450 + 1000 + 55 + 2 * 300)

    def test_sql_is_read_only(self):
        import sqlite3
        from structured.query import sql
        with self.assertRaises(sqlite3.OperationalError):
            sql("DELETE FROM fees")
        self.assertGreater(len(sql("SELECT * FROM v_monthly_costs")), 0)

    def test_leases_follow_building_pricing(self):
        from structured.query import sql
        bad = sql("""SELECT l.lease_id FROM leases l JOIN units u USING (unit_id)
                     JOIN unit_types t ON t.property_id = u.property_id AND t.unit_type = u.unit_type
                     WHERE l.monthly_rent > t.rent_max
                        OR (l.lease_type = 'market' AND l.monthly_rent < t.rent_min)""")
        self.assertEqual(bad, [])

    def test_lease_deposits_follow_fee_policy(self):
        from structured.query import sql
        bad = sql("""SELECT l.lease_id FROM leases l JOIN units u USING (unit_id)
                     JOIN fees f ON f.property_id = u.property_id AND f.fee_code = 'security_deposit'
                     WHERE l.security_deposit != CAST(CASE WHEN f.basis = 'months_of_rent'
                                                     THEN f.amount * l.monthly_rent ELSE f.amount END AS INTEGER)""")
        self.assertEqual(bad, [])

    def test_listing_facts_have_sources(self):
        from structured.query import sql
        for table in ("fees", "unit_types", "pet_policies", "parking", "utilities", "amenities"):
            rows = sql(f"SELECT * FROM {table} WHERE provenance = 'listing' AND (source_url IS NULL OR source_url = '')")
            self.assertEqual(rows, [], table)

    def test_amenity_fee_links_resolve(self):
        from structured.query import sql
        self.assertEqual(sql("""SELECT a.amenity_id FROM amenities a LEFT JOIN fees f USING (fee_id)
                                WHERE a.fee_id IS NOT NULL AND f.fee_id IS NULL"""), [])


class TestBuildingGuides(TestBase):
    TODAY = date(2026, 10, 17)

    def test_no_dollar_amounts_in_prose(self):
        from rag.common import BUILDINGS_DIR, POLICY_DIR
        for path in list(POLICY_DIR.rglob("*.md")) + list(BUILDINGS_DIR.glob("*.md")):
            self.assertNotIn("$", path.read_text(), path)

    def test_guides_point_to_fees_that_exist(self):
        from synthetic.profiles import PROFILES
        from rag.common import BUILDINGS_DIR
        for pid, prof in PROFILES.items():
            text = (BUILDINGS_DIR / f"{pid}.md").read_text()
            for f in prof["fees"]:
                if f["category"] == "pet":
                    self.assertIn(f["fee_name"].lower(), text, (pid, f["fee_code"]))

    def test_guide_utilities_match_database(self):
        from structured.query import utilities
        from rag.common import BUILDINGS_DIR
        words = {"included": "included in rent", "tenant_direct": "paid by you directly",
                 "billed_back": "billed by management"}
        for pid in ("P-NYC-001", "P-SF-002"):
            text = (BUILDINGS_DIR / f"{pid}.md").read_text()
            for u in utilities(pid):
                self.assertIn(words[u["responsibility"]], text, (pid, u["utility"]))

    def test_expired_notices_are_not_retrieved(self):
        summer = search_policies("concert at the oval", "P-NYC-001", topics=["amenities"], k=50,
                                 today=date(2026, 7, 10))
        autumn = search_policies("concert at the oval", "P-NYC-001", topics=["amenities"], k=50, today=self.TODAY)
        self.assertTrue(any("Summer concert" in h.title for h in summer))
        self.assertFalse(any("Summer concert" in h.title for h in autumn))

    def test_current_notice_is_retrieved(self):
        hits = search_policies("is the heat going to be off", "P-NYC-001", today=self.TODAY, k=10)
        self.assertTrue(any("Steam system maintenance" in h.title for h in hits), [h.title for h in hits])

    def test_guides_only_for_own_property(self):
        for h in search_policies("packages parking pets amenities", "P-SF-002", k=50, today=self.TODAY,
                                 topics=["amenities", "parking", "pets"]):
            if h.meta["doc_type"] == "building_guide":
                self.assertEqual(h.meta["doc_id"], "building-p-sf-002")


class TestFactsInContext(TestBase):
    TODAY = date(2026, 10, 17)

    def test_fee_question_gets_exact_facts(self):
        ctx = build_context("how much is the pet fee for my dog?", "P-SF-003", "P-SF-003-2A", today=self.TODAY)
        text = render_context(ctx)
        self.assertIn("Pet fee: $300 per pet", text)
        self.assertIn("FACTS", text)

    def test_garbage_fee_differs_by_city(self):
        sf = render_context(build_context("is there a garbage fee?", "P-SF-001", today=self.TODAY))
        ny = render_context(build_context("is there a garbage fee?", "P-NYC-002", today=self.TODAY))
        self.assertIn("Trash and recycling fee: $25", sf)
        self.assertIn("trash: included", ny)
        self.assertNotIn("Trash and recycling fee", ny)

    def test_maintenance_question_has_no_facts(self):
        ctx = build_context("my radiator is cold", "P-NYC-001", today=self.TODAY)
        self.assertEqual(ctx["facts"], [])

    def test_resident_sees_own_lease(self):
        ctx = build_context("when does my lease end and what is my rent?", "P-NYC-003", "P-NYC-003-2A",
                            today=self.TODAY)
        self.assertEqual(ctx["facts"][0]["kind"], "lease")
