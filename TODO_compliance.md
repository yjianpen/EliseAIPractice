# Compliance engine — next steps (v1 = fair-housing keyword detection only)

- [ ] Act on violations in the ReAct loop: answer flagged queries with a fixed fair-housing refusal before any
      tool call, then rerun `python -m evals.fairness_eval` (baseline: 5/20 passing).
- [ ] Two-stage check (next PR): regex as a rough, high-recall filter (any protected-class term), then an LLM
      classifier only on those hits for the final call; fall back to the regex rule if the LLM fails.
- [ ] Known false positive: behaviour complaints that name a group, e.g. "The children in this building keep
      breaking the elevator" (protected term + "in this building"). Scope cues to the same clause as the term.
- [ ] Known gaps: misspellings, slurs, coded language and other languages are not matched; consider an LLM
      classifier as a second stage for queries the keywords miss.
- [ ] More rules beyond fair housing (e.g. requests for another resident's personal data).
