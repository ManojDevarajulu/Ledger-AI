# Ledger AI — Implementation Roadmap

> **Tracking:** Active engineering tasks for Ledger AI.

---

## Completed Milestones

- [x] **Milestone 1: Hardened Environment & FinanceBench Ingestion**
  - Pin secure dependencies (`fastapi`, `uvicorn`, `pydantic`, `rank-bm25`, `numpy`, `openai`, `beautifulsoup4`).
  - Curate 20 SEC 10-K benchmark cases from Patronus AI's FinanceBench (including refusal cases).
  - Add data integrity verification tests (`tests/test_data_integrity.py`).

- [x] **Milestone 2: Core Processing & Verification Engine**
  - Implement `src/table_parser.py`: contextual table chunker with unit scale and hierarchy propagation.
  - Implement `src/hybrid_retriever.py`: BM25 + dense search with weighted Reciprocal Rank Fusion and exact term reranking.
  - Implement `src/math_verifier.py`: AST-whitelisted `decimal.Decimal` calculator supporting CAGR, variable resolution, and scale conversions.
  - Implement `src/refusal_guard.py`: calibrated refusal for non-disclosed data, temporal mismatches, and forward-looking guidance.
  - Verify with unit tests (`tests/test_core_engine.py` and `tests/test_core_engine_expanded.py`).

- [x] **Milestone 3: Benchmark Evaluation Runner**
  - Build `src/eval_runner.py` measuring 4-way ablation pipeline performance across all 20 benchmark cases.
  - Validate 90.0% answer accuracy and reduced calculation error on verified pipeline in < 0.20s.

- [x] **Milestone 4: Interactive Financial Terminal UI**
  - Build FastAPI service (`web/server.py`).
  - Create dark-mode dashboard (`web/static/`) with dynamic cell highlighting, math tracing, and live benchmark execution.
  - Add 1-command launcher (`run.py`).
  - Verify with end-to-end integration tests (`tests/test_server_api.py`).

---

## Upcoming Enhancements

- [ ] Multi-filing comparative reasoning (side-by-side quarterly YoY across multiple companies).
- [ ] EDGAR real-time API connector via `edgartools` with XBRL fact tag verification.
- [ ] ColPali / vision-based multi-modal PDF table embedding front-end.
