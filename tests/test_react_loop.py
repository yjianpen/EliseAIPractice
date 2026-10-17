import unittest

from query_conversion import convert_message
from react_loop import Step, StopReason, run_react_loop

QUERY = convert_message("Hello, may I ask for my lease renewal? Is there any discount available")
TOOLS = {"lease_lookup": lambda unit_id: f"Lease for {unit_id} ends 2027-01-31",
         "broken": lambda: 1 / 0}


def scripted(*steps):
    """A fake decide() that returns the given steps in order."""
    it = iter(steps)
    return lambda query, history: next(it)


class TestReactLoop(unittest.TestCase):
    def test_tool_then_answer(self):
        decide = scripted(Step(action="lease_lookup", action_input={"unit_id": "3B"}, tokens_used=100),
                          Step(final_answer="Your lease ends Jan 31; renewal offers go out 90 days before.",
                               tokens_used=50))
        r = run_react_loop(QUERY, decide, TOOLS)
        self.assertEqual(r.stop_reason, StopReason.ANSWERED)
        self.assertEqual(r.steps[0].observation, "Lease for 3B ends 2027-01-31")
        self.assertEqual((len(r.steps), r.tokens_used), (2, 150))

    def test_max_attempts(self):
        r = run_react_loop(QUERY, lambda q, h: Step(action="lease_lookup", action_input={"unit_id": "1A"}),
                           TOOLS, max_attempts=3)
        self.assertEqual((r.stop_reason, len(r.steps), r.answer), (StopReason.MAX_ATTEMPTS, 3, None))

    def test_token_budget(self):
        r = run_react_loop(QUERY, lambda q, h: Step(action="lease_lookup", action_input={"unit_id": "1A"},
                                                    tokens_used=400), TOOLS, max_tokens=1000)
        self.assertEqual((r.stop_reason, len(r.steps)), (StopReason.TOKEN_BUDGET, 3))

    def test_timeout(self):
        ticks = iter(range(0, 1000, 10))  # fake clock: +10 s per reading
        r = run_react_loop(QUERY, lambda q, h: Step(action="lease_lookup", action_input={"unit_id": "1A"}),
                           TOOLS, timeout_s=25, clock=lambda: next(ticks))
        self.assertEqual(r.stop_reason, StopReason.TIMEOUT)

    def test_tool_errors_become_observations(self):
        decide = scripted(Step(action="nope"), Step(action="broken"), Step(final_answer="done"))
        r = run_react_loop(QUERY, decide, TOOLS)
        self.assertIn("unknown tool 'nope'", r.steps[0].observation)
        self.assertIn("broken failed", r.steps[1].observation)
        self.assertEqual(r.answer, "done")


if __name__ == "__main__":
    unittest.main()
