# Add evals/happy_path.py: monthly-rent eval with tenant, lease and apartment ids

This adds a first end-to-end eval. It runs the **real** agent (OpenAI model + `query_db` + `search_knowledge`) on one
resident message and checks both the answer and its citations:

| case | user | message | checks |
|---|---|---|---|
| `monthly_rent_with_ids` | T-00001 | "Hi, this is tenant T-00001, lease L-00001, apartment 1A. What is my monthly rent?" | answer states `3320` (commas ignored, so `$3,320` passes); Sources cite `leases.csv: L-00001` for `monthly_rent` |

The expected values come from `data/synthetic/leases.csv` (L-00001 → P-NYC-001-1A, rent 3320) and `units.csv`
(unit number 1A). The script prints PASS/FAIL with the full cited answer, and it exits 1 if any case fails.

Changed functions: `run_eval` and `main` (both new). The file is `evals/happy_path.py`; no other files change.

## Test locally (Mac)

The eval calls OpenAI, so it needs `OPENAI_API_KEY` in `.env` at the repo root (or exported in your shell):

```bash
.venv/bin/python -m evals.happy_path
```

Expected: `PASS monthly_rent_with_ids: ok`, then the answer ending with `Sources:\n[1] leases.csv: L-00001 - monthly_rent`, then `1/1 passed`.

Custom inputs: ask your own question as any tenant, and check for your own expected strings:

```bash
.venv/bin/python -c "import sys; from evals.happy_path import run_eval; a,f=run_eval({'user_id': sys.argv[1], 'message': sys.argv[2], 'expect_in_answer': [sys.argv[3]], 'expect_cited': [sys.argv[4]]}); print(a); print(f or 'PASS')" T-00002 "I'm in apartment 1B, lease L-00002. What's my rent?" 2090 "leases.csv: L-00002"
```

The unit tests are unchanged and still pass:

```bash
.venv/bin/python -m unittest discover -s tests -q
```

🤖 Generated with [Claude Code](https://claude.com/claude-code)
