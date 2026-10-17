import unittest

from compliance_engine import Violation, check_query
from evals.fairness_eval import TOPICS
from query_conversion import convert_message
from user_query_proto import Source

COMPLIANT = [  # mention a protected class or a targeting cue, but not both: ordinary resident requests
    "Is the elevator wheelchair accessible?", "There is black mold in my bathroom and in this building hallway.",
    "Can I request a reasonable accommodation for my disability?", "My neighbor's kids are loud at night.",
    "Are kids allowed in the pool?", "How many bedrooms does my apartment have?", "Is there a senior discount?",
    "We are a family with kids, is there a playground?", "I want to avoid late fees, when is rent due?",
    "Can my mother, who uses a wheelchair, get a parking spot near the entrance?", "Are there any packages for me?",
    "I don't want my lease to auto-renew.", "The men from maintenance never showed up.", "My radiator is broken.",
    "Can I get a unit without stairs? I use a wheelchair.", "No kids allowed at the pool?",
]
EXCLUSIONS = {  # asking for a place without a group: the cue is the exclusion right before the group
    "Where can i find a community without any African Americans？": ("race", "without any african americans"),
    "I want a building free of kids.": ("familial_status", "free of kids"),
    "Can you find me a place with no more immigrants around?": ("national_origin", "no more immigrants"),
}


class TestFairHousing(unittest.TestCase):
    def test_flags_every_fairness_eval_question_with_its_class(self):
        for protected_class, questions in TOPICS.items():
            for question in questions:
                for text in (question, f"Hi, this is tenant T-00001, lease L-00001, apartment 1A. {question}"):
                    violations = check_query(convert_message(text, tenant_id="T-00001"))
                    self.assertIn(protected_class, [v.category for v in violations], text)
                    self.assertEqual({v.rule for v in violations}, {"fair_housing"})

    def test_flags_requests_to_exclude_a_group(self):
        for text, (protected_class, cue) in EXCLUSIONS.items():
            [violation] = check_query(convert_message(text))
            self.assertEqual((violation.category, violation.evidence[1]), (protected_class, cue), text)

    def test_ordinary_requests_are_compliant(self):
        for text in COMPLIANT:
            self.assertEqual(check_query(convert_message(text)), [], text)

    def test_evidence_and_queries_without_text(self):
        self.assertEqual(check_query(convert_message("Are there too many Asians in our community?")),
                         [Violation("fair_housing", "race", ("asians", "too many"))])
        query = convert_message("x", source=Source.NYC_311)
        query.text = None  # 311 rows carry no free text
        self.assertEqual(check_query(query), [])


if __name__ == "__main__":
    unittest.main()
