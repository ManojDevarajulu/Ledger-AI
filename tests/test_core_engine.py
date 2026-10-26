import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from decimal import Decimal
from src.math_verifier import DeterministicMathVerifier, SafeASTEvaluator
from src.table_parser import TableParser
from src.hybrid_retriever import HybridRetriever
from src.refusal_guard import CalibratedRefusalGuard

def test_deterministic_math_verifier_valid():
    # Microsoft Intelligent Cloud growth: (87907 - 75251) / 75251 * 100
    res = DeterministicMathVerifier.verify_and_compute(
        formula="(87907 - 75251) / 75251 * 100",
        unit="%",
        precision=2
    )
    assert res.status == "VERIFIED"
    assert res.result == 16.82
    assert res.formatted_result == "16.82%"
    assert res.is_safe is True

def test_deterministic_math_verifier_division_by_zero():
    res = DeterministicMathVerifier.verify_and_compute(
        formula="100 / 0",
        unit="%"
    )
    assert res.status == "REJECTED"
    assert "Division by zero" in res.error_message

def test_deterministic_math_verifier_security_sandbox():
    # Attempting arbitrary code execution injection
    malicious_inputs = [
        "__import__('os').system('echo pwned')",
        "eval('2 + 2')",
        "open('/etc/passwd').read()",
        "lambda: 42"
    ]
    for bad_code in malicious_inputs:
        res = DeterministicMathVerifier.verify_and_compute(formula=bad_code)
        assert res.status == "REJECTED"
        assert res.is_safe is False or "Disallowed" in str(res.error_message)

def test_table_parser_and_chunking():
    md = """| Segment | FY2022 | FY2023 |
|---|---|---|
| Intelligent Cloud | 75251 | 87907 |
| Productivity | 63364 | 69274 |"""

    parsed = TableParser.parse_markdown_table(
        table_markdown=md,
        table_id="t1",
        title="Segment Data",
        section="Note 19",
        company="Microsoft",
        fiscal_year=2023,
        unit_scale="USD in millions"
    )

    assert len(parsed.rows) == 2
    cell = parsed.get_cell("Intelligent Cloud", "FY2023")
    assert cell is not None
    assert cell.numeric_value == 87907.0

    context_chunks = parsed.to_contextual_chunks()
    assert len(context_chunks) == 2
    assert "USD in millions" in context_chunks[0]
    assert "Microsoft 2023 10-K" in context_chunks[0]

def test_hybrid_retriever_rrf():
    docs = [
        "Microsoft Intelligent Cloud revenue was $87,907 million in FY2023.",
        "Amazon AWS sales reached $90,764 million in fiscal year 2023.",
        "Apple iPhone sales were $200,583 million."
    ]
    retriever = HybridRetriever(docs)
    
    # Query for Microsoft Cloud
    results = retriever.search_hybrid_rrf("Microsoft Intelligent Cloud FY2023 revenue", top_k=2)
    assert len(results) == 2
    assert results[0].chunk_id == 0
    assert "Microsoft" in results[0].text

def test_refusal_guard():
    guard = CalibratedRefusalGuard(confidence_floor=0.01)
    
    # Non-disclosed query should refuse
    refusal = guard.evaluate(
        query="What was Microsoft Copilot standalone ARR in FY2022?",
        retrieved_context="Total revenue was $198,270 million.",
        retrieval_score=0.05
    )
    assert refusal.should_refuse is True
    assert refusal.reason_category == "NON_DISCLOSED_METRIC"

    # Valid grounded query should accept
    acceptance = guard.evaluate(
        query="What was Intelligent Cloud revenue in FY2023?",
        retrieved_context="Intelligent Cloud revenue was $87,907 million.",
        retrieval_score=0.08,
        cited_cells=[{"row": "Cloud", "val": 87907}]
    )
    assert acceptance.should_refuse is False

if __name__ == "__main__":
    test_deterministic_math_verifier_valid()
    test_deterministic_math_verifier_division_by_zero()
    test_deterministic_math_verifier_security_sandbox()
    test_table_parser_and_chunking()
    test_hybrid_retriever_rrf()
    test_refusal_guard()
    print("ALL CORE ENGINE UNIT TESTS PASSED (6/6)!")
