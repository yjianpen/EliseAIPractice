import unittest

from query_conversion import classify_incident, convert_message, detect_intent
from user_query_proto import Channel, Intent, ReporterRole, Urgency


class TestQueryConversion(unittest.TestCase):
    def test_lease_renewal_question(self):
        text = "Hello, may I ask for my lease renewal? Is there any discount avaialble"
        q = convert_message(text, channel=Channel.SMS, tenant_id="T-00001")
        self.assertEqual((q.incident_type, q.category, q.urgency), ("leasing", "leasing_costs", Urgency.ROUTINE))
        self.assertEqual(q.intent, Intent.ASK_QUESTION)
        self.assertEqual(q.reporter_role, ReporterRole.TENANT)
        self.assertEqual(q.text, text)

    def test_most_urgent_topic_wins(self):
        self.assertEqual(classify_incident("I smell gas and my rent is late")[0], "gas")
        self.assertEqual(classify_incident("water leaked in our building last night")[2], Urgency.URGENT)

    def test_intents(self):
        self.assertEqual(detect_intent("There are mice in my kitchen."), Intent.REPORT_ISSUE)
        self.assertEqual(detect_intent("Any update on my leak repair?"), Intent.FOLLOW_UP)
        self.assertEqual(detect_intent("This is unacceptable, no heat for 3 days"), Intent.COMPLAINT)

    def test_unknown_topic(self):
        self.assertEqual(classify_incident("Hi there")[0], "other")


if __name__ == "__main__":
    unittest.main()
