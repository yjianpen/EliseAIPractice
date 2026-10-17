"""search_knowledge tool for the ReAct loop: company policy and housing-law passages for the resident's building.

Passages come from the RAG databases (data/rag/policies.db, data/rag/laws.db), scoped by rag.retrieve to the
resident's property, its company guidebook and the laws of its city/state. Citations work like query_db's:
every passage the tool returned to the model is appended to the shared ledger in code, so the answer cites
exactly what was retrieved, never text the model wrote. Unit-level data (open work orders) is left out:
query_db is the only path to a resident's records.
"""
from __future__ import annotations

from rag.retrieve import _table, build_context, get_unit, render_context


def make_rag_tools(tenant_id: str, ledger: list[dict]) -> tuple[dict, list[dict]]:
    """Build the search_knowledge tool for this resident; it appends one ledger entry per passage it returns."""
    leases = [lease for lease in _table("leases") if lease["tenant_id"] == tenant_id]
    unit_id = max(leases, key=lambda lease: lease["start_date"])["unit_id"] if leases else None
    property_id = get_unit(unit_id)["property_id"] if unit_id else None
    spec = {"type": "function", "name": "search_knowledge",  # flat tool format of the OpenAI Responses API
            "description": "Search the resident's building policies (company guidebook, property addendum) and the "
                           "housing laws that apply to it. Use it for rules, rights, safety and repair questions.",
            "parameters": {"type": "object", "properties": {"question": {"type": "string"}},
                           "required": ["question"]}}

    def run(question: str) -> str:
        if not property_id:
            return "Error: no lease on file for this resident, so no building policies or laws could be looked up."
        ctx = build_context(question, property_id)
        for h in ctx["policies"]:
            ledger.append({"source": f"policies.db ({h['meta']['source_path']})", "exact": True,
                           "ids": [h["id"]], "columns": [h["title"]]})
        for h in ctx["laws"]:
            ledger.append({"source": f"laws.db ({h['meta']['citation']})", "exact": True,
                           "ids": [h["id"]], "columns": [f"{h['title']} <{h['meta']['source_url']}>"]})
        return render_context(ctx)
    return {"search_knowledge": run}, [spec]
