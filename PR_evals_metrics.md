# Eval metrics (token usage, answer accuracy) and saved eval cases

`python -m evals.happy_path` now ends every run with two metrics:

```
4/8 passed
answer accuracy: 4/8 (50%) | citation accuracy: 8/8 (100%)
  monthly_rent 1/2 (50%) | security_deposit 0/1 (0%) | lease_start_date 1/1 (100%) | ...
token usage: total 1,656 | mean 207/case | max 214
```

- **Answer accuracy:** the share of cases whose answer states the value on file, overall and per topic. Citation
  accuracy (the right record and column appear in Sources) is reported next to it, so a correct but uncited answer
  is easy to spot.
- **Token usage:** the tokens each case used (`LoopResult.tokens_used`, summed over every model call in the ReAct loop).
  Each case's PASS/FAIL line shows its own count; the summary shows the total, mean and max.
- `run_eval` now returns `(answer, failures, tokens_used)`.
- **Saved cases:** a run reuses `evals/happy_path_cases.json` (committed: the 40 default cases, one per line) instead of
  generating new ones, so every run and every machine asks the same questions about the same leases. The generator
  runs only when no file is saved yet, or when you pass `--regenerate`; it then saves the result, plus the args that
  produced it. `--cases PATH` picks a different file. Generator args passed without `--regenerate` while a file
  exists are ignored, and the run says so.

Changed functions: `load_or_generate_evals` (new); `run_eval` and `main` (updated). The sample output above is from an offline run of `main()` with a
fake model that answers every other case correctly. Not yet run against the real OpenAI model.

## Test locally (Mac)

Needs `OPENAI_API_KEY` in `.env` at the repo root. All 40 cases:

```bash
.venv/bin/python -m evals.happy_path
```

The first line should say `loaded 40 cases from .../evals/happy_path_cases.json`.

Custom inputs: generate your own cases into a separate file (so the committed 40 stay untouched), then rerun to reuse them:

```bash
.venv/bin/python -m evals.happy_path --cases /tmp/my_cases.json --regenerate --num-tests 6 --topics monthly_rent bedrooms --lease-ids L-00001 L-00002 L-00003
```

```bash
.venv/bin/python -m evals.happy_path --cases /tmp/my_cases.json
```

The first command prints `generated and saved 6 cases`; the second prints `loaded 6 cases` and asks the same questions.

One case of your own, with its token count:

```bash
.venv/bin/python -c "import sys; from evals.happy_path import run_eval; a,f,t=run_eval({'user_id': sys.argv[1], 'message': sys.argv[2], 'expect_any_of': [sys.argv[3]], 'expect_cited': [sys.argv[4]]}); print(a); print(f or 'PASS', f'{t} tokens')" T-00002 "I'm in apartment 1B, lease L-00002. What's my rent?" 2090 "leases.csv"
```

Unit tests are unchanged:

```bash
.venv/bin/python -m unittest discover -s tests -q
```

🤖 Generated with [Claude Code](https://claude.com/claude-code)
