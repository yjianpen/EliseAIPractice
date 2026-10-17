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
        for pid in ("P-SF-001", "P-SF-002"):  # Bayline
            for h in search_policies("heat leak mold noise pests entry", pid, k=50, topics=list(taxonomy())):
                self.assertNotIn("lumen", h.meta["doc_id"], (pid, h.id))
        for pid in ("P-NYC-001", "P-SF-003"):  # Lumen
            for h in search_policies("heat leak mold noise pests entry", pid, k=50, topics=list(taxonomy())):
                self.assertNotIn("bayline", h.meta["doc_id"], (pid, h.id))

    def test_same_company_different_city_sections(self):
        sf = [h.title for h in search_policies("radiator is cold", "P-SF-003", k=10)]
        ny = [h.title for h in search_policies("radiator is cold", "P-NYC-001", k=10)]
        self.assertTrue(any("San Francisco" in t for t in sf), sf)
        self.assertFalse(any("New York City" in t for t in sf), sf)
        self.assertTrue(any("New York City" in t for t in ny), ny)

    def test_only_own_property_addendum(self):
        for h in search_policies("quiet hours noise", "P-NYC-002", k=20):
            if h.meta["scope"] == "property":
                self.assertEqual(h.meta["doc_id"], "addendum-p-nyc-002")

    def test_addendum_reflects_property_facts(self):
        hits = search_policies("what are the quiet hours", "P-NYC-003", k=5)
        addendum = next(h for h in hits if h.meta["scope"] == "property")
        self.assertIn("11:00 PM", addendum.text)  # Hudson Yards Tower differs from the 10 PM default

    def test_irrelevant_question_returns_nothing(self):
        self.assertEqual(search_policies("what time does the gym open", "P-NYC-003"), [])

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
        ctx = build_context("peeling paint, my 2 year old child lives here", "P-NYC-001", "P-NYC-001-2A")
        self.assertIn("nyc-lead-ll1", [h["id"] for h in ctx["laws"]])
        self.assertTrue(any(c["law_id"] == "nyc-lead-ll1" for c in ctx["compliance"]))


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
