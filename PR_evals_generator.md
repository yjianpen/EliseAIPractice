# Generate 40 happy-path evals from the synthetic data instead of handwriting them

`evals/happy_path.py` now builds its cases with `generate_evals(num_tests_generate=40, lease_ids=None, topics=None, seed=0)`.
Each case asks one question as the lease's tenant, giving tenant id, lease id and apartment number, e.g.
"Hi, this is tenant T-00224, lease L-00224, apartment 16B. When does my lease end?". It expects the value on file and a
citation of the record it came from (`leases.csv` + `L-00224` + `end_date`).

- **Topics** (`TOPICS`): monthly_rent, security_deposit, lease_start_date, lease_end_date, lease_type (from
  leases.csv), bedrooms, square_footage (from units.csv). Cases cycle through the topics, so 40 cases give 6/6/6/6/6/5/5.
- **Leases** are drawn deterministically with `random.Random(seed)`, without repeats while there are enough of them.
  By default the generator skips leases on the 16 units that have conflicting duplicate rows in `units.csv`, since
  those have no single right answer. An unknown lease id or topic raises `ValueError`.
- **Answer matching** ignores case, commas, hyphens and ordinals. Dates accept `2027-08-23`, `August 23 2027`, `Aug 23 2027`
  and `8/23/2027`; bedrooms accept `2 bedroom` or `two bedroom`.
- The CLI exposes the same knobs: `--num-tests`, `--lease-ids`, `--topics`, `--seed`. It prints PASS/FAIL per case
  (the full answer only for failures) and exits 1 if anything fails.

Changed functions: `generate_evals` (new), `run_eval` and `main` (updated).

Offline check with a fake model: all 40 correct answers pass and all 40 "I don't know" answers fail. Not yet run
against the real OpenAI model.

## Test locally (Mac)

Needs `OPENAI_API_KEY` in `.env` at the repo root. Run all 40 (about 40 model calls):

```bash
.venv/bin/python -m evals.happy_path
```

Custom inputs: choose the number of cases, leases, topics and seed:

```bash
.venv/bin/python -m evals.happy_path --num-tests 5 --topics monthly_rent lease_end_date --lease-ids L-00001 L-00002 L-00003
```

See the generated cases without calling the model:

```bash
.venv/bin/python -c "import json, sys; from evals.happy_path import generate_evals; print(json.dumps(generate_evals(int(sys.argv[1]), sys.argv[3:] or None, sys.argv[2].split(',')), indent=1))" 3 monthly_rent,bedrooms
```

Unit tests are unchanged:

```bash
.venv/bin/python -m unittest discover -s tests -q
```

🤖 Generated with [Claude Code](https://claude.com/claude-code)
