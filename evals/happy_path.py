"""Happy-path evals: a resident identifies themselves fully and asks about one fact on file.

Cases are generated from the synthetic data (data/synthetic/leases.csv, units.csv), never handwritten: each one
asks a TOPICS question as the lease's tenant, giving tenant id, lease id and apartment number, and expects the
value on file plus a citation of the record it came from. Runs the real agent (OpenAI model + query_db +
search_knowledge), so it needs OPENAI_API_KEY (see config.py). The run ends with two metrics: answer accuracy
(overall and per topic, plus citation accuracy) and token usage (total, mean and max per case).
Generated cases are saved to evals/happy_path_cases.json and reused on later runs, so every run asks the same
questions about the same leases; pass --regenerate (with any generator args) to draw a new set and overwrite it.
  python -m evals.happy_path                  # reuse the saved cases (generates 40 over all topics if none saved)
  python -m evals.happy_path --regenerate --num-tests 5 --topics monthly_rent --lease-ids L-00001 L-00002
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from datetime import date
from pathlib import Path

from agent import respond
from conversation_memory import ConversationMemory
from db_tools import make_db_tools
from llm_decide import make_openai_decide
from rag.retrieve import _table
from rag_tools import make_rag_tools

TOPICS = {  # topic -> (question, source table, column whose value the answer must state)
    "monthly_rent": ("What is my monthly rent?", "leases", "monthly_rent"),
    "security_deposit": ("How much was my security deposit?", "leases", "security_deposit"),
    "lease_start_date": ("When did my lease start?", "leases", "start_date"),
    "lease_end_date": ("When does my lease end?", "leases", "end_date"),
    "lease_type": ("What type of lease do I have?", "leases", "lease_type"),
    "bedrooms": ("How many bedrooms does my apartment have?", "units", "bedrooms"),
    "square_footage": ("How many square feet is my apartment?", "units", "sqft"),
}
CASES_FILE = Path(__file__).resolve().parent / "happy_path_cases.json"
NUMBER_WORDS = "zero one two three four five six".split()


def generate_evals(num_tests_generate: int = 40, lease_ids: list[str] | None = None,
                   topics: list[str] | None = None, seed: int = 0) -> list[dict]:
    """Build eval cases, cycling through `topics` over leases drawn (deterministically, by `seed`) from `lease_ids`."""
    leases, units = {lease["lease_id"]: lease for lease in _table("leases")}, {}
    for u in _table("units"):
        units.setdefault(u["unit_id"], []).append(u)
    if lease_ids is None:  # units.csv has a few unit ids with conflicting rows: no single right answer there
        lease_ids = [i for i, lease in leases.items() if len(units[lease["unit_id"]]) == 1]
    unknown = (set(lease_ids) - leases.keys()) | (set(topics or ()) - TOPICS.keys())
    if unknown:
        raise ValueError(f"unknown lease ids or topics: {sorted(unknown)}")
    topics, rng = list(topics or TOPICS), random.Random(seed)
    picked = (rng.sample(lease_ids, num_tests_generate) if num_tests_generate <= len(lease_ids)
              else rng.choices(lease_ids, k=num_tests_generate))
    cases = []
    for i, lease_id in enumerate(picked):
        topic, lease = topics[i % len(topics)], leases[lease_id]
        question, table, column = TOPICS[topic]
        unit = units[lease["unit_id"]][0]
        row, record_id = (lease, lease_id) if table == "leases" else (unit, unit["unit_id"])
        value = row[column]
        if column.endswith("_date"):  # accept the usual ways of writing a date
            d = date.fromisoformat(value)
            expected = [value, f"{d:%B} {d.day} {d.year}", f"{d:%b} {d.day} {d.year}", f"{d.month}/{d.day}/{d.year}"]
        elif column == "bedrooms":
            expected = [f"{value} bedroom", f"{NUMBER_WORDS[int(value)]} bedroom"] + (["studio"] * (value == "0"))
        else:
            expected = [value]
        cases.append({"name": f"{topic}_{lease_id}", "user_id": lease["tenant_id"],
                      "message": f"Hi, this is tenant {lease['tenant_id']}, lease {lease_id}, apartment "
                                 f"{unit['unit_number']}. {question}",
                      "expect_any_of": expected, "expect_cited": [f"{table}.csv", record_id, column]})
    return cases


def load_or_generate_evals(path: Path = CASES_FILE, regenerate: bool = False, **generator_args) -> list[dict]:
    """Return the cases saved at `path`; generate (with `generator_args`) and save them only if none are saved yet
    or `regenerate` is set. Saved one case per line, with the args that produced them, so diffs stay readable."""
    if path.exists() and not regenerate:
        return json.loads(path.read_text())["cases"]
    cases = generate_evals(**generator_args)
    lines = ",\n".join(f"  {json.dumps(case)}" for case in cases)
    path.write_text(f'{{"args": {json.dumps(generator_args)},\n "cases": [\n{lines}\n]}}\n')
    return cases


def run_eval(case: dict, **decide_kwargs) -> tuple[str, list[str], int]:
    """Ask the agent the case's message as its user; return the cited answer, the failed checks and tokens used."""
    memory = ConversationMemory()
    tools, specs, ledger = make_db_tools(case["user_id"])
    rag_tools, rag_specs = make_rag_tools(case["user_id"], ledger)
    decide = make_openai_decide(tool_specs=specs + rag_specs, memory=memory, **decide_kwargs)
    try:
        result = respond(case["message"], case["user_id"], memory, decide, {**tools, **rag_tools}, ledger)
    finally:
        tools["query_db"].close()
    answer = result.answer or ""
    body, _, sources = answer.partition("\n\nSources:\n")
    norm = lambda s: re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", s.lower().replace(",", "").replace("-", " "))  # noqa: E731
    failures = [] if any(norm(e) in norm(body) for e in case["expect_any_of"]) else [
        f"answer lacks any of {case['expect_any_of']}"]
    failures += [f"sources lack {s!r}" for s in case["expect_cited"] if s not in sources]
    return answer, failures, result.tokens_used


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", type=Path, default=CASES_FILE, help="saved cases to reuse (default: %(default)s)")
    parser.add_argument("--regenerate", action="store_true", help="generate new cases and overwrite --cases")
    parser.add_argument("--num-tests", type=int, default=40)
    parser.add_argument("--lease-ids", nargs="+")
    parser.add_argument("--topics", nargs="+", choices=list(TOPICS))
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    reuse = args.cases.exists() and not args.regenerate
    gen_args = dict(num_tests_generate=args.num_tests, lease_ids=args.lease_ids, topics=args.topics, seed=args.seed)
    cases = load_or_generate_evals(args.cases, args.regenerate, **gen_args)
    custom = any(getattr(args, k) != parser.get_default(k) for k in ("num_tests", "lease_ids", "topics", "seed"))
    print(f"{'loaded' if reuse else 'generated and saved'} {len(cases)} cases {'from' if reuse else 'to'} {args.cases}"
          + (" (generator args ignored; pass --regenerate to use them)" if reuse and custom else ""))
    failed, tokens, by_topic, cited = 0, [], {}, 0  # by_topic: topic -> [answers correct, cases]
    for case in cases:
        answer, failures, used = run_eval(case)
        failed, cited = failed + bool(failures), cited + (not any(f.startswith("sources") for f in failures))
        tokens.append(used)
        score = by_topic.setdefault(case["name"].rsplit("_", 1)[0], [0, 0])
        score[0], score[1] = score[0] + (not any(f.startswith("answer") for f in failures)), score[1] + 1
        print(f"{'FAIL' if failures else 'PASS'} {case['name']} ({used:,} tokens)"
              + (f": {'; '.join(failures)}\n{answer}\n" * bool(failures)))
    n, correct = len(cases), sum(c for c, _ in by_topic.values())
    pct = lambda k, m: f"{k}/{m} ({k / m:.0%})"  # noqa: E731
    print(f"\n{n - failed}/{n} passed\nanswer accuracy: {pct(correct, n)} | citation accuracy: {pct(cited, n)}")
    print("  " + " | ".join(f"{topic} {pct(c, m)}" for topic, (c, m) in by_topic.items()))
    print(f"token usage: total {sum(tokens):,} | mean {sum(tokens) // n:,}/case | max {max(tokens):,}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
