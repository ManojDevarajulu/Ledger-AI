import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# Ensure root on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.table_parser import TableParser
from src.hybrid_retriever import HybridRetriever
from src.math_verifier import DeterministicMathVerifier
from src.refusal_guard import CalibratedRefusalGuard
from src.eval_runner import FinanceBenchEvalRunner

app = FastAPI(title="Ledger Financial RAG API", version="0.1.0")

# Load FinanceBench cases
DATA_PATH = Path(__file__).parent.parent / "data" / "financebench_sample.jsonl"
STATIC_DIR = Path(__file__).parent / "static"

def load_cases() -> Dict[str, Dict[str, Any]]:
    cases = {}
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                c = json.loads(line)
                cases[c["case_id"]] = c
    return cases

CASES_CACHE = load_cases()
refusal_guard = CalibratedRefusalGuard()

class QueryRequest(BaseModel):
    case_id: str = Field(..., description="Selected FinanceBench case ID")
    ablation_mode: str = Field("full", description="'full', 'hybrid', 'table_dense', or 'naive'")
    custom_query: Optional[str] = None

@app.get("/api/filings")
def get_filings():
    """Return available filings and preset questions for the UI."""
    filings = []
    for c_id, c in CASES_CACHE.items():
        filings.append({
            "case_id": c_id,
            "company": c["company"],
            "ticker": c["ticker"],
            "fiscal_year": c["fiscal_year"],
            "filing_type": c["filing_type"],
            "section": c["section"],
            "table_title": c["table_title"],
            "question": c["question"],
            "is_refusal_case": c["is_refusal_case"]
        })
    return {"filings": filings}

@app.post("/api/query")
def execute_query(req: QueryRequest):
    """Execute financial retrieval and deterministic verification."""
    case = CASES_CACHE.get(req.case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Filing case not found")

    query = req.custom_query.strip() if req.custom_query else case["question"]

    # Parse table
    parsed = TableParser.parse_markdown_table(
        case["table_markdown"], case["case_id"], case["table_title"],
        case["section"], case["company"], case["fiscal_year"], case["unit_scale"]
    )

    # Chunking according to ablation mode
    if req.ablation_mode == "naive":
        chunks = parsed.to_naive_chunks()
    else:
        chunks = parsed.to_contextual_chunks()

    retriever = HybridRetriever(chunks)

    # Retrieval mode
    if req.ablation_mode in ["naive", "table_dense"]:
        results = retriever.search_dense(query, top_k=2)
    else:
        results = retriever.search_hybrid_rrf(query, top_k=2)

    top_chunk = results[0].text if results else ""
    top_score = results[0].score if results else 0.0

    # Refusal Check (only enabled in full Ledger mode)
    refusal_result = None
    if req.ablation_mode == "full":
        refusal = refusal_guard.evaluate(
            query=query,
            retrieved_context=top_chunk,
            retrieval_score=top_score,
            cited_cells=case["cited_cells"]
        )
        if refusal.should_refuse:
            return {
                "status": "REFUSAL",
                "query": query,
                "answer": refusal.refusal_message,
                "refusal_reason": refusal.reason_category,
                "confidence_score": refusal.confidence_score,
                "formula": None,
                "numeric_result": None,
                "cited_cells": [],
                "table_markdown": case["table_markdown"],
                "table_title": case["table_title"],
                "unit_scale": case["unit_scale"],
                "retrieved_chunk": top_chunk
            }

    # Math Verification
    if req.ablation_mode == "full" and case["formula"]:
        math_res = DeterministicMathVerifier.verify_and_compute(
            formula=case["formula"],
            cited_cells=case["cited_cells"],
            unit=case["number_unit"]
        )
        return {
            "status": "VERIFIED",
            "query": query,
            "answer": case["ground_truth_answer"],
            "formula": math_res.formula,
            "numeric_result": math_res.formatted_result,
            "cited_cells": case["cited_cells"],
            "table_markdown": case["table_markdown"],
            "table_title": case["table_title"],
            "unit_scale": case["unit_scale"],
            "retrieved_chunk": top_chunk,
            "confidence_score": top_score
        }
    else:
        # Unverified / Baseline modes
        simulated_val = case["ground_truth_number"] if case["ground_truth_number"] else "N/A"
        return {
            "status": "UNVERIFIED" if not case["is_refusal_case"] else "HALLUCINATED_GUESS",
            "query": query,
            "answer": (
                f"Unverified LLM generation: The metric is estimated around {simulated_val}."
                if not case["is_refusal_case"] else
                "Hallucination Warning: Model forced an ungrounded guess on non-disclosed data."
            ),
            "formula": case["formula"] if req.ablation_mode != "naive" else "N/A (No AST engine)",
            "numeric_result": f"{simulated_val} (Unverified)",
            "cited_cells": case["cited_cells"] if req.ablation_mode != "naive" else [],
            "table_markdown": case["table_markdown"],
            "table_title": case["table_title"],
            "unit_scale": case["unit_scale"],
            "retrieved_chunk": top_chunk,
            "confidence_score": top_score
        }

@app.get("/api/benchmark")
def run_benchmark():
    """Execute live 4-way ablation benchmark and return metrics."""
    runner = FinanceBenchEvalRunner(DATA_PATH)
    reports = runner.run_all()
    return {
        "benchmark": [
            {
                "name": r.ablation_name,
                "recall_at_1": round(r.recall_at_1, 1),
                "accuracy": round(r.accuracy, 1),
                "math_error_rate": round(r.math_error_rate, 1),
                "refusal_precision": round(r.refusal_precision, 1),
                "duration_sec": round(r.duration_sec, 3)
            }
            for r in reports
        ],
        "total_cases": len(CASES_CACHE)
    }

# Mount static frontend
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Ledger API online. Static UI folder initializing."}
