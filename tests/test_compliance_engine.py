import unittest

from types import SimpleNamespace as NS

from compliance_engine import Violation, check_query, make_llm_classifier
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



class TestLLMStage(unittest.TestCase):
    def test_classifier_runs_only_on_stage_one_hits_and_makes_the_call(self):
        calls = []
        def classify(text, candidates):
            calls.append(candidates)
            return {"violation": "elevator" not in text, "category": candidates[0], "reason": "targets a group"}
        self.assertEqual(check_query(convert_message("My radiator is broken."), classify), [])
        self.assertEqual(calls, [])  # no protected class mentioned: no model call
        # the regex rule alone flags this behaviour complaint; the classifier clears it
        self.assertEqual(check_query(convert_message("The children in this building keep breaking the elevator"),
                                     classify), [])
        self.assertEqual(check_query(convert_message("Is it true that seniors are bad tenants?"), classify),
                         [Violation("fair_housing", "age", ("seniors", "targets a group"), "llm")])  # no regex cue
        self.assertEqual(calls, [["familial_status"], ["age"]])

    def test_failed_classifier_falls_back_to_the_regex_rule(self):
        text = "Where can i find a community without any African Americans?"
        self.assertEqual(check_query(convert_message(text), lambda *_: None),
                         [Violation("fair_housing", "race", ("african americans", "without any african americans"))])

    def test_llm_classifier_parses_replies_and_never_raises(self):
        def client(reply):
            def create(**request):
                requests.append(request)
                if isinstance(reply, Exception):
                    raise reply
                return NS(output_text=reply)
            return NS(responses=NS(create=create))
        requests, ok = [], {"violation": True, "category": "race", "reason": "excludes a race"}
        classify = make_llm_classifier(client('```json\n{"violation": true, "category": "race", '
                                              '"reason": "excludes a race"}\n```'), model="small")
        self.assertEqual(classify("a community without any african americans", ["race"]), ok)
        self.assertEqual((requests[0]["model"], requests[0]["reasoning"]), ("small", {"effort": "low"}))
        self.assertIn("Possible classes: race", requests[0]["input"])
        for reply in ["not json", '{"violation": "maybe"}', '{"category": "race"}', RuntimeError("API down")]:
            self.assertIsNone(make_llm_classifier(client(reply), model="small")("x", ["race"]), reply)


if __name__ == "__main__":
    unittest.main()
