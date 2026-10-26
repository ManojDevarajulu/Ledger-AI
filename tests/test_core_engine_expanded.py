import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from decimal import Decimal
from src.math_verifier import DeterministicMathVerifier
from src.table_parser import TableParser
from src.hybrid_retriever import HybridRetriever
from src.refusal_guard import CalibratedRefusalGuard

def test_cagr_and_power_math():
    # 2-Year CAGR formula: ((End / Start) ** (1/2) - 1) * 100
    # From 100 to 144 over 2 years: sqrt(1.44) - 1 = 0.20 -> 20.0%
    cagr_formula = "((144 / 100) ** (1 / 2) - 1) * 100"
    res = DeterministicMathVerifier.verify_and_compute(cagr_formula, unit="%", precision=2)
    assert res.status == "VERIFIED"
    assert res.result == 20.0
    assert res.formatted_result == "20.00%"
    print("PASS: CAGR & Power math verification.")

def test_symbolic_variable_resolution():
    formula = "(rev_fy23 - rev_fy22) / rev_fy22 * 100"
    vars_map = {
        "rev_fy23": 87907,
        "rev_fy22": 75251
    }
    res = DeterministicMathVerifier.verify_and_compute(
        formula=formula,
        variables=vars_map,
        unit="%"
    )
    assert res.status == "VERIFIED"
    assert res.result == 16.82
    assert "87907" in res.resolved_formula
    print("PASS: Symbolic variable resolution.")

def test_scale_conversion():
    # $1,500,000 thousands = $1,500 millions
    converted = DeterministicMathVerifier.convert_scale(1500000, from_scale="thousands", to_scale="millions")
    assert converted == 1500.0

    # $2.5 billion = $2,500 million
    conv_b = DeterministicMathVerifier.convert_scale(2.5, from_scale="billions", to_scale="millions")
    assert conv_b == 2500.0
    print("PASS: Scale conversion.")

def test_hierarchical_table_parser_and_footnotes():
    md = """| Metric | FY2022 | FY2023 |
|---|---|---|
| Operating Expenses: | | |
| Research and Development (1) | 26251 | 29915 |
| Selling, General and Administrative | 25094 | 24932 |"""

    parsed = TableParser.parse_markdown_table(
        table_markdown=md,
        table_id="t_hier",
        title="Operating Expenses",
        section="Item 8",
        company="Apple",
        fiscal_year=2023,
        unit_scale="USD in millions"
    )

    assert len(parsed.rows) == 2
    rd_row = parsed.rows[0]
    assert rd_row.row_label == "Research and Development"
    assert "Operating Expenses: > Research and Development" in rd_row.hierarchy_path
    assert "1" in rd_row.footnote_refs
    
    chunks = parsed.to_contextual_chunks()
    assert "Category: Operating Expenses: > Research and Development" in chunks[0]
    assert "Footnotes: 1" in chunks[0]
    print("PASS: Hierarchical table category and footnote parsing.")

def test_html_table_parsing():
    html_sample = """
    <table>
        <tr><th>Segment</th><th>FY2022</th><th>FY2023</th></tr>
        <tr><td>Intelligent Cloud</td><td>75251</td><td>87907</td></tr>
        <tr><td>More Personal Computing</td><td>59655</td><td>54734</td></tr>
    </table>
    """
    parsed = TableParser.parse_html_table(
        html_content=html_sample,
        table_id="html_1",
        title="Segment Breakdown",
        section="Note 19",
        company="Microsoft",
        fiscal_year=2023
    )
    assert len(parsed.rows) == 2
    cell = parsed.get_cell("Intelligent Cloud", "FY2023")
    assert cell.numeric_value == 87907.0
    print("PASS: SEC HTML table parser.")

def test_metadata_prefiltering_and_reranking():
    docs = [
        "Microsoft Cloud revenue in FY2023 was $87,907 million.",
        "Apple iPhone net sales in FY2023 was $200,583 million.",
        "Microsoft Productivity revenue in FY2023 was $69,274 million."
    ]
    meta = [
        {"ticker": "MSFT", "fiscal_year": 2023},
        {"ticker": "AAPL", "fiscal_year": 2023},
        {"ticker": "MSFT", "fiscal_year": 2023}
    ]
    retriever = HybridRetriever(docs, metadata=meta)

    # Filter strictly for MSFT
    msft_results = retriever.search_hybrid_rrf("revenue", filter_dict={"ticker": "MSFT"}, top_k=2)
    assert len(msft_results) == 2
    for r in msft_results:
        assert r.metadata["ticker"] == "MSFT"

    # Second-stage exact reranker
    candidates = retriever.search_sparse("Microsoft FY2023 Cloud", top_k=3)
    reranked = retriever.rerank_exact_terms("Microsoft FY2023 Cloud revenue 87907", candidates, top_n=1)
    assert "87,907" in reranked[0].text
    print("PASS: Metadata pre-filtering & exact term reranking.")

def test_expanded_refusal_guard():
    guard = CalibratedRefusalGuard()

    # Forward-looking forecast rejection
    res_fwd = guard.evaluate(
        query="What is the projected revenue forecast for next year?",
        retrieved_context="Total historical revenue was $211,915 million.",
        retrieval_score=0.08
    )
    assert res_fwd.should_refuse is True
    assert res_fwd.reason_category == "FORWARD_LOOKING_OUT_OF_SCOPE"

    # Temporal boundary mismatch (asking for FY2018 when filing is FY2022/FY2023)
    res_year = guard.evaluate(
        query="What was net sales in 2018?",
        retrieved_context="Net sales in FY2023 was $383,285 million.",
        retrieval_score=0.08,
        available_fiscal_years=[2022, 2023]
    )
    assert res_year.should_refuse is True
    assert res_year.reason_category == "TEMPORAL_OUT_OF_BOUNDS"
    print("PASS: Expanded refusal guard (forward-looking & temporal boundaries).")

if __name__ == "__main__":
    test_cagr_and_power_math()
    test_symbolic_variable_resolution()
    test_scale_conversion()
    test_hierarchical_table_parser_and_footnotes()
    test_html_table_parsing()
    test_metadata_prefiltering_and_reranking()
    test_expanded_refusal_guard()
    print("\nALL EXPANDED CORE ENGINE TESTS PASSED (7/7)!")
