import unittest
from types import SimpleNamespace as NS

from llm_decide import build_input, make_openai_decide, parse_arguments
from query_conversion import convert_message
from react_loop import Step, StopReason, run_react_loop

QUERY = convert_message("May I ask for my lease renewal? Is there any discount available", unit_id="3B")
REASONING = NS(type="reasoning", id="rs_1")


def fake_client(*outputs):
    """Stands in for openai.OpenAI() (Responses API): returns the given outputs in order, 100 tokens each."""
    replies, self_inputs = iter(outputs), []

    def create(**kwargs):
        self_inputs.append(kwargs["input"])
        items, text = next(replies)
        return NS(output=items, output_text=text, usage=NS(total_tokens=100))
    return NS(responses=NS(create=create)), self_inputs


def tool_call(name, arguments, call_id="call_abc"):
    return ([REASONING, NS(type="function_call", call_id=call_id, name=name, arguments=arguments)], "")


class TestOpenAIDecide(unittest.TestCase):
    def test_tool_call_then_answer_through_the_loop(self):
        client, inputs = fake_client(tool_call("lease_lookup", '{"unit_id": "3B"}'),
                                     ([], "Your lease ends Jan 31."))
        tools = {"lease_lookup": lambda unit_id: f"Lease for {unit_id} ends 2027-01-31"}
        r = run_react_loop(QUERY, make_openai_decide(client=client, model="test-model"), tools)
        self.assertEqual((r.stop_reason, r.answer, r.tokens_used), (StopReason.ANSWERED, "Your lease ends Jan 31.", 200))
        self.assertEqual(r.steps[0].action_input, {"unit_id": "3B"})
        second = inputs[1]  # reasoning item and function call are replayed, then the tool output
        self.assertIs(second[-3], REASONING)
        self.assertEqual(second[-1], {"type": "function_call_output", "call_id": "call_abc",
                                      "output": "Lease for 3B ends 2027-01-31"})

    def test_dirty_arguments_are_repaired_or_reported(self):
        sql = {"sql": "SELECT 1"}
        for raw in ['{"sql": "SELECT 1"}', '```json\n{"sql": "SELECT 1"}\n```', 'Sure! {"sql": "SELECT 1"} done',
                    sql]:
            self.assertEqual(parse_arguments(raw), (sql, None), raw)
        self.assertEqual(parse_arguments('{"sql": "SELECT\n1"}')[0], {"sql": "SELECT\n1"})  # raw newline in string
        for raw in [None, "", "  "]:
            self.assertEqual(parse_arguments(raw), ({}, None))
        for raw in ['{"sql": "SELECT 1"', "not json", '["SELECT 1"]', '"SELECT 1"', "42", 7]:
            args, error = parse_arguments(raw)
            self.assertEqual(args, {}, raw)
            self.assertTrue(error.startswith("Error: the tool arguments were not a valid JSON object"), raw)

    def test_bad_arguments_do_not_kill_the_loop(self):
        client, inputs = fake_client(tool_call("lease_lookup", '{"unit_id": "3B"'),  # truncated JSON
                                     tool_call("lease_lookup", '{"unit_id": "3B"}', call_id="call_2"),
                                     ([], "Your lease ends Jan 31."))
        calls = []
        tools = {"lease_lookup": lambda unit_id: calls.append(unit_id) or f"Lease for {unit_id} ends 2027-01-31"}
        r = run_react_loop(QUERY, make_openai_decide(client=client, model="test-model"), tools)
        self.assertEqual((r.stop_reason, r.answer, calls), (StopReason.ANSWERED, "Your lease ends Jan 31.", ["3B"]))
        self.assertIn("not a valid JSON object", r.steps[0].observation)  # tool not run; model told to resend
        self.assertEqual(inputs[1][-1]["output"], r.steps[0].observation)

    def test_input_without_model_context_synthesizes_the_call(self):
        step = Step(action="lease_lookup", action_input={"unit_id": "3B"}, observation="ends 2027-01-31")
        items = build_input(QUERY, [step])
        self.assertIn("incident_type=leasing", items[0]["content"])
        self.assertEqual(items[1]["call_id"], items[2]["call_id"])
        self.assertEqual(items[2]["output"], "ends 2027-01-31")


if __name__ == "__main__":
    unittest.main()
