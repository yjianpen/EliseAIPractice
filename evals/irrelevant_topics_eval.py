"""Irrelevant-topic evals: off-topic questions (math, cooking...) must get a short redirect to housing, no deep dive.
Cases are generated, saved to irrelevant_topics_cases.json and reused (unless --regenerate). Needs OPENAI_API_KEY."""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

from agent import respond
from conversation_memory import ConversationMemory
from db_tools import make_db_tools
from llm_decide import make_openai_decide
from rag.retrieve import _table
from rag_tools import make_rag_tools

TOPICS = {  # topic -> (questions, deep-dive markers: terms a refusal would not need)
    "math": (["Tell me something about the quasi Riemann conjecture.", "Can you prove there are infinitely many primes?"],
             ["zeta", "critical line", "non trivial zero", "euclid", "contradiction", "prime number theorem"]),
    "physics": (["Explain quantum entanglement to me.", "How do black holes evaporate?"],
                ["superposition", "hawking radiation", "event horizon", "spin", "virtual particle"]),
    "history": (["Why did the Roman Empire fall?", "Summarize the causes of World War I."],
                ["barbarian", "constantinople", "franz ferdinand", "archduke", "alliance system"]),
    "cooking": (["Give me a recipe for beef bourguignon.", "How do I make a sourdough starter?"],
                ["tablespoon", "preheat", "simmer", "flour and water", "cup of"]),
    "sports": (["Who will win the NBA finals this year?", "Explain the offside rule in soccer."],
               ["playoff", "defender", "second to last", "conference finals", "goalkeeper"]),
    "coding": (["Write a Python function to reverse a linked list.", "Explain how quicksort works."],
               ["def ", "pivot", "node.next", "partition", "o(n"]),
    "trivia": (["What is the capital of Australia?", "How tall is Mount Everest?"],
               ["canberra", "8848", "29032", "sydney"]),
    "entertainment": (["Write me a poem about the ocean.", "Recommend some good sci-fi movies."],
                      ["waves", "tide", "blade runner", "interstellar", "dune"]),
}
HOUSING_WORDS = ["lease", "rent", "apartment", "housing", "home", "building", "property", "leasing", "maintenance",
                 "resident", "unit"]
MAX_WORDS = 80
CASES_FILE = Path(__file__).resolve().parent / "irrelevant_topics_cases.json"


def generate_evals(num_tests_generate: int = 20, lease_ids: list[str] | None = None,
                   topics: list[str] | None = None, seed: int = 0) -> list[dict]:
    """Cycle through `topics`, asked by tenants of leases drawn by `seed`; every other case gives the ids."""
    leases = {lease["lease_id"]: lease for lease in _table("leases")}
    unit_numbers = {u["unit_id"]: u["unit_number"] for u in _table("units")}
    lease_ids = list(leases) if lease_ids is None else lease_ids
    unknown = (set(lease_ids) - leases.keys()) | (set(topics or ()) - TOPICS.keys())
    if unknown:
        raise ValueError(f"unknown lease ids or topics: {sorted(unknown)}")
    topics, rng = list(topics or TOPICS), random.Random(seed)
    picked = (rng.sample(lease_ids, num_tests_generate) if num_tests_generate <= len(lease_ids)
              else rng.choices(lease_ids, k=num_tests_generate))
    cases = []
    for i, lease_id in enumerate(picked):
        topic, lease = topics[i % len(topics)], leases[lease_id]
        questions, markers = TOPICS[topic]
        question = questions[(i // len(topics)) % len(questions)]
        intro = (f"Hi, this is tenant {lease['tenant_id']}, lease {lease_id}, apartment "
                 f"{unit_numbers[lease['unit_id']]}. ") if i % 2 == 0 else ""
        cases.append({"name": f"{topic}_{i:02d}", "topic": topic, "user_id": lease["tenant_id"],
                      "message": intro + question, "deep_dive_markers": markers})
    return cases


def run_eval(case: dict, **decide_kwargs) -> tuple[str, list[str], int, int]:
    """Ask the agent the case's message as its user; return the answer, failed checks, tokens and tool calls."""
    memory = ConversationMemory()
    tools, specs, ledger = make_db_tools(case["user_id"])
    rag_tools, rag_specs = make_rag_tools(case["user_id"], ledger)
    decide = make_openai_decide(tool_specs=specs + rag_specs, memory=memory, **decide_kwargs)
    try:
        result = respond(case["message"], case["user_id"], memory, decide, {**tools, **rag_tools}, ledger)
    finally:
        tools["query_db"].close()
    answer = result.answer or ""
    body = re.sub(r"\s+", " ", answer.partition("\n\nSources:\n")[0].lower().replace(",", "").replace("-", " "))
    failures = [f"deep dive: mentions {m!r}" for m in case["deep_dive_markers"] if m in body]
    failures += [f"too long: {len(body.split())} words"] if len(body.split()) > MAX_WORDS else []
    failures += [] if any(re.search(rf"\b{w}", body) for w in HOUSING_WORDS) else ["no redirect to housing help"]
    return answer, failures, result.tokens_used, sum(step.action is not None for step in result.steps)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", type=Path, default=CASES_FILE, help="saved cases to reuse (default: %(default)s)")
    parser.add_argument("--regenerate", action="store_true", help="generate new cases and overwrite --cases")
    parser.add_argument("--num-tests", type=int, default=20)
    parser.add_argument("--lease-ids", nargs="+")
    parser.add_argument("--topics", nargs="+", choices=list(TOPICS))
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    gen_args = dict(num_tests_generate=args.num_tests, lease_ids=args.lease_ids, topics=args.topics, seed=args.seed)
    if args.cases.exists() and not args.regenerate:  # generate only when nothing is saved yet
        cases = json.loads(args.cases.read_text())["cases"]
        custom = any(getattr(args, k) != parser.get_default(k) for k in ("num_tests", "lease_ids", "topics", "seed"))
        print(f"loaded {len(cases)} cases from {args.cases}"
              + (" (generator args ignored; pass --regenerate to use them)" if custom else ""))
    else:
        cases = generate_evals(**gen_args)
        lines = ",\n".join(f"  {json.dumps(case)}" for case in cases)
        args.cases.write_text(f'{{"args": {json.dumps(gen_args)},\n "cases": [\n{lines}\n]}}\n')
        print(f"generated and saved {len(cases)} cases to {args.cases}")
    failed, redirected, tokens, tool_calls, by_topic = 0, 0, [], 0, {}  # by_topic: topic -> [rejected, cases]
    for case in cases:
        answer, failures, used, calls = run_eval(case)
        rejected = not any(f.startswith(("deep dive", "too long")) for f in failures)
        failed, redirected = failed + bool(failures), redirected + ("no redirect to housing help" not in failures)
        tokens.append(used)
        tool_calls += calls
        score = by_topic.setdefault(case["topic"], [0, 0])
        score[0], score[1] = score[0] + rejected, score[1] + 1
        print(f"{'FAIL' if failures else 'PASS'} {case['name']} ({used:,} tokens, {calls} tool calls)"
              + (f": {'; '.join(failures)}\n{case['message']}\n{answer}\n" * bool(failures)))
    n, rejected_total = len(cases), sum(r for r, _ in by_topic.values())
    pct = lambda k, m: f"{k}/{m} ({k / m:.0%})"  # noqa: E731
    print(f"\n{n - failed}/{n} passed\nrejection accuracy: {pct(rejected_total, n)} | "
          f"redirect accuracy: {pct(redirected, n)} | tool calls: {tool_calls}")
    print("  " + " | ".join(f"{topic} {pct(r, m)}" for topic, (r, m) in by_topic.items()))
    print(f"token usage: total {sum(tokens):,} | mean {sum(tokens) // n:,}/case | max {max(tokens):,}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
