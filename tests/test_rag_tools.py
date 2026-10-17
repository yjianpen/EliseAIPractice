import unittest
from types import SimpleNamespace as NS

from agent import respond
from conversation_memory import ConversationMemory
from llm_decide import make_openai_decide
from rag_tools import make_rag_tools

TENANT = "T-00329"  # leases a unit at P-NYC-003 (Lumen Park Residential, New York)
SMOKE = "can i uninstall smoke detector or fire alert by myself?"


class TestSearchKnowledge(unittest.TestCase):
    def test_cites_every_passage_it_returned(self):
        ledger = []
        tools, specs = make_rag_tools(TENANT, ledger)
        out = tools["search_knowledge"](SMOKE)
        self.assertEqual((specs[0]["type"], specs[0]["name"]), ("function", "search_knowledge"))
        self.assertIn("Smoke and carbon monoxide alarms", out)
        sources = {e["source"].split(" ")[0] for e in ledger}
        self.assertEqual(sources, {"policies.db", "laws.db"})
        for e in ledger:  # each citation is a passage the model was actually shown
            self.assertIn(e["columns"][0].split(" <")[0].split(" > ")[-1], out)
        self.assertIn("nyc-smoke-co-alarms", [e["ids"][0] for e in ledger])
        self.assertIn("knowledge/policies/companies/C-LUMEN.md", ledger[0]["source"])

    def test_unknown_resident_gets_error_and_no_citations(self):
        ledger = []
        tools, _ = make_rag_tools("T-99999", ledger)
        self.assertTrue(tools["search_knowledge"](SMOKE).startswith("Error"))
        self.assertEqual(ledger, [])

    def test_agent_answer_ends_with_rag_sources(self):
        call = NS(type="function_call", call_id="call_1", name="search_knowledge",
                  arguments=f'{{"question": "{SMOKE}"}}')
        replies = iter([([call], ""), ([], "No, please don't remove the alarm yourself.")])
        client = NS(responses=NS(create=lambda **kw: (lambda items, text: NS(
            output=items, output_text=text, usage=NS(total_tokens=10)))(*next(replies))))
        ledger = []
        tools, specs = make_rag_tools(TENANT, ledger)
        memory = ConversationMemory()
        decide = make_openai_decide(tool_specs=specs, client=client, model="test", memory=memory)
        r = respond(SMOKE, TENANT, memory, decide, tools, ledger)
        answer, sources = r.answer.split("\n\nSources:\n")
        self.assertEqual(answer, "No, please don't remove the alarm yourself.")
        self.assertIn("policies.db (knowledge/policies/companies/C-LUMEN.md): guidebook-c-lumen#18", sources)
        self.assertIn("laws.db (NYC Admin. Code Title 28, Art. 312", sources)
        self.assertEqual(memory.recent(TENANT)[-1].text, answer)  # memory keeps the uncited answer


if __name__ == "__main__":
    unittest.main()
