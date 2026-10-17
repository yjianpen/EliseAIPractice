import unittest
import warnings
from types import SimpleNamespace as NS

from llm_decide import create_with_fallbacks, make_openai_decide


class FakeAPIError(Exception):
    def __init__(self, message, status_code=400, param=None):
        super().__init__(message)
        self.status_code, self.param = status_code, param


def scripted_client(*outcomes):
    """Fake Responses client: each call pops the next outcome (an exception to raise, or a response)."""
    calls, queue = [], list(outcomes)

    def create(**kwargs):
        calls.append(kwargs)
        outcome = queue.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    return NS(responses=NS(create=create)), calls


OK = NS(output=[], output_text="ok", usage=NS(total_tokens=1))
REQUEST = {"input": [], "reasoning": {"effort": "low"}, "tools": [{"type": "function", "name": "query_db"}]}


class TestModelFallbacks(unittest.TestCase):
    def setUp(self):  # silence the fallback warnings for this test only
        self.enterContext(warnings.catch_warnings())
        warnings.simplefilter("ignore")

    def test_reasoning_unsupported_retries_without_reasoning(self):
        client, calls = scripted_client(FakeAPIError("Function tools with reasoning_effort are not supported",
                                                     param="reasoning_effort"), OK)
        self.assertIs(create_with_fallbacks(client, ["gpt-6-luna"], REQUEST), OK)
        self.assertIn("reasoning", calls[0])
        self.assertNotIn("reasoning", calls[1])
        self.assertEqual(calls[1]["model"], "gpt-6-luna")

    def test_retired_model_moves_to_next_fallback(self):
        client, calls = scripted_client(FakeAPIError("The model does not exist", status_code=404), OK)
        create_with_fallbacks(client, ["gpt-6-luna", "gpt-5.6-luna"], REQUEST)
        self.assertEqual([c["model"] for c in calls], ["gpt-6-luna", "gpt-5.6-luna"])

    def test_other_errors_are_not_hidden(self):
        client, _ = scripted_client(FakeAPIError("Incorrect API key provided", status_code=401))
        with self.assertRaises(FakeAPIError):
            create_with_fallbacks(client, ["gpt-6-luna", "gpt-5.6-luna"], REQUEST)

    def test_all_models_failing_raises_the_last_error(self):
        client, calls = scripted_client(FakeAPIError("model gone", status_code=404),
                                        FakeAPIError("model gone too", status_code=404))
        with self.assertRaisesRegex(FakeAPIError, "gone too"):
            create_with_fallbacks(client, ["a", "b"], REQUEST)
        self.assertEqual(len(calls), 2)

    def test_old_sdk_without_responses_api_fails_clearly(self):
        with self.assertRaisesRegex(RuntimeError, "pip install -U"):
            make_openai_decide(client=NS(chat=None), model="test")


if __name__ == "__main__":
    unittest.main()
