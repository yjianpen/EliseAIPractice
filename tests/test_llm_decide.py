import unittest
from types import SimpleNamespace as NS

from llm_decide import build_messages, make_openai_decide
from query_conversion import convert_message
from react_loop import Step, StopReason, run_react_loop

QUERY = convert_message("May I ask for my lease renewal? Is there any discount available", unit_id="3B")


def fake_client(*messages):
    """Stands in for openai.OpenAI(): returns the given assistant messages in order, 100 tokens each."""
    replies = iter(messages)
    create = lambda **kwargs: NS(choices=[NS(message=next(replies))], usage=NS(total_tokens=100))
    return NS(chat=NS(completions=NS(create=create)))


def tool_call(name, arguments):
    return NS(content=None, tool_calls=[NS(function=NS(name=name, arguments=arguments))])


class TestOpenAIDecide(unittest.TestCase):
    def test_tool_call_then_answer_through_the_loop(self):
        client = fake_client(tool_call("lease_lookup", '{"unit_id": "3B"}'),
                             NS(content="Your lease ends Jan 31.", tool_calls=None))
        tools = {"lease_lookup": lambda unit_id: f"Lease for {unit_id} ends 2027-01-31"}
        r = run_react_loop(QUERY, make_openai_decide(client=client, model="test-model"), tools)
        self.assertEqual((r.stop_reason, r.answer, r.tokens_used), (StopReason.ANSWERED, "Your lease ends Jan 31.", 200))
        self.assertEqual(r.steps[0].action_input, {"unit_id": "3B"})

    def test_messages_replay_history(self):
        step = Step(action="lease_lookup", action_input={"unit_id": "3B"}, observation="ends 2027-01-31")
        msgs = build_messages(QUERY, [step])
        self.assertIn("incident_type=leasing", msgs[1]["content"])
        self.assertEqual(msgs[2]["tool_calls"][0]["id"], msgs[3]["tool_call_id"])
        self.assertEqual(msgs[3]["content"], "ends 2027-01-31")


if __name__ == "__main__":
    unittest.main()
