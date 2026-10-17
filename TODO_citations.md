# Citations — follow-ups (deferred from feature/db-citations)

- [x] Row-level lineage: cite only the rows a query returned (e.g. `WHERE status = 'open'` on
      my_work_orders currently cites all of the resident's work orders, capped at 5 + "N more").
      Done for simple single-table SELECTs; joins/CTEs/compound selects still cite the whole record set.
- [ ] Row-level lineage for joins and CTEs (today they fall back, marked "row lineage unavailable").
- [ ] units.csv has repeated unit_id rows, so unit citations repeat the same id; dedupe or use a real key.
- [ ] Strip any model-written "Sources:" block from the answer before appending the ledger's.
- [ ] Return citations as a structured field on LoopResult (for UI rendering) instead of only as text.
- [ ] Cite RAG / knowledge-base passages the same way (ledger filled by the retrieval tool).
