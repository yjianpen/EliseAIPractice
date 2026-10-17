import csv
import unittest
from types import SimpleNamespace as NS

from agent import respond
from conversation_memory import ConversationMemory
from db_tools import DATA_DIR, make_db_tools
from llm_decide import make_openai_decide

LEASE = next(csv.DictReader((DATA_DIR / "leases.csv").open()))  # first lease in the synthetic data


class TestQueryDb(unittest.TestCase):
    def setUp(self):
        tools, self.specs = make_db_tools(LEASE["tenant_id"])
        self.query = tools["query_db"]

    def test_reads_own_lease(self):
        self.assertIn(LEASE["monthly_rent"], self.query("SELECT monthly_rent FROM my_lease"))

    def test_only_own_rows_exist(self):
        out = self.query("SELECT DISTINCT tenant_id FROM my_lease UNION SELECT DISTINCT tenant_id FROM my_work_orders")
        self.assertEqual(out.splitlines()[1:], [LEASE["tenant_id"]])
        cte = "WITH x AS (SELECT * FROM my_lease) SELECT count(*) FROM x"  # CTEs can only see own rows
        self.assertEqual(self.query(cte).splitlines()[1], "1")

    def test_read_only_and_no_other_tables(self):
        for sql in ["SELECT * FROM leases", "SELECT * FROM tenants", "UPDATE my_lease SET monthly_rent = 1",
                    "DELETE FROM my_lease", "PRAGMA table_info(my_lease)", "ATTACH DATABASE 'x.db' AS x",
                    "SELECT 1; DROP TABLE my_lease"]:
            self.assertTrue(self.query(sql).startswith("Error"), sql)

    def test_spec_lists_views_and_columns(self):
        self.assertEqual((self.specs[0]["type"], self.specs[0]["name"]), ("function", "query_db"))
        description = self.specs[0]["description"]
        self.assertIn("my_lease(lease_id", description)
        self.assertIn("monthly_rent", description)

    def test_agent_answers_rent_from_db(self):
        call = NS(type="function_call", call_id="call_1", name="query_db",
                  arguments='{"sql": "SELECT monthly_rent FROM my_lease"}')
        replies = iter([([call], ""), ([], "Your monthly rent is on file.")])
        client = NS(responses=NS(create=lambda **kw: (lambda items, text: NS(
            output=items, output_text=text, usage=NS(total_tokens=10)))(*next(replies))))
        tools, specs = make_db_tools(LEASE["tenant_id"])
        memory = ConversationMemory()
        decide = make_openai_decide(tool_specs=specs, client=client, model="test", memory=memory)
        r = respond("How much is my monthly rent?", LEASE["tenant_id"], memory, decide, tools)
        self.assertIn(LEASE["monthly_rent"], r.steps[0].observation)
        self.assertEqual(r.answer, "Your monthly rent is on file.")


if __name__ == "__main__":
    unittest.main()
