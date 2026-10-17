# Cite RAG passages (policies.db / laws.db) in answers

Questions about rules, rights and safety (e.g. "can i uninstall smoke detector or fire alert by myself?") need the
knowledge base, not the resident's records. Until now the agent couldn't search it at all. This PR adds a
`search_knowledge` tool (`rag_tools.py`). It runs `rag.retrieve.build_context` for the resident's building (their
latest lease → unit → property) and appends one entry per returned passage to the **same citation ledger** as
`query_db`. The citations come from code, like the DB ones: the answer cites what retrieval returned, never text the
model wrote.

- `policies.db` passages cite their chunk id, section title and source file (`knowledge/policies/...md`).
- `laws.db` passages cite their law id, legal citation, title and source URL.
- Unit-level data (open work orders) is left out of this tool's output, so `query_db` stays the only path to a
  resident's records.
- `agent.py` chat registers both tools and shares one ledger.
- Small fix: `query_db` now has a `.close()`, and the DB tests call it on cleanup. This silences the
  `ResourceWarning: unclosed database` lines the test run used to print.

Changed functions: `make_rag_tools` and its inner `run` (both new); the `agent.py` `__main__` wiring. Tests are in `tests/test_rag_tools.py`.

## Test locally (Mac)

```bash
.venv/bin/python -m unittest discover -s tests -q
```

Custom inputs: pass any tenant id, then one or more questions:

```bash
.venv/bin/python -c "import sys; from rag_tools import make_rag_tools; from db_tools import format_citations; l=[]; t,_=make_rag_tools(sys.argv[1], l); [print(t['search_knowledge'](q)) for q in sys.argv[2:]]; print(format_citations(l))" T-00329 "can i uninstall smoke detector or fire alert by myself?"
```

Expected: the unit tests print no `ResourceWarning`, and the Sources block lists `policies.db (knowledge/policies/companies/C-LUMEN.md): guidebook-c-lumen#18 - ... Smoke and carbon monoxide alarms`
and `laws.db (NYC Admin. Code Title 28, Art. 312; ...): nyc-smoke-co-alarms`.

Full chat with the real model (needs `OPENAI_API_KEY` in `.env`):

```bash
.venv/bin/python agent.py T-00329
```

🤖 Generated with [Claude Code](https://claude.com/claude-code)
