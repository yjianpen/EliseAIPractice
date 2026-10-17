import unittest
from types import SimpleNamespace as NS

from agent import respond
from conversation_memory import ConversationMemory
from llm_decide import make_openai_decide


def recording_client(*answers):
    """Fake OpenAI client: replies with the given answers in order and records every prompt it was sent."""
    replies, prompts = iter(answers), []

    def create(**kwargs):
        prompts.append(kwargs["input"])
        return NS(output=[], output_text=next(replies), usage=NS(total_tokens=10))
    return NS(responses=NS(create=create)), prompts


class TestAgentMemory(unittest.TestCase):
    def setUp(self):
        self.memory = ConversationMemory()
        self.client, self.prompts = recording_client("Renewals go out 90 days early.", "It ends Jan 31.", "Hi!")
        self.decide = make_openai_decide(client=self.client, model="test", memory=self.memory)

    def test_second_message_sees_first_exchange(self):
        respond("When do lease renewals go out?", "T-1", self.memory, self.decide)
        respond("And when does my lease end?", "T-1", self.memory, self.decide)
        second = [(m["role"], m["content"]) for m in self.prompts[1][0:2]]
        self.assertEqual(second, [("user", "When do lease renewals go out?"),
                                  ("assistant", "Renewals go out 90 days early.")])
        self.assertEqual(len(self.memory.recent("T-1")), 4)

    def test_users_do_not_share_memory(self):
        respond("When do lease renewals go out?", "T-1", self.memory, self.decide)
        respond("Hello", "T-2", self.memory, self.decide)
        roles = [m["role"] for m in self.prompts[1]]
        self.assertEqual(roles, ["user"])  # T-2 sees no T-1 turns
        self.assertNotIn("renewals", str(self.prompts[1]).lower())

    def test_current_message_not_duplicated(self):
        respond("When do lease renewals go out?", "T-1", self.memory, self.decide)
        self.assertEqual(sum("renewals go out" in str(m["content"]) for m in self.prompts[0]), 1)


if __name__ == "__main__":
    unittest.main()
