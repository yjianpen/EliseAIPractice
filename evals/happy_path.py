"""Happy-path eval: a resident identifies themselves fully and asks for their monthly rent.

Runs the real agent (OpenAI model + query_db + search_knowledge) and checks that the answer states the rent on
file in data/synthetic/leases.csv and cites the lease record it came from. Needs OPENAI_API_KEY (see config.py).
  python -m evals.happy_path
"""
from __future__ import annotations

import sys

from agent import respond
from conversation_memory import ConversationMemory
from db_tools import make_db_tools
from llm_decide import make_openai_decide
from rag_tools import make_rag_tools

EVALS = [  # expected values are copied from data/synthetic/leases.csv and units.csv
    {"name": "monthly_rent_with_ids", "user_id": "T-00001",
     "message": "Hi, this is tenant T-00001, lease L-00001, apartment 1A. What is my monthly rent?",
     "expect_in_answer": ["3320"], "expect_cited": ["leases.csv: L-00001", "monthly_rent"]},
]


def run_eval(case: dict, **decide_kwargs) -> tuple[str, list[str]]:
    """Ask the agent the case's message as its user; return the cited answer and the failed checks."""
    memory = ConversationMemory()
    tools, specs, ledger = make_db_tools(case["user_id"])
    rag_tools, rag_specs = make_rag_tools(case["user_id"], ledger)
    decide = make_openai_decide(tool_specs=specs + rag_specs, memory=memory, **decide_kwargs)
    try:
        answer = respond(case["message"], case["user_id"], memory, decide, {**tools, **rag_tools}, ledger).answer or ""
    finally:
        tools["query_db"].close()
    body, _, sources = answer.partition("\n\nSources:\n")
    failures = [f"answer lacks {s!r}" for s in case["expect_in_answer"] if s not in body.replace(",", "")]
    failures += [f"sources lack {s!r}" for s in case["expect_cited"] if s not in sources]
    return answer, failures


def main() -> int:
    failed = 0
    for case in EVALS:
        answer, failures = run_eval(case)
        failed += bool(failures)
        print(f"{'FAIL' if failures else 'PASS'} {case['name']}: {'; '.join(failures) or 'ok'}\n{answer}\n")
    print(f"{len(EVALS) - failed}/{len(EVALS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
