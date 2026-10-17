import unittest
from datetime import datetime, timedelta

from conversation_memory import ConversationMemory


class FakeClock:
    def __init__(self):
        self.now = datetime(2026, 10, 17, 9, 0)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


class TestConversationMemory(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.memory = ConversationMemory(clock=self.clock)

    def test_separated_by_user(self):
        self.memory.add("T-1", "user", "Is there a lease renewal discount?")
        self.memory.add("T-2", "user", "My sink is leaking")
        self.assertEqual([t.text for t in self.memory.recent("T-1")], ["Is there a lease renewal discount?"])
        self.assertEqual([t.text for t in self.memory.recent("T-2")], ["My sink is leaking"])
        self.assertEqual(self.memory.recent("T-unknown"), [])

    def test_two_hour_sliding_window(self):
        self.memory.add("T-1", "user", "old question")
        self.clock.advance(minutes=90)
        self.memory.add("T-1", "assistant", "newer answer")
        self.clock.advance(minutes=31)  # first turn is now 2h01m old, second is 31m old
        self.assertEqual([t.text for t in self.memory.recent("T-1")], ["newer answer"])

    def test_turn_exactly_at_window_edge_is_kept(self):
        self.memory.add("T-1", "user", "edge")
        self.clock.advance(hours=2)
        self.assertEqual(len(self.memory.recent("T-1")), 1)

    def test_expired_users_are_forgotten(self):
        self.memory.add("T-1", "user", "hello")
        self.clock.advance(hours=3)
        self.assertEqual(self.memory.recent("T-1"), [])
        self.assertNotIn("T-1", self.memory._turns)

    def test_per_user_turn_cap(self):
        memory = ConversationMemory(max_turns_per_user=3, clock=self.clock)
        for i in range(5):
            memory.add("T-1", "user", f"msg {i}")
        self.assertEqual([t.text for t in memory.recent("T-1")], ["msg 2", "msg 3", "msg 4"])


if __name__ == "__main__":
    unittest.main()
